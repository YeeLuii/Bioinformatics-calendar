"""Per-store atomic change history and field-level conflict-aware undo."""
import copy
import uuid
import datetime
import desktop_runtime as rt
from desktop_storage import read_json, write_json

STORES = {'board': 'desktop_board_state.json', 'projects': 'desktop_projects.json', 'links': 'desktop_project_links.json'}


def records(store, doc):
    if store == 'board':
        return {name: {x['id']: x for x in doc.get(name, [])} for name in ('cards', 'todos')}
    if store == 'projects':
        return {'projects': {x['id']: x for x in doc.get('projects', [])}}
    return {'links': doc.get('projects', {})}


def changed(store, before, after):
    a, b = records(store, before), records(store, after)
    changes = []
    for collection in a:
        for key in sorted(set(a[collection]) | set(b[collection])):
            old, new = a[collection].get(key), b[collection].get(key)
            if old != new:
                changes.append({'collection': collection, 'key': key, 'before': old, 'after': new})
    return changes


def write(store, before, after, label, undo_of=None):
    """Caller holds the workspace lock. Data and audit are one atomic JSON write."""
    entries = copy.deepcopy(before.get('_history', read_json(rt.path(STORES[store]), {}).get('_history', [])))
    entry = {'id': 'change-' + uuid.uuid4().hex, 'store': store, 'at': datetime.datetime.now().astimezone().isoformat(timespec='microseconds'), 'label': label, 'changes': changed(store, before, after)}
    if undo_of:
        entry['undo_of'] = undo_of
        for old in entries:
            if old['id'] == undo_of: old['undone_by'] = entry['id']
    if entry['changes']:
        entries.append(entry)
    # Bounded history. The data itself is never truncated.
    after['_history'] = entries[-100:]
    write_json(rt.path(STORES[store]), after)
    return entry


def snapshot():
    docs = {store: read_json(rt.path(name), {}) for store, name in STORES.items()}
    return docs, sum(d.get('revision', 0) for d in docs.values())


def listing():
    with rt.workspace_lock():
        docs, revision = snapshot()
        entries = [e for doc in docs.values() for e in doc.get('_history', [])]
        return {'revision': revision, 'entries': sorted(entries, key=lambda x: x['at'], reverse=True)}


def reverse_record(current, before, after):
    if before is None or after is None or not isinstance(before, dict) or not isinstance(after, dict):
        if current != after: raise ValueError('目标已被后续操作修改，无法安全撤销')
        return copy.deepcopy(before)
    if not isinstance(current, dict): raise ValueError('目标已被移除，无法安全撤销')
    result = copy.deepcopy(current)
    for key in set(before) | set(after):
        if key == 'updated_at': continue
        if before.get(key) == after.get(key) and (key in before) == (key in after): continue
        if current.get(key) != after.get(key) or (key in current) != (key in after):
            raise ValueError('字段 '+key+' 已被后续操作修改，无法安全撤销')
        if key in before: result[key] = copy.deepcopy(before[key])
        else: result.pop(key, None)
    return result


def undo(entry_id, expected_revision):
    from desktop_services import ConflictError, NotFoundError
    with rt.workspace_lock():
        docs, revision = snapshot()
        if revision != expected_revision: raise ConflictError('历史 revision 冲突，请重新读取')
        entry = next((e for d in docs.values() for e in d.get('_history', []) if e['id'] == entry_id), None)
        if not entry: raise NotFoundError('历史记录不存在或已超出保留范围')
        if entry.get('undone_by'): raise ValueError('该操作已经撤销')
        store = entry['store']; old = docs[store]; new = copy.deepcopy(old)
        cols = records(store, new)
        try:
            for change in entry['changes']:
                col = cols[change['collection']]; key = change['key']
                restored = reverse_record(col.get(key), change['before'], change['after'])
                if restored is None: col.pop(key, None)
                else: col[key] = restored
        except ValueError as e: raise ConflictError(str(e))
        if store == 'board':
            import desktop_state
            new.update({k: list(v.values()) for k, v in cols.items()})
            desktop_state.validate(new)
        elif store == 'projects':
            new['projects'] = list(cols['projects'].values())
            for p in new['projects']:
                if any(c['key']==p['id'] for c in entry['changes']):p['updated_at']=rt.now()
            # Undo of a newly created project cannot leave tasks/cards/links orphaned.
            deleted = {x['id'] for x in old.get('projects', [])} - set(cols['projects'])
            generated = read_json(rt.path('desktop_data.json'), {})
            deleted -= {p['id'] for p in generated.get('projects', [])}
            board = docs['board']
            if any(c.get('type') == 'project' and c.get('target') in deleted for c in board.get('cards', [])) or any(t.get('project_id') in deleted for t in board.get('todos', [])) or any(docs['links'].get('projects', {}).get(k) for k in deleted):
                raise ConflictError('新项目已经被卡片、任务或会话使用，不能撤销创建；可归档项目')
        else: new['projects'] = cols['links']
        new['revision'] = old.get('revision', 0) + 1
        if store == 'board': new['saved_at'] = rt.now()
        inverse = write(store, old, new, '撤销：' + entry['label'], undo_of=entry_id)
        return {'revision': revision + 1, 'undone': entry_id, 'entry': inverse}
