"""Exercise the actual HTTP adapter in an isolated workspace."""
import json
import http.client
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import desktop_contract as contract
import desktop_manage as manage
import desktop_runtime as rt


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai4s-http-')
        self.root = pathlib.Path(self.temp.name)
        manage.init(self.root / 'workspace')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.base = 'http://127.0.0.1:' + str(self.port)
        self.process = subprocess.Popen([
            sys.executable, '-B', str(rt.APP_DIR / 'desktop_server.py'),
            '--config', str(self.root / 'workspace/workspace.json'), '--port', str(self.port)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 10
        try:
            while True:
                try:
                    self.token = self.call('/api/overview')[1]['token']
                    break
                except (OSError, TimeoutError):
                    if self.process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('HTTP test server failed to start')
                    time.sleep(.05)
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.communicate(timeout=10)
        self.temp.cleanup()

    def tearDown(self):
        self.stop()

    def call(self, path, method='GET', body=None, headers=None):
        data = None if body is None else json.dumps(body).encode('utf8')
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            connection.request(method, path, body=data,
                               headers={'Content-Type': 'application/json', **(headers or {})})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_project_lifecycle_auth_and_board_revision(self):
        auth = {'X-Desk-Token': self.token}
        payload = {'expected_revision': 0, 'project': {'id': 'study', 'name': '研究项目', 'local': '.'}}
        self.assertEqual(self.call('/api/v1/projects', 'POST', payload)[0], 403)
        self.assertEqual(self.call('/api/v1/projects', headers={'Host': 'untrusted.example'})[0], 403)
        self.assertEqual(self.call('/api/v1/projects', 'POST', payload, {**auth, 'Origin': 'https://untrusted.example'})[0], 403)
        code, result = self.call('/api/v1/projects', 'POST', payload, auth)
        self.assertEqual(code, 200)
        contract.validate(result, contract.OUTPUTS['project_create'])
        self.assertEqual(self.call('/api/v1/projects/study', 'PATCH', {'patch': {'status': '已复核'}, 'expected_revision': 1}, auth)[0], 200)
        self.assertEqual(self.call('/api/v1/projects/study', 'PATCH', {'patch': {'status': '过期写入'}, 'expected_revision': 1}, auth)[0], 409)
        self.assertEqual(self.call('/api/v1/projects/missing')[0], 404)
        summary = self.call('/api/v1/projects/study/summary')[1]
        self.assertIn('已复核', summary['summary'])
        self.assertEqual(summary['basis']['type'], 'registered_metadata')
        board = self.call('/api/board-state')[1]
        board['todos'] = [{'id': 'todo-1', 'title': '复核图表', 'date': '2026-11-24', 'card': 'p-study', 'done': False}]
        self.assertEqual(self.call('/api/board-state', 'POST', board, auth)[0], 200)
        self.assertEqual(self.call('/api/board-state', 'POST', board, auth)[0], 409)
        self.assertEqual(self.call('/api/v1/projects/study/archive', 'POST', {'expected_revision': 2}, auth)[0], 200)
        self.assertEqual(self.call('/api/v1/projects')[1]['projects'], [])
        self.assertEqual(len(self.call('/api/v1/projects?include_archived=true')[1]['projects']), 1)
        self.assertEqual(self.call('/api/v1/projects/study/restore', 'POST', {'expected_revision': 3}, auth)[0], 200)
        self.assertEqual(self.call('/api/board-state')[1]['todos'][0]['title'], '复核图表')
        self.assertEqual(self.call('/api/files')[1]['total'], 0)
        self.assertEqual(self.call('/api/openapi.json')[1], contract.openapi())


class ContractTests(unittest.TestCase):
    def test_checked_in_openapi_matches_code(self):
        self.assertEqual(json.loads((rt.APP_DIR / 'openapi.json').read_text(encoding='utf8')), contract.openapi())

    def test_demo_is_valid_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='ai4s-demo-test-') as temp:
            dest = pathlib.Path(temp) / 'demo'
            command = [sys.executable, '-B', str(rt.APP_DIR / 'examples/create_demo.py'), '--destination', str(dest), '--date', '2026-11-23']
            result = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((dest / 'data/desktop_data.json').read_text(encoding='utf8'))
            self.assertEqual(len(data['projects']), 6)
            self.assertEqual(len(data['bundles']), 4)
            self.assertTrue((dest / 'data/files.sqlite').exists())
            original = (dest / 'data/desktop_board_state.json').read_bytes()
            result = subprocess.run(command, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((dest / 'data/desktop_board_state.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
