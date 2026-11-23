"""Deterministic local deployment. Python >=3.9,<4.0; no third-party packages."""
import argparse
import contextlib
import io
import http.client
import json
import os
import pathlib
import platform
import socket
import subprocess
import sys
import time
import uuid
import webbrowser

import desktop_manage as manage
import desktop_runtime as rt
from desktop_storage import workspace_lock, write_json, read_json
from deploy_codex import DeploymentError, register

APP = pathlib.Path(__file__).resolve().parent


def check_environment():
    if not (3, 9) <= sys.version_info[:2] < (4, 0):
        raise DeploymentError('Python >=3.9,<4.0 is required; use an existing compatible interpreter.')
    try:
        import sqlite3, ssl, http.server, ctypes
        with sqlite3.connect(':memory:') as db:
            db.execute('select 1').fetchone()
    except ImportError as error:
        raise DeploymentError('Required standard-library module is missing: ' + error.name) from error
    return {'system': platform.system(), 'architecture': platform.machine(),
            'python': sys.version.split()[0], 'interpreter': sys.executable,
            'supported_python': '>=3.9,<4.0'}


def request(port, path, body=None, token=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Desk-Token'] = token
        connection.request('POST' if body is not None else 'GET', path,
                           body=None if body is None else json.dumps(body).encode('utf8'), headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise DeploymentError('Local service returned HTTP ' + str(response.status))
        return json.loads(response.read())
    finally:
        connection.close()


def health(port):
    try:
        result = request(port, '/api/deploy-health')
        return result if result.get('application') == 'ai4s-workbench' else None
    except (OSError, ValueError, DeploymentError, http.client.HTTPException):
        return None


def same_workspace(info):
    return bool(info and info.get('data_dir') and info.get('app_dir')
                and pathlib.Path(info['data_dir']).resolve() == rt.DATA_DIR
                and pathlib.Path(info['app_dir']).resolve() == APP)


def free_port(preferred):
    if not 1 <= preferred <= 65535:
        raise DeploymentError('Port must be between 1 and 65535.')
    for port in range(preferred, min(preferred + 100, 65536)):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise DeploymentError('No free local port found in the next 100 ports.')


def mcp_check(config):
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'ai4s-deploy', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'workspace_status', 'arguments': {}}}
    ]
    result = subprocess.run([sys.executable, '-B', str(APP / 'desktop_mcp.py'), '--config', str(config)],
        input=''.join(json.dumps(m) + '\n' for m in messages).encode(), capture_output=True,
        timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise DeploymentError('MCP process failed its startup check; no Codex configuration was changed.')
    replies = {r['id']: r for r in map(json.loads, result.stdout.decode('utf8').splitlines())}
    if replies.get(3, {}).get('result', {}).get('isError', True):
        raise DeploymentError('MCP workspace check failed.')
    count = len(replies.get(2, {}).get('result', {}).get('tools', []))
    if count != 10:
        raise DeploymentError('Unexpected MCP tool inventory.')
    return count


def stop_owned(state):
    info = health(state.get('port', 0))
    if not info:
        return {'status': 'not_running'}
    if not same_workspace(info) or not state.get('deployment_id') or info.get('deployment_id') != state['deployment_id']:
        raise DeploymentError('This service is not owned by this deployment record; it was not stopped.')
    if request(state['port'], '/api/overview').get('refresh_running'):
        raise DeploymentError('A refresh is running; finish it before stopping this service.')
    token = request(state['port'], '/api/overview')['token']
    request(state['port'], '/api/deploy-stop', {'deployment_id': state['deployment_id']}, token)
    for _ in range(40):
        if not health(state['port']):
            return {'status': 'stopped'}
        time.sleep(.1)
    raise DeploymentError('Service did not stop within the expected time.')


def start(config, preferred, state):
    for port in dict.fromkeys([state.get('port', preferred), preferred]):
        info = health(port)
        if same_workspace(info):
            return {'port': port, 'pid': info['pid'], 'deployment_id': info['deployment_id'], 'reused': True}
    port = free_port(preferred)
    instance = uuid.uuid4().hex
    logs = rt.DATA_DIR / '.deployment'
    logs.mkdir(exist_ok=True)
    kwargs = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)} if os.name == 'nt' else {'start_new_session': True}
    with (logs / 'server.log').open('ab') as output:
        process = subprocess.Popen([sys.executable, '-B', str(APP / 'desktop_server.py'),
            '--config', str(config), '--port', str(port), '--deployment-id', instance],
            cwd=APP, stdin=subprocess.DEVNULL, stdout=output, stderr=output, **kwargs)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            info = health(port)
            if same_workspace(info) and info.get('deployment_id') == instance:
                return {'port': port, 'pid': process.pid, 'deployment_id': instance, 'reused': False}
            time.sleep(.1)
        raise DeploymentError('HTTP startup failed; see ' + str(logs / 'server.log'))
    except Exception:
        if process.poll() is None:
            process.terminate()  # Only the child just created by this call.
            process.wait(timeout=10)
        raise


def deploy(args):
    environment = check_environment()
    if args.config:
        config = pathlib.Path(args.config).resolve()
        if not config.is_file():
            raise DeploymentError('--config must refer to an existing workspace.json.')
    elif not args.workspace and (APP / 'workspace.json').is_file():
        config = APP / 'workspace.json'
    else:
        workspace = pathlib.Path(args.workspace).resolve() if args.workspace else APP.parent / 'ai4s-workspace'
        config = workspace / 'workspace.json'
        if not config.exists():
            if args.action != 'start':
                raise DeploymentError('Workspace does not exist.')
            if workspace.exists() and any(workspace.iterdir()):
                raise DeploymentError('Destination is nonempty and is not an AI4S workspace. Choose --workspace explicitly.')
            with contextlib.redirect_stdout(io.StringIO()):
                manage.init(workspace)
    rt.configure(config)
    preferred = args.port if args.port is not None else rt.CONFIG.get('port', 8828)
    if not isinstance(preferred, int) or not 1 <= preferred <= 65535:
        raise DeploymentError('Port must be between 1 and 65535.')
    private = rt.DATA_DIR / '.deployment'
    private.mkdir(exist_ok=True)
    if os.name != 'nt':
        private.chmod(0o700)
    with workspace_lock(private):
        state_path = private / 'state.json'
        state = read_json(state_path, {})
        if args.action == 'stop':
            result = stop_owned(state)
            return {**result, 'workspace': str(config)}
        if args.action == 'status':
            info = health(state.get('port', rt.CONFIG.get('port', 8828)))
            return {'status': 'running' if same_workspace(info) else 'not_running',
                    'workspace': str(config), 'service': info if same_workspace(info) else None}
        tools = mcp_check(config)
        registration = register(pathlib.Path(sys.executable).resolve(), APP / 'desktop_mcp.py', config,
                                args.mcp, args.codex, args.replace_mcp)
        if args.restart:
            stop_owned(state)
        service = start(config, preferred, state)
        url = 'http://127.0.0.1:' + str(service['port'])
        result = {**service, 'status': 'ready', 'url': url, 'workspace': str(config),
                  'environment': environment, 'mcp_tools': tools, 'mcp_registration': registration,
                  'source_sync': 'not_performed; ask the user for source scope after deployment'}
        write_json(state_path, result)
        if not args.no_open:
            webbrowser.open(url)
        return result


def main():
    rt.configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=['start', 'status', 'stop'], default='start')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--workspace')
    group.add_argument('--config')
    parser.add_argument('--port', type=int)
    parser.add_argument('--mcp', choices=['auto', 'required', 'off'], default='auto')
    parser.add_argument('--codex', help='Path to Codex executable (or npm launcher with resolvable Node entry point)')
    parser.add_argument('--replace-mcp', action='store_true')
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(deploy(args), ensure_ascii=False, indent=2))
    except (DeploymentError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
