"""Project catalog projection and editable metadata repository."""
import pathlib
import desktop_addresses as addresses
import desktop_runtime as rt
from desktop_storage import read_json, write_json
path=rt.path
remap=rt.remap
local_path=rt.local_path
workspace_lock=rt.workspace_lock
CATEGORIES=rt.CATEGORIES

def overrides():return read_json(path('desktop_projects.json'),{'schema_version':1,'revision':0,'projects':[]})

def overview(include_archived=False, saved_projects=None):
    source=read_json(path('desktop_data.json'),{})
    data={**source}
    projects={p['id']:dict(p) for p in source.get('projects',[])}
    for p in (overrides() if saved_projects is None else saved_projects)['projects']:projects[p['id']]={**projects.get(p['id'],{}),**p}
    for p in projects.values():
        for k in ['summary','status','current_version','scope','todo','local','remote']:p.setdefault(k,'')
        p.setdefault('counts',{});p.setdefault('name',p['id'])
        p.setdefault('addresses',[])
        p['ssh_alias']=p.get('ssh_alias') or rt.CONFIG.get('ssh_alias','')
        p['local']=str(local_path(p['local'])) if p['local'] else ''
        p['remote']=remap(p['remote'],'server')
        p['local_id']='project:'+p['id']+':local' if p['local'] else ''
        p['remote_id']='project:'+p['id']+':server' if p['remote'] else ''
    data['projects']=[p for p in projects.values() if include_archived or not p.get('archived',False)]
    data.setdefault('bundles',[])
    data['bundles']=[b for b in data['bundles'] if include_archived or not projects.get(b['project_id'],{}).get('archived',False)]
    for b in data['bundles']:
        b['locations']=[{**r,'path':remap(r['path'],r['host'])} for r in b.get('locations',[])]
        b['remote']=[remap(p,'server') for p in b.get('remote',[])]
    for k,v in {'updated_at':'','counts':{},'categories':CATEGORIES,'stale_bundles':[],'local_files':0,'server_entries':0,'remote_status':'not_configured'}.items():data.setdefault(k,v)
    pointer=read_json(path('desktop_active.json'),{})
    data['workspace']={'name':rt.CONFIG.get('name','AI4S工作台'),'ssh_alias':rt.CONFIG.get('ssh_alias','')}
    data['capabilities']={'file_index':bool(pointer.get('db') and (rt.DATA_DIR/pointer['db']).is_file()),'refresh':bool(rt.CONFIG.get('refresh_command')),'project_edit':True,'chat_provider':'codex','export_files':path('tables/unified_file_inventory.tsv').is_file(),'export_summary':path('UNIFIED_RESULTS.md').is_file()}
    return data

def project_location(id):
    for p in overview()['projects']:
        for entry in addresses.clean_addresses(p['addresses']):
            if id=='project:'+p['id']+':address:'+entry['id']:
                return addresses.location(p,entry)
        for host,key in [('local','local'),('server','remote')]:
            if p.get(key+'_id' if key=='local' else 'remote_id')!=id:continue
            value=p[key]
            return dict(id=id,path=value,host=host,project_id=p['id'],object_type='directory',availability=('available' if pathlib.Path(value).is_dir() else 'missing_at_path') if host=='local' else 'unverified',ssh_alias=p['ssh_alias'])
    return None

def save_project(obj):
    with workspace_lock():
        current=overrides()
        if obj.get('revision')!=current['revision']:return None
        p=obj.get('project',{})
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',p.get('id','')):raise ValueError('项目 ID 只能包含字母、数字、连字符和下划线')
        allowed=['id','name','summary','status','current_version','scope','todo','local','remote','ssh_alias']
        clean={k:p.get(k,'').strip() for k in allowed if isinstance(p.get(k,''),str)}
        if len(clean)!=len(allowed) or not clean['name'] or any(len(v)>12000 for v in clean.values()):raise ValueError('项目内容无效')
        if clean['ssh_alias'] and (clean['ssh_alias'].startswith('-') or not re.fullmatch(r'[\w.@:-]+',clean['ssh_alias'])):raise ValueError('SSH 别名无效')
        clean['addresses']=addresses.clean_addresses(p.get('addresses',[]))
        if 'archived' in p:
            if not isinstance(p['archived'],bool):raise ValueError('归档状态必须为布尔值')
            clean['archived']=p['archived']
        entries={p['id']:p for p in current['projects']};entries[clean['id']]=clean
        result=dict(schema_version=1,revision=current['revision']+1,projects=list(entries.values()))
        write_json(path('desktop_projects.json'),result);return result
