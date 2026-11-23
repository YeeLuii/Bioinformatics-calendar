import desktop_links as links
import desktop_repository as repository
"""Research-project use cases shared by HTTP, MCP and command-line clients."""
import uuid
import desktop_runtime as rt
import desktop_state as state
from desktop_contract import TOOLS, FIELDS, validate

class ConflictError(ValueError):pass
class NotFoundError(ValueError):pass

def get_project(id):
    saved=repository.overrides()
    p=next((p for p in repository.overview(include_archived=True,saved_projects=saved)['projects'] if p['id']==id),None)
    if not p:raise NotFoundError('项目不存在：'+id)
    return {'revision':saved['revision'],'project':p,'threads':links.project_links(id)['threads']}

def raw_project(id):
    source=rt.read_json(rt.path('desktop_data.json'),{})
    p=next((dict(p) for p in source.get('projects',[]) if p['id']==id),{})
    p.update(next((p for p in repository.overrides()['projects'] if p['id']==id),{}))
    if not p:raise NotFoundError('项目不存在：'+id)
    return p

def store(p,revision):
    result=repository.save_project({'project':p,'revision':revision})
    if result is None:raise ConflictError('revision 冲突，请重新读取项目')
    return get_project(p['id'])

def web_save(obj):
    p=obj.get('project',{});id=p.get('id','')
    exists=any(x['id']==id for x in repository.overview(include_archived=True)['projects'])
    if exists:return execute('project_update',{'project_id':id,'patch':{k:v for k,v in p.items() if k!='id'},'expected_revision':obj.get('revision')})
    return execute('project_create',{'project':p,'expected_revision':obj.get('revision')})

def execute(name,args):
    if name not in TOOLS:raise ValueError('未知操作：'+name)
    validate(args,TOOLS[name][1])
    id=args.get('project_id')
    if name=='projects_list':
        saved=repository.overrides()
        return {'revision':saved['revision'],'projects':repository.overview(args.get('include_archived',False),saved_projects=saved)['projects']}
    if name=='project_get':return get_project(id)
    if name=='project_create':
        p=dict(args['project']);p.setdefault('id','project-'+str(uuid.uuid4()))
        if any(x['id']==p['id'] for x in repository.overview(True)['projects']):raise ValueError('项目 ID 已存在')
        return store(p,args['expected_revision'])
    if name=='project_update':
        p=raw_project(id);p.update(args['patch']);return store(p,args['expected_revision'])
    if name in {'project_archive','project_restore'}:
        p=raw_project(id);p['archived']=name=='project_archive';return store(p,args['expected_revision'])
    if name=='project_threads_get':return links.project_links(id)
    if name=='project_threads_set':
        result=links.save_project_links({'project_id':id,'revision':args['expected_revision'],'threads':args['threads']})
        if result is None:raise ConflictError('关联 revision 冲突，请重新读取关联会话')
        return result
    if name=='project_summarize':
        result=get_project(id);p=result['project'];d=repository.overview(True)
        result.update(summary='\n'.join(f'{label}：{p.get(k)}' for k,label in [('name','项目'),('summary','研究内容'),('status','进度'),('current_version','采用版本'),('scope','适用范围'),('todo','待完成事项')] if p.get(k)),basis={'type':'registered_metadata','index_observed_at':d.get('updated_at',''),'generated_at':rt.now(),'note':'汇总已登记信息，未重新读取研究结果或验证科学结论。'},results=[{'id':b['id'],'name':b['name'],'category':b['category'],'scope':b['scope'],'current_version':b['current_version']} for b in d['bundles'] if b['project_id']==id])
        return result
    if name=='workspace_status':return {'data_dir':str(rt.DATA_DIR),'workspace_root':str(rt.WORKSPACE_ROOT),'capabilities':repository.overview()['capabilities'],'schema_version':1,'mcp_protocol':'2025-11-25','project_revision':repository.overrides()['revision']}
