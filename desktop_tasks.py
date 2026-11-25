"""Date-based research tasks shared by calendar, Gantt and agents."""
import calendar
import copy
import datetime as dt
import re
import uuid

STATUSES = {'todo', 'doing', 'blocked', 'done'}
REPEATS = {'none', 'daily', 'weekly', 'monthly'}


def date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('任务日期须为 YYYY-MM-DD')
    return dt.date.fromisoformat(value)


def normalize(task, cards, previous=None):
    """Upgrade an old task in memory; never change a source file on reads."""
    previous = previous or {}
    t = {**copy.deepcopy(previous), **copy.deepcopy(task)}
    t.setdefault('card', '')
    t.setdefault('project_id', '')
    if not t['project_id']:
        card = next((c for c in cards if c['id'] == t['card']), {})
        if card.get('type') == 'project':
            t['project_id'] = card['target']
    t.setdefault('start_date', t.get('date', ''))
    t.setdefault('status', 'done' if t.get('done') else 'todo')
    # Old calendar clients only edit done. Their writes keep new metadata.
    if 'done' in task and task['done'] != previous.get('done') and ('status' not in task or task.get('status') == previous.get('status')):
        t['status'] = 'done' if task['done'] else 'todo'
    t['done'] = t['status'] == 'done'
    t.setdefault('progress', 100 if t['done'] else 0)
    if t['done']:
        t['progress'] = 100
    elif previous.get('done') and t['progress'] == 100:
        t['progress'] = 0
    for k, default in [('dependencies', []), ('milestone', False), ('repeat', 'none'), ('notes', '')]:
        t.setdefault(k, default)
    return t


def normalize_board(board, previous=None):
    result = copy.deepcopy(board)
    old = {t['id']: t for t in (previous or {}).get('todos', [])}
    previous_cards = list({c['id']:c for c in (previous or {}).get('cards',[])+result['cards']}.values())
    result['todos'] = [normalize(t, previous_cards, old.get(t.get('id'))) for t in result['todos']]
    ids = {c['id'] for c in result['cards']}
    for t in result['todos']:
        if t['card'] and t['card'] not in ids:
            t['card'] = ''
    return result


def validate(tasks, cards, project_ids):
    ids = set()
    card_ids = {c['id'] for c in cards}
    for t in tasks:
        if not isinstance(t, dict) or not isinstance(t.get('id'), str) or not 1 <= len(t['id']) <= 100 or t['id'] in ids:
            raise ValueError('任务 ID 重复或无效')
        ids.add(t['id'])
        if not isinstance(t.get('title'), str) or not 1 <= len(t['title'].strip()) <= 1000:
            raise ValueError('请填写任务标题（最多 1000 字）')
        if date(t['start_date']) > date(t['date']):
            raise ValueError('开始日期不能晚于截止日期')
        if t['status'] not in STATUSES or type(t['done']) is not bool or t['done'] != (t['status'] == 'done'):
            raise ValueError('任务状态无效')
        if type(t['progress']) is not int or not 0 <= t['progress'] <= 100:
            raise ValueError('任务进度须为 0–100 的整数')
        if t['repeat'] not in REPEATS or type(t['milestone']) is not bool:
            raise ValueError('任务重复规则或里程碑无效')
        if t['milestone'] and t['start_date'] != t['date']:
            raise ValueError('里程碑的开始和截止日期须相同')
        if t['project_id'] and t['project_id'] not in project_ids:
            raise ValueError('任务关联项目不存在')
        if t['card'] and t['card'] not in card_ids:
            raise ValueError('任务关联卡片不存在')
        if not isinstance(t['notes'], str) or len(t['notes']) > 12000:
            raise ValueError('任务说明过长或无效')
        if not isinstance(t['dependencies'], list) or len(t['dependencies']) > 100 or any(not isinstance(x, str) for x in t['dependencies']) or len(set(t['dependencies'])) != len(t['dependencies']):
            raise ValueError('任务依赖无效')
    deps = {t['id']: t['dependencies'] for t in tasks}
    indegree = {k: len(v) for k, v in deps.items()}
    children = {k: [] for k in deps}
    for id, parents in deps.items():
        for parent in parents:
            if parent not in ids or parent == id:
                raise ValueError('前置任务不存在或任务依赖自身')
            children[parent].append(id)
    ready = [k for k, v in indegree.items() if not v]
    visited = 0
    while ready:
        id = ready.pop(); visited += 1
        for child in children[id]:
            indegree[child] -= 1
            if not indegree[child]: ready.append(child)
    if visited != len(tasks):
        raise ValueError('任务依赖不能形成循环')


def warnings(tasks):
    by_id = {t['id']: t for t in tasks}
    result = []
    for t in tasks:
        for id in t['dependencies']:
            p = by_id[id]
            if t['start_date'] <= p['date']:
                result.append({'task_id': t['id'], 'dependency_id': id, 'kind': 'schedule_overlap', 'message': '开始日期未晚于前置任务截止日期；未自动改期。'})
            if t['status'] in {'doing', 'done'} and not p['done']:
                result.append({'task_id': t['id'], 'dependency_id': id, 'kind': 'dependency_unfinished', 'message': '前置任务尚未完成。'})
    return result


def advance(value, rule):
    d = date(value)
    if rule == 'daily': return (d + dt.timedelta(days=1)).isoformat()
    if rule == 'weekly': return (d + dt.timedelta(days=7)).isoformat()
    month = d.month % 12 + 1
    year = d.year + (1 if d.month == 12 else 0)
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1])).isoformat()


def repeat_completed(board, previous):
    old = {t['id']: t for t in previous.get('todos', [])}
    ids = {t['id'] for t in board['todos']}
    additions = []
    for t in board['todos']:
        if not t['done'] or old.get(t['id'], {}).get('done') or t['repeat'] == 'none':
            continue
        next_id = 'repeat-' + uuid.uuid5(uuid.NAMESPACE_URL, 'ai4s:' + t['id']).hex
        # Remember emission even if the user later removes the next instance.
        if t.get('next_instance_id') or next_id in ids:
            continue
        n = copy.deepcopy(t)
        n.update(id=next_id, start_date=advance(t['start_date'], t['repeat']), date=advance(t['date'], t['repeat']), status='todo', done=False, progress=0, previous_instance_id=t['id'])
        n.pop('next_instance_id', None)
        t['next_instance_id'] = next_id
        additions.append(n); ids.add(next_id)
    board['todos'].extend(additions)
