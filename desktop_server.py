import desktop_links as links
import desktop_navigation as navigation
import desktop_repository as repository
"""Loopback-only research desk. Navigation is restricted to registered local folders."""
import argparse, csv, http.server, json, mimetypes, os, pathlib, secrets, sqlite3, subprocess, sys, threading, urllib.parse, webbrowser
from contextlib import closing
import desktop_state
import desktop_runtime as runtime
import desktop_services as services
import desktop_contract as contract
from desktop_runtime import read_json as jread

HERE=runtime.DATA_DIR;ROOT=runtime.WORKSPACE_ROOT
WEB=runtime.APP_DIR/'desktop';PORT=8828;TOKEN=secrets.token_urlsafe(32);REFRESH=None;MUTEX=threading.Lock()
def connect():
    name=jread(HERE/'desktop_active.json',{}).get('db','');p=HERE/name
    if not name:return None
    if p.parent!=HERE or p.suffix!='.sqlite':raise ValueError('Invalid index')
    db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
def getrow(id):
    virtual=repository.project_location(id)
    if virtual:return virtual
    db=connect()
    if db is None:return None
    with closing(db) as db:r=db.execute('SELECT * FROM files WHERE id=?',(id,)).fetchone()
    return {**dict(r),'path':runtime.remap(r['path'],r['host'])} if r else None
def folder_target(r):
    if not r or r['host']!='local':raise ValueError('只支持已登记的本机目录')
    q=pathlib.Path(r['path']).resolve(strict=True);q=q if q.is_dir() else q.parent
    # Inputs can be on E/F; their exact registered parent is allowed, not arbitrary paths.
    return q
def refresh():
    global REFRESH
    command=runtime.refresh_args()
    if not command:raise ValueError('当前工作区未配置刷新程序')
    (HERE/'evidence').mkdir(exist_ok=True)
    with (HERE/'evidence/desktop_refresh.log').open('wb') as f:
        REFRESH=subprocess.Popen(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(b)
    def valid_host(self):return self.headers.get('Host') in {f'127.0.0.1:{PORT}',f'localhost:{PORT}'}
    def do_GET(self):
        if not self.valid_host():return self.send({'error':'Host rejected'},403)
        u=urllib.parse.urlsplit(self.path);a=urllib.parse.parse_qs(u.query);v=lambda k,d='':a.get(k,[d])[0]
        try:
            if u.path=='/api/openapi.json':return self.send(contract.openapi())
            if u.path=='/api/agent-guide':return self.file(runtime.APP_DIR/'AGENT_API.md')
            public=contract.route('get',u.path)
            if public:
                operation,args=public
                if operation=='projects_list':args['include_archived']=v('include_archived','false').lower()=='true'
                return self.send(services.execute(operation,args))
            if u.path=='/api/board-state':return self.send(desktop_state.read())
            if u.path=='/api/threads':return self.send(links.sources())
            if u.path=='/api/overview':
                data=repository.overview();data['token']=TOKEN;data['refresh_running']=bool(REFRESH and REFRESH.poll() is None);return self.send(data)
            if u.path=='/api/project-links':return self.send(links.project_links(v('project_id')))
            if u.path=='/api/projects':return self.send(repository.overrides())
            if u.path=='/api/files':
                if not repository.overview()['capabilities']['file_index']:return self.send({'rows':[],'total':0,'page':1,'pages':1})
                where=[];args=[]
                for key in ['project_id','category','host','bundle_id','object_type']:
                    if v(key):where.append(key+'=?');args.append(v(key))
                if v('q'):
                    where.append('(path LIKE ? ESCAPE "\\" OR current_version LIKE ? ESCAPE "\\")')
                    q=v('q').replace('\\','\\\\').replace('%','\\%').replace('_','\\_');args.extend(['%'+q+'%']*2)
                clause=' WHERE '+' AND '.join(where) if where else ''
                page=max(1,min(100000,int(v('page','1'))));size=50
                with closing(connect()) as db:
                    count=db.execute('SELECT count(*) FROM files'+clause,args).fetchone()[0]
                    rs=[{**dict(r),'path':runtime.remap(r['path'],r['host'])} for r in db.execute('SELECT * FROM files'+clause+' ORDER BY path LIMIT ? OFFSET ?',args+[size,(page-1)*size])]
                return self.send({'rows':rs,'total':count,'page':page,'pages':max(1,(count+size-1)//size)})
            if u.path=='/api/item':
                r=getrow(v('id'));return self.send(r or {'error':'未登记'},200 if r else 404)
            if u.path=='/api/folder':
                return self.send({'folder':str(folder_target(getrow(v('id'))))})
            if u.path=='/api/preview':
                r=getrow(v('id'))
                if not r or r['host']!='local':return self.send({'error':'只预览本地已登记文本'},400)
                p=pathlib.Path(r['path'])
                if p.suffix.lower() not in {'.md','.txt','.json','.tsv','.csv'}:return self.send({'error':'该格式请从所在目录打开'},400)
                with p.open('rb') as f:b=f.read(65537)
                return self.send({'path':str(p),'text':b[:65536].decode('utf-8-sig','replace'),'truncated':len(b)>65536})
            if u.path=='/api/refresh-status':return self.send({'running':bool(REFRESH and REFRESH.poll() is None),'exit_code':REFRESH.poll() if REFRESH else None,'status':jread(HERE/'refresh_status.json')})
            exports={'/export/files.tsv':HERE/'tables/unified_file_inventory.tsv','/export/summary.md':HERE/'UNIFIED_RESULTS.md'}
            if u.path in exports:return self.file(exports[u.path],download=True)
            if u.path in ['/', '/index.html']:return self.file(WEB/'index.html')
            if u.path in ['/style.css','/app.js','/board.css','/board.js','/details.js','/icon.svg']:return self.file(WEB/u.path.lstrip('/'))
            return self.send({'error':'Not found'},404)
        except services.NotFoundError as e:return self.send({'error':str(e)},404)
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as e:return self.send({'error':str(e)},400)
    def file(self,p,download=False):
        if not p.is_file():return self.send({'error':'此工作区未包含该导出文件'},404)
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(p.stat().st_size));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if download:self.send_header('Content-Disposition','attachment; filename="'+('unified_files.tsv' if p.suffix=='.tsv' else 'results_summary.md')+'"')
        self.end_headers()
        with p.open('rb') as f:
            while True:
                b=f.read(1024*1024)
                if not b:break
                self.wfile.write(b)
    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<=n<=2097152:return self.send({'error':'请求长度无效或请求过大'},400)
            # Consume a bounded body before a 403 response. Closing with unread request
            # bytes can reset the TCP connection on Windows and hide the JSON error.
            self.connection.settimeout(10)
            body=self.rfile.read(n)
            if not self.valid_host() or self.headers.get('X-Desk-Token')!=TOKEN or self.headers.get('Origin') not in {None,f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}:
                return self.send({'error':'请求来源不匹配'},403)
            obj=json.loads(body or b'{}')
            public=contract.route(self.command,urllib.parse.urlsplit(self.path).path)
            if public:
                operation,args=public
                return self.send(services.execute(operation,{**obj,**args}))
            if self.path=='/api/projects':
                result=services.web_save(obj)
                return self.send(result or {'error':'项目已被其他页面修改，请重新打开'},200 if result else 409)
            if self.path=='/api/project-links':
                result=links.save_project_links(obj)
                return self.send(result or {'error':'会话关联已变化，请重新打开'},200 if result else 409)
            if self.path=='/api/open-thread':
                target=links.linked_thread_target(obj.get('project_id',''),obj.get('thread_id',''))
                navigation.open_native(target);return self.send({'opened':target})
            if self.path=='/api/board-state':
                state=desktop_state.save(obj)
                return self.send(state if state else {'error':'另一个页面已修改桌面，请刷新后重试。'},200 if state else 409)
            if self.path=='/api/open-card':
                target=desktop_state.card_target(obj.get('id',''))
                navigation.open_native(target);return self.send({'opened':target})
            if self.path=='/api/open-folder':
                q=folder_target(getrow(obj.get('id','')))
                navigation.open_native(str(q));return self.send({'opened':str(q)})
            if self.path=='/api/refresh':
                with MUTEX:
                    if REFRESH and REFRESH.poll() is None:return self.send({'running':True},202)
                    refresh()
                return self.send({'running':True},202)
            return self.send({'error':'不支持此操作'},404)
        except services.ConflictError as e:return self.send({'error':str(e)},409)
        except services.NotFoundError as e:return self.send({'error':str(e)},404)
        except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError) as e:return self.send({'error':str(e)},400)

    do_PATCH=do_POST
    do_PUT=do_POST

if __name__=='__main__':
    runtime.configure_console()
    parser=argparse.ArgumentParser(description='AI4S工作台');parser.add_argument('--port',type=int);parser.add_argument('--config');parser.add_argument('--data-dir');parser.add_argument('--open',action='store_true');args=parser.parse_args()
    runtime.configure(args.config,args.data_dir);HERE=runtime.DATA_DIR;ROOT=runtime.WORKSPACE_ROOT;PORT=args.port or runtime.CONFIG.get('port',8828)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    if args.open:webbrowser.open(f'http://127.0.0.1:{PORT}')
    print(f'AI4S: http://127.0.0.1:{PORT}',flush=True);server.serve_forever()
