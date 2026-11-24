"""Versioned tool contracts; shared by MCP, HTTP and generated OpenAPI."""
import re

VERSION='1.1.0'
TEXT={'type':'string','maxLength':12000}
PID={'type':'string','pattern':r'^[a-zA-Z0-9_-]{1,80}$'}
REV={'type':'integer','minimum':0,'description':'先读取列表或项目返回的 revision；冲突后重新读取，不强行覆盖。'}
FIELDS={k:{**TEXT,'description':v} for k,v in {'name':'项目名称','summary':'研究问题与项目概述','status':'当前进度','current_version':'当前采用版本','scope':'结果适用范围与限制','todo':'待完成事项','local':'本地目录，支持工作区相对路径','remote':'服务器目录；不涉及服务器时留空','ssh_alias':'SSH 主机别名；不存放密码'}.items()}

def obj(props,required=()):return {'type':'object','properties':props,'required':list(required),'additionalProperties':False}
ADDRESS=obj({'id':PID,'label':{'type':'string','maxLength':200},'kind':{'type':'string','enum':['local','server','url']},'path':{'type':'string','maxLength':4096},'ssh_alias':{'type':'string','maxLength':200}},['id','kind','path'])
FIELDS['addresses']={'type':'array','items':ADDRESS,'maxItems':50,'description':'附加命名地址；省略保留现有列表，提供数组则整体替换，空数组清空。主local/remote字段保持兼容。'}
PROJECT=obj({'id':PID,**FIELDS},['name'])
PATCH=obj(FIELDS)
THREAD=obj({'id':{'type':'string','pattern':r'^[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$'},'title':TEXT,'provider':{'type':'string','enum':['codex']}},['id','title'])
TOOLS={
 'projects_list':('列出研究项目；可包含已归档项目。',obj({'include_archived':{'type':'boolean'}}),True),
 'project_get':('读取项目概述、地址、版本、关联会话和 revision。',obj({'project_id':PID},['project_id']),True),
 'project_create':('添加项目登记；不创建研究目录或启动分析。',obj({'project':PROJECT,'expected_revision':REV},['project','expected_revision']),False),
 'project_update':('局部修改项目字段；未提供的字段保留。',obj({'project_id':PID,'patch':PATCH,'expected_revision':REV},['project_id','patch','expected_revision']),False),
 'project_archive':('从活跃项目列表移出，可恢复；源文件、会话和卡片布局保留。',obj({'project_id':PID,'expected_revision':REV},['project_id','expected_revision']),False),
 'project_restore':('恢复归档的项目及其原有桌面卡片。',obj({'project_id':PID,'expected_revision':REV},['project_id','expected_revision']),False),
 'project_summarize':('汇总已登记研究内容、进度、版本、待办与来源时间；不重跑分析，不生成未经登记的科学结论。',obj({'project_id':PID},['project_id']),True),
 'project_threads_get':('读取项目会话关联及独立的关联 revision。',obj({'project_id':PID},['project_id']),True),
 'project_threads_set':('替换项目会话关联；不向会话发送消息。expected_revision 使用关联列表的 revision。',obj({'project_id':PID,'threads':{'type':'array','items':THREAD,'maxItems':100},'expected_revision':REV},['project_id','threads','expected_revision']),False),
 'workspace_status':('查看工作区路径、协议版本及可用功能。',obj({}),True)
}

RECORD={'type':'object','properties':{'id':PID,**FIELDS,'archived':{'type':'boolean'},'counts':{'type':'object','additionalProperties':{'type':'integer'}}},'required':['id','name'],'additionalProperties':True}
DETAIL=obj({'revision':REV,'project':RECORD,'threads':{'type':'array','items':THREAD}},['revision','project','threads'])
LINKS=obj({'revision':REV,'project_id':PID,'threads':{'type':'array','items':THREAD}},['revision','project_id','threads'])
OUTPUTS={
 'projects_list':obj({'revision':REV,'projects':{'type':'array','items':RECORD}},['revision','projects']),
 **{name:DETAIL for name in ['project_get','project_create','project_update','project_archive','project_restore']},
 **{name:LINKS for name in ['project_threads_get','project_threads_set']},
 'project_summarize':obj({**DETAIL['properties'],'summary':{'type':'string'},'basis':obj({'type':{'const':'registered_metadata'},'index_observed_at':{'type':'string'},'generated_at':{'type':'string'},'note':{'type':'string'}},['type','index_observed_at','generated_at','note']),'results':{'type':'array','items':{'type':'object'}}},['revision','project','threads','summary','basis','results']),
 'workspace_status':obj({'data_dir':{'type':'string'},'workspace_root':{'type':'string'},'capabilities':{'type':'object'},'schema_version':{'type':'integer'},'mcp_protocol':{'type':'string'},'project_revision':REV},['data_dir','workspace_root','capabilities','schema_version','mcp_protocol','project_revision'])
}

def validate(value,schema,label='arguments'):
    if 'enum' in schema and value not in schema['enum']:raise ValueError(label+' 不在允许值范围内')
    kind=schema.get('type')
    checks={'object':lambda:isinstance(value,dict),'array':lambda:isinstance(value,list),'string':lambda:isinstance(value,str),'integer':lambda:type(value) is int,'boolean':lambda:type(value) is bool}
    if kind in checks and not checks[kind]():raise ValueError(label+' 类型必须为 '+kind)
    if kind=='object':
        for key in schema.get('required',[]):
            if key not in value:raise ValueError(label+' 缺少字段 '+key)
        props=schema.get('properties',{})
        for key,v in value.items():
            if key not in props:
                if schema.get('additionalProperties') is False:raise ValueError(label+' 不支持字段 '+key)
            else:validate(v,props[key],label+'.'+key)
    if kind=='array':
        if len(value)>schema.get('maxItems',100000):raise ValueError(label+' 条目过多')
        for v in value:validate(v,schema['items'],label+'[]')
    if kind=='string':
        if len(value)>schema.get('maxLength',100000):raise ValueError(label+' 过长')
        if 'pattern' in schema and re.fullmatch(schema['pattern'],value) is None:raise ValueError(label+' 格式无效')
    if kind=='integer' and value<schema.get('minimum',value):raise ValueError(label+' 数值过小')

ROUTES=[
 ('get','/api/v1/projects','projects_list'),
 ('post','/api/v1/projects','project_create'),
 ('get','/api/v1/projects/{project_id}','project_get'),
 ('patch','/api/v1/projects/{project_id}','project_update'),
 ('post','/api/v1/projects/{project_id}/archive','project_archive'),
 ('post','/api/v1/projects/{project_id}/restore','project_restore'),
 ('get','/api/v1/projects/{project_id}/summary','project_summarize'),
 ('get','/api/v1/projects/{project_id}/threads','project_threads_get'),
 ('put','/api/v1/projects/{project_id}/threads','project_threads_set'),
 ('get','/api/v1/workspace','workspace_status')
]

def route(method,path):
    for verb,template,operation in ROUTES:
        m=re.fullmatch(re.escape(template).replace(r'\{project_id\}',r'(?P<project_id>[a-zA-Z0-9_-]+)'),path)
        if verb==method.lower() and m:return operation,m.groupdict()
    return None

def tool_definitions():
    return [{'name':name,'description':description,'inputSchema':schema,'outputSchema':OUTPUTS[name],'annotations':{'readOnlyHint':readonly,'destructiveHint':False,'idempotentHint':readonly,'openWorldHint':False}} for name,(description,schema,readonly) in TOOLS.items()]

def openapi():
    paths={}
    response={'description':'操作结果（包含 revision 的项目元数据）','content':{'application/json':{'schema':{'type':'object'}}}}
    for method,path,name in ROUTES:
        description,schema,readonly=TOOLS[name];parameters=[]
        body={**schema,'properties':dict(schema['properties']),'required':list(schema['required'])}
        if '{project_id}' in path:
            parameters.append({'in':'path','name':'project_id','required':True,'schema':PID});body['properties'].pop('project_id',None)
            body['required']=[x for x in body['required'] if x!='project_id']
        output=OUTPUTS[name]
        operation_response={'description':response['description'],'content':{'application/json':{'schema':output}}}
        entry={'operationId':name,'summary':description,'responses':{'200':operation_response,'400':{'description':'参数无效'},'403':{'description':'写入令牌或来源无效'},'404':{'description':'项目不存在'},'409':{'description':'revision 冲突，重新读取后再提交'}},'parameters':parameters,'security':[] if readonly else [{'DeskToken':[]}]}
        if method=='get':
            parameters += [{'in':'query','name':k,'schema':v,'required':False} for k,v in body['properties'].items()]
        else:entry['requestBody']={'required':True,'content':{'application/json':{'schema':body}}}
        paths.setdefault(path,{})[method]=entry
    paths['/api/overview']={'get':{'operationId':'getBootstrap','summary':'浏览器启动信息与当前进程的临时写入令牌 token','responses':{'200':response},'security':[]}}
    return {'openapi':'3.1.0','info':{'title':'AI4S Workspace API','version':VERSION,'description':'本机单用户研究项目管理。写入需要 X-Desk-Token；从 GET /api/overview 读取当前进程令牌。研究文件不会被修改。'},'servers':[{'url':'http://127.0.0.1:{port}','variables':{'port':{'default':'8828'}}}],'paths':paths,'components':{'securitySchemes':{'DeskToken':{'type':'apiKey','in':'header','name':'X-Desk-Token'}},'schemas':{'ProjectInput':PROJECT,'ProjectPatch':PATCH,'ProjectAddress':ADDRESS,'ThreadLink':THREAD,'ProjectRecord':{'type':'object','properties':{'id':PID,**FIELDS,'archived':{'type':'boolean'},'counts':{'type':'object','additionalProperties':{'type':'integer'}}},'required':['id','name'],'additionalProperties':True}}},'x-ai4s-mcp-protocol':'2025-11-25','x-ai4s-tool-contracts':tool_definitions()}
