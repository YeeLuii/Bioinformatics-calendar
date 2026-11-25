"""Deployment tests use synthetic workspaces and a fake Codex CLI only."""
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import deploy
import deploy_codex as codex

APP = pathlib.Path(__file__).resolve().parent


class CodexRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.target = self.root / 'config.toml'
        self.original = b'model = "example-model"\r\n# keep this comment\r\n'
        self.target.write_bytes(self.original)
        self.python = self.root / 'Python path' / 'python.exe'
        self.script = self.root / 'app' / 'desktop_mcp.py'
        self.config = self.root / 'workspace' / 'workspace.json'
        self.arguments = ['-B', str(self.script), '--config', str(self.config)]
        self.other = {'name': 'other', 'enabled': True, 'transport': {'type': 'stdio', 'command': 'other'}}
        self.entry = {'name': 'ai4s', 'enabled': True, 'transport': {
            'type': 'stdio', 'command': str(self.python), 'args': self.arguments}}
        self.rows = [self.other]
        self.calls = []
        self.failure = None
        self.patcher = mock.patch.object(codex, 'codex_command', return_value=['fake-codex'])
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def runner(self, command, args):
        self.calls.append(args)
        if args[1] == 'add':
            self.assertEqual(args, ['mcp', 'add', 'ai4s', '--', str(self.python), *self.arguments])
            raw = self.original + b'\r\n[mcp_servers.ai4s]\r\ncommand = "python"\r\n'
            self.target.write_bytes(raw.replace(b'\r\n', b'\r\r\n') if self.failure == 'newline' else raw)
            self.rows = [self.other, self.entry]
            return subprocess.CompletedProcess(command, 1 if self.failure == 'exit' else 0, b'', b'')
        if len(self.calls) > 1 and self.failure == 'concurrent':
            self.target.write_bytes(b'# external edit\n')
        rows = {'invalid': True} if len(self.calls) > 1 and self.failure == 'shape' else self.rows
        return subprocess.CompletedProcess(command, 0, json.dumps(rows).encode(), b'')

    def register(self, **kwargs):
        return codex.register(self.python, self.script, self.config, home=self.root, runner=self.runner, **kwargs)

    def test_backup_and_repeat_registration_preserve_bytes(self):
        result = self.register()
        self.assertEqual(result['status'], 'registered')
        self.assertEqual(pathlib.Path(result['backup']).read_bytes(), self.original)
        after = self.target.read_bytes()
        self.assertEqual(self.register()['status'], 'already_configured')
        self.assertEqual(self.target.read_bytes(), after)
        self.assertEqual(sum(c[1] == 'add' for c in self.calls), 1)

    def test_bad_existing_line_endings_do_not_call_cli(self):
        self.target.write_bytes(self.original.replace(b'\r\n', b'\r\r\n'))
        before = self.target.read_bytes()
        with self.assertRaises(codex.DeploymentError):
            self.register()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.target.read_bytes(), before)

    def test_failed_cli_or_verification_restores_exact_bytes(self):
        for failure in ('newline', 'exit', 'shape'):
            with self.subTest(failure=failure):
                self.target.write_bytes(self.original)
                self.rows, self.calls, self.failure = [self.other], [], failure
                with self.assertRaisesRegex(codex.DeploymentError, 'original bytes were restored'):
                    self.register()
                self.assertEqual(self.target.read_bytes(), self.original)

    def test_conflicting_entry_is_not_overwritten(self):
        self.rows.append({**self.entry, 'transport': {'type': 'stdio', 'command': 'different'}})
        with self.assertRaisesRegex(codex.DeploymentError, 'already points elsewhere'):
            self.register()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.register(replace=True)['status'], 'registered')

    def test_concurrent_change_is_not_rolled_back(self):
        self.failure = 'concurrent'
        with self.assertRaisesRegex(codex.DeploymentError, 'rollback was skipped'):
            self.register()
        self.assertEqual(self.target.read_bytes(), b'# external edit\n')
        self.assertEqual(len(list(self.root.glob('config.toml.ai4s-backup-*'))), 1)

    def test_cli_absence_has_explicit_outcomes(self):
        with mock.patch.object(codex, 'codex_command', return_value=None):
            self.assertEqual(self.register()['status'], 'cli_unavailable')
            self.assertEqual(self.register(mode='off')['status'], 'disabled')
            with self.assertRaises(codex.DeploymentError):
                self.register(mode='required')
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_absent_config_restored_to_absence(self):
        self.target.unlink()
        self.failure = 'exit'
        with self.assertRaises(codex.DeploymentError):
            self.register()
        self.assertFalse(self.target.exists())


class DeploymentTests(unittest.TestCase):
    def test_python_range(self):
        for version, accepted in [((3, 8), False), ((3, 9), True), ((3, 14), True), ((4, 0), False)]:
            with self.subTest(version=version), mock.patch.object(sys, 'version_info', version):
                if accepted:
                    self.assertEqual(deploy.check_environment()['supported_python'], '>=3.9,<4.0')
                else:
                    with self.assertRaises(codex.DeploymentError):
                        deploy.check_environment()

    def run_deploy(self, workspace, *args, bootstrap=False):
        if bootstrap and os.name == 'nt':
            command = [shutil.which('powershell') or shutil.which('pwsh'), '-NoProfile',
                       '-ExecutionPolicy', 'Bypass', '-File', str(APP / 'deploy.ps1')]
        elif bootstrap:
            command = ['sh', str(APP / 'deploy.sh')]
        else:
            command = [sys.executable, '-B', str(APP / 'deploy.py')]
        result = subprocess.run(command + list(args) + ['--workspace', str(workspace), '--no-open', '--mcp', 'off'],
                                capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf8', errors='replace'))
        return json.loads(result.stdout.decode('utf8'))

    def test_bootstrap_reuse_port_conflict_and_guarded_stop(self):
        with tempfile.TemporaryDirectory(prefix='ai4s-') as directory:
            workspace = pathlib.Path(directory) / '研究 workspace'
            with socket.socket() as occupied:
                occupied.bind(('127.0.0.1', 0))
                occupied.listen()
                port = occupied.getsockname()[1]
                result = self.run_deploy(workspace, '--port', str(port), bootstrap=True)
            try:
                self.assertEqual(result['status'], 'ready')
                self.assertNotEqual(result['port'], port)
                self.assertEqual(result['mcp_tools'], len(deploy.contract.TOOLS))
                self.assertEqual(result['mcp_registration']['status'], 'disabled')
                projects = workspace / 'data/desktop_projects.json'
                original = projects.read_bytes()
                repeated = self.run_deploy(workspace)
                self.assertTrue(repeated['reused'])
                self.assertEqual(repeated['pid'], result['pid'])
                self.assertEqual(projects.read_bytes(), original)
                board = workspace / 'data/desktop_board_state.json'
                board.write_text('{"revision":0,"cards":[],"todos":[]}\n', encoding='utf8')
                board_before = board.read_bytes()
                status = self.run_deploy(workspace, 'status')
                self.assertEqual(status['status'], 'running')
                token = deploy.request(result['port'], '/api/overview')['token']
                with self.assertRaises(codex.DeploymentError):
                    deploy.request(result['port'], '/api/deploy-stop', {'deployment_id': 'wrong'}, token)
                self.assertIsNotNone(deploy.health(result['port']))
                with self.assertRaises(codex.DeploymentError):
                    deploy.request(result['port'], '/api/deploy-stop', {'deployment_id': result['deployment_id']})
                restarted = self.run_deploy(workspace, '--restart')
                self.assertNotEqual(restarted['deployment_id'], result['deployment_id'])
                self.assertEqual(projects.read_bytes(), original)
                self.assertEqual(board.read_bytes(), board_before)
            finally:
                stopped = self.run_deploy(workspace, 'stop')
                self.assertEqual(stopped['status'], 'stopped')
            self.assertEqual(self.run_deploy(workspace, 'status')['status'], 'not_running')
            self.assertEqual(self.run_deploy(workspace, 'stop')['status'], 'not_running')


if __name__ == '__main__':
    unittest.main()
