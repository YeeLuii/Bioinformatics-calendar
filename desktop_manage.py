"""Initialize or package an AI4S workspace without research files or dependencies."""
import argparse, json, pathlib, zipfile, sys
import desktop_runtime as rt

CODE=['desktop_server.py','desktop_runtime.py','desktop_state.py','desktop_manage.py','desktop_storage.py','desktop_repository.py','desktop_addresses.py','desktop_navigation.py','desktop_links.py','desktop_services.py','desktop_contract.py','desktop_mcp.py','deploy.py','deploy_codex.py','deploy.ps1','deploy.sh']
CODE+=['desktop_tasks.py','desktop_history.py','desktop_diagnostics.py']
WEB=['index.html','style.css','board.css','app.js','board.js','details.js','icon.svg']
WEB+=['tasks.js','gantt.js','workspace.js','workspace.css']
DATA=['desktop_data.json','desktop_projects.json','desktop_project_links.json','desktop_threads.json','desktop_board_state.json']

def init(dest):
    dest=pathlib.Path(dest).resolve()
    if (dest/'workspace.json').exists():raise ValueError('工作区已经存在，不覆盖配置')
    (dest/'data').mkdir(parents=True,exist_ok=True)
    rt.write_json(dest/'workspace.json',dict(schema_version=1,name='AI4S工作台',data_dir='data',workspace_root='.',port=8828,ssh_alias='',path_mappings=[],refresh_command=[]))
    rt.write_json(dest/'data/desktop_projects.json',dict(schema_version=1,revision=0,projects=[]))
    print(str(dest/'workspace.json'))

def pack(output,include_index=False):
    target=pathlib.Path(output).resolve()
    if target.exists():raise ValueError('输出文件已存在，请使用新文件名')
    target.parent.mkdir(parents=True,exist_ok=True)
    cfg={**rt.CONFIG,'data_dir':'data','workspace_root':'.','refresh_command':[]}
    cfg['schema_version']=1;cfg['name']='AI4S工作台'
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in CODE:z.write(rt.APP_DIR/name,name)
        for name in WEB:z.write(rt.APP_DIR/'desktop'/name,'desktop/'+name)
        z.writestr('workspace.json',json.dumps(cfg,ensure_ascii=False,indent=2))
        for name in DATA:
            p=rt.path(name)
            if p.is_file():z.write(p,'data/'+name)
        if not rt.path('desktop_projects.json').exists():z.writestr('data/desktop_projects.json',json.dumps({'schema_version':1,'revision':0,'projects':[]}))
        if include_index:
            ptr=rt.read_json(rt.path('desktop_active.json'),{})
            name=ptr.get('db','')
            if not name or pathlib.Path(name).name!=name:raise ValueError('没有可打包的有效索引')
            z.write(rt.path(name),'data/'+name);z.write(rt.path('desktop_active.json'),'data/desktop_active.json')
            for name in ['tables/unified_file_inventory.tsv','UNIFIED_RESULTS.md']:
                if rt.path(name).is_file():z.write(rt.path(name),'data/'+name)
        z.writestr('start.cmd','@echo off\r\ncd /d "%~dp0"\r\npowershell -NoProfile -ExecutionPolicy Bypass -File ".\\deploy.ps1" --mcp off\r\n')
        z.writestr('README.md',HELP)
        if (rt.APP_DIR/'AI4S_ARCHITECTURE.md').is_file():z.write(rt.APP_DIR/'AI4S_ARCHITECTURE.md','ARCHITECTURE.md')
        for name in ['AGENT_API.md','openapi.json']:
            if (rt.APP_DIR/name).is_file():z.write(rt.APP_DIR/name,name)
        for name in ['docs/API.md','docs/DATA_MODEL.md','docs/USAGE.md','docs/DEPLOYMENT.md','examples/http_client.py','examples/create_demo.py','examples/export_openapi.py','examples/import_run_snapshot.py']:
            if (rt.APP_DIR/name).is_file():z.write(rt.APP_DIR/name,name)
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'includes_file_index':include_index},ensure_ascii=False))

HELP='''# AI4S工作台

需要 Python >=3.9,<4.0，无需 pip、Node.js 或数据库服务。自动复用已有解释器，不下载 Python。

解压后运行：
```
python -B deploy.py --mcp off
```
Windows 也可双击 start.cmd；macOS/Linux 可运行 sh ./deploy.sh --mcp off。
只监听本机 127.0.0.1，实际地址见脚本输出。启停与 Codex 注册见 docs/DEPLOYMENT.md。

默认轻量包包含程序、项目资料、会话关联和个人安排，不包含科研数据或逐文件索引。
原目录地址保留为引用。换电脑后在 workspace.json 的 path_mappings 中填写旧根目录和新根目录：
```json
{"host":"local","from":"D:/old/project","to":"E:/new/project"}
```
服务器地址可以同样设置 host=server。SSH 别名在 workspace.json 或项目编辑页配置。
不搬动研究文件；映射只改变导航。Codex 会话要求目标电脑安装并登录可访问该会话的 Codex。

新工作区：python desktop_manage.py init ../new-workspace
然后：python desktop_server.py --config ../new-workspace/workspace.json --open
进入页面点击“新建项目”，填写概述和本地／服务器地址，并关联会话。

核心代码与 data/ 分开保存；迁移 data/ 和 workspace.json 即可保留项目、会话关联及布局。
打包会关闭源项目的刷新命令，避免在新电脑误调用旧分析适配器。需要时显式重新配置。
完整文件查询需要打包时添加 --include-index，会显著增大文件体积。

MCP 独立运行，无需先启动网页：
python -B desktop_mcp.py --config workspace.json
为本机生成 MCP 客户端配置：
python desktop_manage.py mcp-config --config workspace.json
Codex 使用部署脚本的 --mcp required 参数，通过官方 CLI 注册；不要手工追加 TOML。
JSON 输出供其他兼容客户端配置使用；不要手动向 MCP 进程的 stdout 写入日志。
机器可读接口见 openapi.json，Agent 使用说明见 AGENT_API.md。
完整接口说明见 docs/API.md，使用示例见 docs/USAGE.md。
个人迁移包包含项目资料和会话关联；公开分享前应另建虚构演示工作区。
'''

def mcp_config(config_path,format='json'):
    p=pathlib.Path(config_path or rt.APP_DIR/'workspace.json').resolve()
    args=['-B',str(rt.APP_DIR/'desktop_mcp.py'),'--config',str(p)]
    if format=='json':print(json.dumps({'mcpServers':{'ai4s':{'command':sys.executable,'args':args}}},ensure_ascii=False,indent=2))
    else:print('[mcp_servers.ai4s]\ncommand = '+json.dumps(sys.executable)+'\nargs = '+json.dumps(args,ensure_ascii=False))

if __name__=='__main__':
    rt.configure_console()
    parser=argparse.ArgumentParser(description='AI4S工作区工具')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('init');p.add_argument('directory')
    p=sub.add_parser('pack');p.add_argument('--config');p.add_argument('--output',required=True);p.add_argument('--include-index',action='store_true')
    p=sub.add_parser('mcp-config');p.add_argument('--config');p.add_argument('--format',choices=['json','codex'],default='json')
    args=parser.parse_args()
    if args.command=='init':init(args.directory)
    elif args.command=='mcp-config':mcp_config(args.config,args.format)
    else:rt.configure(args.config);pack(args.output,args.include_index)
