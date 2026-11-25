import desktop_links as links
import desktop_repository as repository
"""Research-project use cases shared by HTTP, MCP and command-line clients."""
import uuid,copy,datetime,json
import desktop_runtime as rt
import desktop_state as state
from desktop_contract import TOOLS, FIELDS, validate
import desktop_tasks as tasks
import desktop_history as history
import desktop_diagnostics as diagnostics

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
    if name=='tasks_list':
        s=state.read();result=task_response(s)
        if id:result['tasks']=[t for t in result['tasks'] if t['project_id']==id]
        return result
    if name in {'task_create','task_update','task_remove','card_create','card_update','card_remove'}:return edit_board(name,args)
    if name=='cards_list':
        s=state.read();return {'revision':s['revision'],'cards':s['cards']}
    if name=='history_list':return history.listing()
    if name=='history_undo':return history.undo(args['entry_id'],args['expected_revision'])
    if name=='workspace_diagnostics':return diagnostics.inspect()
    if name=='path_mappings_preview':return diagnostics.preview(args['mappings'])
    if name=='path_mappings_set':return diagnostics.save(args['mappings'],args['expected_revision'])
    if name=='workspace_export':return export_workspace(args['format'],args.get('project_id'))
    if name=='projects_list':
        saved=repository.overrides()
        return {'revision':saved['revision'],'projects':repository.overview(args.get('include_archived',False),saved_projects=saved)['projects']}
    if name=='project_get':return get_project(id)
    if name=='project_create':
        p=dict(args['project']);p.setdefault('id','project-'+str(uuid.uuid4()))
        if any(x['id']==p['id'] for x in repository.overview(True)['projects']):
            existing=raw_project(p['id'])
            if all(existing.get(k)==v for k,v in p.items()):return get_project(p['id'])
            raise ConflictError('项目 ID 已存在且内容不同，请读取后更新')
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
    if name=='workspace_status':return {'data_dir':str(rt.DATA_DIR),'workspace_root':str(rt.WORKSPACE_ROOT),'capabilities':{**repository.overview()['capabilities'],'tasks':True,'gantt':True,'history':True,'diagnostics':True},'schema_version':1,'mcp_protocol':'2025-11-25','project_revision':repository.overrides()['revision']}


def task_response(s,id=None):
    result={'revision':s['revision'],'tasks':s['todos'],'warnings':tasks.warnings(s['todos'])}
    if id:result['task']=next(t for t in s['todos'] if t['id']==id)
    return result


def edit_board(name,args):
    is_task=name.startswith('task_');key='todos' if is_task else 'cards';kind='task' if is_task else 'card'
    action=name.split('_',1)[1]
    with rt.workspace_lock():
        old=state.read();new=copy.deepcopy(old)
        if action=='create':
            value=copy.deepcopy(args[kind]);value.setdefault('id',kind+'-'+uuid.uuid4().hex);id=value['id']
            existing=next((v for v in old[key] if v['id']==id),None)
            if existing:
                if all(existing.get(k)==v for k,v in value.items()):
                    return task_response(old,id) if is_task else {'revision':old['revision'],'cards':old['cards'],'card':existing}
                raise ConflictError('该 ID 已存在且内容不同，请读取后更新')
        else:
            id=args[kind+'_id'];existing=next((v for v in new[key] if v['id']==id),None)
            if existing is None:raise NotFoundError('任务或卡片不存在')
        if old['revision']!=args['expected_revision']:raise ConflictError('桌面 revision 冲突，请重新读取任务或卡片')
        if action=='create':
            if is_task:value=tasks.normalize(value,new['cards'])
            else:
                for k,v in [('target',''),('folder',''),('zone','inbox'),('x',0),('y',0)]:value.setdefault(k,v)
            new[key].append(value)
        elif action=='update':
            if is_task:
                replacement=tasks.normalize(args['patch'],new['cards'],existing)
                existing.clear();existing.update(replacement)
            else:
                patch=args['patch']
                if 'folder' in patch and patch['folder']!=existing['folder'] and 'order' not in patch:existing.pop('order',None)
                existing.update(patch)
        else:
            if is_task and any(id in t['dependencies'] for t in new['todos']):raise ValueError('其他任务仍依赖此任务，请先调整依赖关系')
            new[key]=[v for v in new[key] if v['id']!=id]
            if not is_task:
                for card in new['cards']:
                    if card['folder']==id:card.update(folder='',zone='inbox')
                for task in new['todos']:
                    if task['card']==id:task['card']=''
        saved=state.save_unlocked(new,old,{'create':'新增','update':'修改','remove':'移除'}[action]+('任务' if is_task else '卡片')+'：'+(value if action=='create' else existing).get('title',id))
        if is_task:return task_response(saved,id if action!='remove' else None)
        result={'revision':saved['revision'],'cards':saved['cards']}
        if action!='remove':result['card']=next(c for c in saved['cards'] if c['id']==id)
        return result


def export_workspace(format,project_id=None):
    with rt.workspace_lock():
        projects=repository.overview()['projects'];s=state.read()
    if project_id:
        projects=[p for p in projects if p['id']==project_id]
        if not projects:raise NotFoundError('活跃项目不存在')
        s['todos']=[t for t in s['todos'] if t['project_id']==project_id]
        s['cards']=[c for c in s['cards'] if c['type']=='project' and c['target']==project_id]
    if format=='json':
        content=json.dumps({'exported_at':rt.now(),'projects':projects,'cards':s['cards'],'tasks':s['todos']},ensure_ascii=False,indent=2)
    elif format=='markdown':
        cell=lambda s:str(s or '').replace('|','\\|').replace('\r',' ').replace('\n',' ')
        lines=['# 科研项目工作报告','', '整理时间：'+rt.now(),'','状态来自登记信息；运行成功不等于结果已复核。','', '| 项目 | 研究阶段/进度 | 运行状态 | 当前采用版本 | 下一步 |','|---|---|---|---|---|']
        for p in projects:lines.append('| '+' | '.join(cell(x) for x in [p['name'],p.get('research_stage') or p['status'],p.get('run_status','unknown'),p['current_version'],p['todo']])+' |')
        for p in projects:
            lines+=['','## '+cell(p['name']),'', '来源：'+cell(p.get('source')), '观察时间：'+cell(p.get('observed_at')), '复核时间：'+cell(p.get('reviewed_at'))]
            for version in p.get('result_versions',[]):lines.append('- '+cell(version.get('name'))+' / '+cell(version.get('version'))+'：'+cell(version.get('status'))+'；'+cell(version.get('scope')))
        lines+=['','## 计划任务','','| 任务 | 开始 | 截止 | 状态 |','|---|---|---|---|']
        for t in s['todos']:lines.append('| '+' | '.join(cell(t[k]) for k in ['title','start_date','date','status'])+' |')
        content='\n'.join(lines)+'\n'
    else:
        escape=lambda v:str(v).replace('\r\n','\n').replace('\r','\n').replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
        lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//AI4S//Research Tasks//ZH','CALSCALE:GREGORIAN']
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        for t in s['todos']:
            end=(tasks.date(t['date'])+datetime.timedelta(days=1)).strftime('%Y%m%d')
            lines+=['BEGIN:VEVENT','UID:'+escape(t['id'])+'@ai4s.local','DTSTAMP:'+stamp,'DTSTART;VALUE=DATE:'+t['start_date'].replace('-',''),'DTEND;VALUE=DATE:'+end,'SUMMARY:'+escape(t['title']),'DESCRIPTION:'+escape(t['status']+'\n'+t['notes']),'END:VEVENT']
        lines.append('END:VCALENDAR')
        # RFC 5545 folding counts UTF-8 octets without splitting a character.
        folded=[]
        for line in lines:
            part='';size=0
            for char in line:
                n=len(char.encode('utf-8'))
                if size+n>75:folded.append(part);part=' ';size=1
                part+=char;size+=n
            folded.append(part)
        content='\r\n'.join(folded)+'\r\n'
    return {'format':format,'filename':'ai4s-workspace.'+{'markdown':'md','ics':'ics','json':'json'}[format],'content':content}
