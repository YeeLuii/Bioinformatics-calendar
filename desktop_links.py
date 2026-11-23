"""Codex chat registry and explicit project-to-chat associations."""
import re
import desktop_runtime as runtime
import desktop_repository as repository
from desktop_storage import read_json as jread
UUID=re.compile(r'^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$',re.I)

def sources():
    return jread(runtime.path('desktop_threads.json')) or {'threads':[]}

def project_links(project_id):
    if project_id not in {p['id'] for p in repository.overview(include_archived=True)['projects']}:raise ValueError('项目不存在')
    saved=jread(runtime.path('desktop_project_links.json'),{'revision':0,'projects':{}})
    return {'revision':saved['revision'],'project_id':project_id,'threads':saved['projects'].get(project_id,[])}

def save_project_links(obj):
    with runtime.workspace_lock():
        existing=project_links(obj.get('project_id',''))
        if obj.get('revision')!=existing['revision']:return None
        threads=obj.get('threads')
        if not isinstance(threads,list) or len(threads)>100:raise ValueError('会话列表无效')
        clean=[];seen=set()
        for t in threads:
            if not isinstance(t,dict) or not UUID.fullmatch(t.get('id','')) or not isinstance(t.get('title'),str) or len(t['title'])>12000:raise ValueError('会话 ID 或名称无效')
            if t['id'] in seen:continue
            seen.add(t['id']);clean.append({'id':t['id'],'title':t['title'],'provider':'codex'})
        saved=jread(runtime.path('desktop_project_links.json'),{'revision':0,'projects':{}})
        saved['revision']+=1;saved['projects'][obj['project_id']]=clean
        runtime.write_json(runtime.path('desktop_project_links.json'),saved)
        return project_links(obj['project_id'])

def linked_thread_target(project_id,thread_id):
    if not any(t['id']==thread_id for t in project_links(project_id)['threads']):raise ValueError('此会话未关联到项目')
    return 'codex://threads/'+thread_id
