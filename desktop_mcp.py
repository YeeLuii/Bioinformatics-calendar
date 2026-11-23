"""AI4S MCP stdio adapter. No HTTP server or third-party runtime required."""
import argparse, json, sys
import desktop_contract as contract
import desktop_runtime as rt
import desktop_services as services

SUPPORTED=('2025-11-25','2025-06-18','2025-03-26','2024-11-05')
LIMIT=2*1024*1024

class ProtocolError(Exception):
    def __init__(self,code,message):self.code=code;self.message=message

class Session:
    def __init__(self):self.negotiated=False;self.ready=False;self.version=SUPPORTED[0]
    def dispatch(self,method,params):
        if not isinstance(params,dict):raise ProtocolError(-32602,'params must be an object')
        if method=='initialize':
            if not all(k in params for k in ['protocolVersion','capabilities','clientInfo']):raise ProtocolError(-32602,'Missing initialize fields')
            self.version=params['protocolVersion'] if params['protocolVersion'] in SUPPORTED else SUPPORTED[0]
            self.negotiated=True
            return {'protocolVersion':self.version,'capabilities':{'tools':{'listChanged':False},'resources':{'subscribe':False,'listChanged':False}},'serverInfo':{'name':'ai4s-workbench','version':contract.VERSION},'instructions':'Manage research-project metadata in this workspace. Read revision before mutations. Archive is reversible; research files and real chats are never deleted. project_summarize summarizes registered metadata only. Read ai4s://docs/agent for workflow and limits.'}
        if method=='ping':return {}
        if not self.negotiated:raise ProtocolError(-32002,'Initialize first')
        if method=='notifications/initialized':self.ready=True;return None
        if method.startswith('notifications/'):return None
        if not self.ready:raise ProtocolError(-32002,'Send notifications/initialized first')
        if method=='tools/list':
            definitions=contract.tool_definitions()
            if self.version not in {'2025-11-25','2025-06-18'}:
                for tool in definitions:tool.pop('outputSchema',None)
            return {'tools':definitions}
        if method=='tools/call':
            name=params.get('name')
            if name not in contract.TOOLS:raise ProtocolError(-32602,'Unknown tool')
            try:
                result=services.execute(name,params.get('arguments',{}))
                response={'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],'isError':False}
                if self.version in {'2025-11-25','2025-06-18'}:response['structuredContent']=result
                return response
            except (ValueError,OSError,TypeError) as e:
                code='revision_conflict' if isinstance(e,services.ConflictError) else 'not_found' if isinstance(e,services.NotFoundError) else 'invalid_request'
                return {'content':[{'type':'text','text':json.dumps({'error':code,'message':str(e)},ensure_ascii=False)}],'isError':True}
        if method=='resources/list':return {'resources':[{'uri':'ai4s://docs/openapi','name':'openapi','mimeType':'application/json','description':'AI4S OpenAPI 3.1 and tool input schemas'},{'uri':'ai4s://docs/agent','name':'agent-guide','mimeType':'text/markdown','description':'Agent workflow, revisions and operation boundaries'}]}
        if method=='resources/read':
            uri=params.get('uri')
            if uri=='ai4s://docs/openapi':text=json.dumps(contract.openapi(),ensure_ascii=False);mime='application/json'
            elif uri=='ai4s://docs/agent':text=(rt.APP_DIR/'AGENT_API.md').read_text(encoding='utf-8');mime='text/markdown'
            else:raise ProtocolError(-32002,'Unknown resource')
            return {'contents':[{'uri':uri,'mimeType':mime,'text':text}]}
        raise ProtocolError(-32601,'Method not found')

def run(stdin,stdout):
    session=Session()
    while True:
        raw=stdin.readline(LIMIT+1)
        if not raw:break
        request=None;id=None
        try:
            if len(raw)>LIMIT:
                while raw and not raw.endswith(b'\n'):raw=stdin.readline(LIMIT+1)
                raise ProtocolError(-32600,'Message too large')
            try:request=json.loads(raw.decode('utf-8'))
            except (UnicodeError,ValueError):raise ProtocolError(-32700,'Invalid JSON')
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0' or not isinstance(request.get('method'),str):raise ProtocolError(-32600,'Invalid JSON-RPC request')
            id=request.get('id')
            if id is not None and type(id) not in (int,str):raise ProtocolError(-32600,'Invalid request id')
            result=session.dispatch(request['method'],request.get('params',{}))
            if 'id' not in request:continue
            response={'jsonrpc':'2.0','id':id,'result':result}
        except ProtocolError as e:
            if isinstance(request,dict) and 'id' not in request:continue
            response={'jsonrpc':'2.0','id':id,'error':{'code':e.code,'message':e.message}}
        except Exception as e:
            print('AI4S MCP: '+str(e),file=sys.stderr)
            if isinstance(request,dict) and 'id' not in request:continue
            response={'jsonrpc':'2.0','id':id,'error':{'code':-32603,'message':'Internal error; see stderr'}}
        stdout.write((json.dumps(response,ensure_ascii=False)+'\n').encode('utf-8'));stdout.flush()

if __name__=='__main__':
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='AI4S MCP stdio server');parser.add_argument('--config');parser.add_argument('--data-dir');args=parser.parse_args()
    rt.configure(args.config,args.data_dir);run(sys.stdin.buffer,sys.stdout.buffer)
