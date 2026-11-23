import desktop_links as links
import desktop_repository as repository
"""Private visual arrangements, independent of research files and Codex projects."""
import datetime, json, math, os, pathlib, re, threading
import desktop_runtime as runtime
from desktop_runtime import read_json as jread

def state_path():return runtime.path('desktop_board_state.json')
LOCK=threading.Lock()
ZONES={'inbox','do','plan','delegate','later'}
UUID=re.compile(r'^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$',re.I)

def initial():
    cards=[]
    for p in repository.overview()['projects']:
        cards.append(dict(id='p-'+p['id'],type='project',target=p['id'],title=p['name'],folder='',zone='inbox',x=0,y=0))
    for t in links.sources()['threads']:
        cards.append(dict(id='t-'+t['id'],type='thread',target=t['id'],title=t['title'],folder='',zone='inbox',x=0,y=0))
    return dict(revision=0,cards=cards,todos=[],saved_at=None)

def read():
    return jread(state_path()) if state_path().exists() else initial()

def validate(s):
    cards=s.get('cards');todos=s.get('todos')
    if not isinstance(cards,list) or not isinstance(todos,list) or len(cards)>1000 or len(todos)>3000:raise ValueError('卡片或待办数量无效')
    ids=set();projects={p['id'] for p in repository.overview(include_archived=True)['projects']}
    for c in cards:
        if not isinstance(c,dict):raise ValueError('卡片格式无效')
        for k in ['id','type','target','title','folder','zone']:
            if not isinstance(c.get(k),str):raise ValueError('卡片字段不完整')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',c['id']) or c['id'] in ids:raise ValueError('卡片标识重复或无效')
        ids.add(c['id'])
        if not 1<=len(c['title'].strip())<=12000:raise ValueError('请填写卡片标题')
        if c['type'] not in {'project','thread','folder','directory'} or c['zone'] not in ZONES:raise ValueError('卡片类型或区域无效')
        if c['type']=='thread' and not UUID.fullmatch(c['target']):raise ValueError('请填写正确的 Codex 会话 UUID')
        if c['type']=='project' and c['target'] not in projects:raise ValueError('项目未登记')
        if c['type']=='directory':
            if len(c['target'])>2048 or not (pathlib.PureWindowsPath(c['target']).is_absolute() or pathlib.PurePosixPath(c['target']).is_absolute()):raise ValueError('目录须使用绝对路径')
        for k in ['x','y']:
            n=c.get(k)
            if not isinstance(n,(int,float)) or not math.isfinite(n) or not 0<=n<=1:raise ValueError('卡片位置无效')
    folders={c['id'] for c in cards if c['type']=='folder'}
    for c in cards:
        if c['folder'] and (c['folder'] not in folders or c['type']=='folder'):raise ValueError('文件夹不能嵌套，卡片须属于现有文件夹')
    taskids=set()
    for t in todos:
        if not isinstance(t,dict) or not isinstance(t.get('id'),str) or t['id'] in taskids:raise ValueError('待办标识无效')
        taskids.add(t['id'])
        if not isinstance(t.get('title'),str) or not 1<=len(t['title'].strip())<=1000:raise ValueError('请填写待办标题（最多 1000 字）')
        if not isinstance(t.get('date'),str) or len(t['date'])!=10:raise ValueError('待办日期无效')
        datetime.date.fromisoformat(t['date'])
        if not isinstance(t.get('done'),bool) or (t.get('card') and t['card'] not in ids):raise ValueError('待办关联卡片无效')

def save(obj):
    with runtime.workspace_lock():
        STATE=state_path()
        old=read()
        if obj.get('revision')!=old['revision']:return None
        validate(obj)
        obj={k:obj[k] for k in ['cards','todos']}
        obj.update(revision=old['revision']+1,saved_at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
        tmp=STATE.with_suffix('.tmp')
        tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
        if STATE.exists():runtime.path('desktop_board_state.previous.json').write_bytes(STATE.read_bytes())
        os.replace(tmp,STATE)
        return obj

def card_target(id):
    c=next((c for c in read()['cards'] if c['id']==id),None)
    if not c:raise ValueError('卡片尚未保存')
    if c['type']=='thread':return 'codex://threads/'+c['target']
    if c['type']=='directory':
        p=runtime.local_path(c['target']).resolve(strict=True)
        if not p.is_dir():raise ValueError('目录不存在')
        return str(p)
    raise ValueError('此卡片没有直接打开目标')
