"""AI4S workspace configuration and data access. Standard library only."""
import datetime, hashlib, json, os, pathlib, subprocess, sys, threading
from desktop_storage import read_json, write_json, workspace_lock as storage_lock

APP_DIR=pathlib.Path(__file__).resolve().parent
DATA_DIR=APP_DIR
WORKSPACE_ROOT=APP_DIR.parent
CONFIG={}
WRITE_LOCK=threading.Lock()
CATEGORIES={'paper':'可用于文章的结果','exploratory':'探索性结果','intermediate':'中间文件','logs':'日志与审计','support':'输入、代码与参考','pending':'待判定 / 待复核'}

def workspace_lock():return storage_lock(DATA_DIR)

def configure_console():
    """Keep CLI output readable when redirected on non-Chinese Windows systems."""
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')

def configure(config_path=None,data_dir=None):
    global CONFIG,DATA_DIR,WORKSPACE_ROOT
    p=pathlib.Path(config_path).resolve() if config_path else APP_DIR/'workspace.json'
    CONFIG=read_json(p,{})
    if CONFIG.get('schema_version',1)!=1:raise ValueError('不支持的工作区配置版本')
    base=p.parent
    DATA_DIR=pathlib.Path(data_dir).resolve() if data_dir else (base/CONFIG.get('data_dir','.')).resolve()
    WORKSPACE_ROOT=(base/CONFIG.get('workspace_root','..')).resolve()
    if not DATA_DIR.is_dir():raise ValueError('数据目录不存在，请先使用 desktop_manage.py init 初始化')
    return CONFIG

def path(name):return DATA_DIR/name
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')

def remap(value,host='local'):
    if not value:return ''
    s=str(value).replace('\\','/')
    mappings=sorted(CONFIG.get('path_mappings',[]),key=lambda m:len(m['from']),reverse=True)
    for m in mappings:
        if m.get('host','local')!=host:continue
        old=m['from'].replace('\\','/').rstrip('/')
        a,b=(s.lower(),old.lower()) if host=='local' else (s,old)
        if a==b or a.startswith(b+'/'):return m['to'].replace('\\','/').rstrip('/')+s[len(old):]
    return s

def local_path(value):
    v=remap(value)
    # Preserve foreign absolute paths as missing, rather than anchoring them under a new workspace.
    if len(v)>2 and v[1]==':' and os.name!='nt':return pathlib.Path(v)
    p=pathlib.Path(v)
    return p if p.is_absolute() else WORKSPACE_ROOT/p

def refresh_args():
    substitutions={'python':sys.executable,'data_dir':str(DATA_DIR),'workspace_root':str(WORKSPACE_ROOT),'app_dir':str(APP_DIR)}
    return [s.format(**substitutions) for s in CONFIG.get('refresh_command',[])]
