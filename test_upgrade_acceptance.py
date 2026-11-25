# -*- coding: utf-8 -*-
"""Independent behavior acceptance: isolated data, preservation and recovery."""
import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import desktop_history as history
import desktop_contract as contract
import desktop_manage as manage
import desktop_repository as repository
import desktop_runtime as rt
import desktop_services as services
import desktop_state as state
import desktop_storage as storage


class UpgradeAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai4s-upgrade-acceptance-')
        self.root = pathlib.Path(self.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            manage.init(self.root / 'workspace')
        self.config = self.root / 'workspace/workspace.json'
        rt.configure(self.config)
        services.execute('project_create', {'expected_revision': 0, 'project': {
            'id': 'synthetic-study', 'name': 'Synthetic study', 'local': '.',
            'source': 'README.md', 'observed_at': '2026-10-01T09:00:00+08:00',
            'research_stage': 'Results review', 'run_status': 'unknown',
            'status': 'Waiting for review', 'todo': 'Check replicate quality'
        }})

    def tearDown(self):
        rt.configure()
        self.temp.cleanup()

    def old_board(self):
        return {'revision': 7, 'cards': [
            {'id': 'project-card', 'type': 'project', 'target': 'synthetic-study',
             'title': 'Study shortcut', 'folder': 'folder-1', 'zone': 'plan', 'x': .27, 'y': .61},
            {'id': 'folder-1', 'type': 'folder', 'target': '', 'title': 'Studies',
             'folder': '', 'zone': 'plan', 'x': .12, 'y': .34},
        ], 'todos': [
            {'id': 'old-review', 'title': 'Review replicates', 'date': '2026-11-25',
             'card': 'project-card', 'done': False},
            {'id': 'old-complete', 'title': 'Previous review', 'date': '2026-11-24',
             'card': '', 'done': True}
        ], 'saved_at': '2026-11-24T12:30:00+08:00'}

    def seed_old_board(self):
        rt.write_json(state.state_path(), self.old_board())

    def add_task(self, identifier, **patch):
        value = {'id': identifier, 'title': identifier, 'date': '2026-11-25',
                 'start_date': '2026-11-25', 'card': '', 'done': False,
                 'project_id': 'synthetic-study', 'status': 'todo', 'progress': 0,
                 'dependencies': [], 'milestone': False, 'repeat': 'none', 'notes': ''}
        value.update(patch)
        board = state.read()
        board['todos'].append(value)
        result = state.save(board)
        self.assertIsNotNone(result)
        return result

    def change_task(self, identifier, **patch):
        board = state.read()
        next(t for t in board['todos'] if t['id'] == identifier).update(patch)
        return state.save(board)

    def test_legacy_read_is_non_destructive_and_card_removal_keeps_project(self):
        self.seed_old_board()
        original = state.state_path().read_bytes()
        board = state.read()
        self.assertEqual(state.state_path().read_bytes(), original, 'Reading must not silently migrate files')
        task = next(t for t in board['todos'] if t['id'] == 'old-review')
        self.assertEqual(task['project_id'], 'synthetic-study')
        self.assertEqual(task['start_date'], task['date'])
        saved_other = copy.deepcopy(board['todos'][1])
        board['cards'] = [c for c in board['cards'] if c['id'] != 'project-card']
        task['card'] = ''
        state.save(board)
        restored = state.read()
        self.assertEqual(restored['todos'][0]['project_id'], 'synthetic-study')
        self.assertEqual(restored['todos'][1], saved_other)
        self.assertEqual(restored['cards'][0]['x'], .12)

    def test_invalid_dates_and_cycle_leave_bytes_unchanged(self):
        self.add_task('a')
        self.add_task('b', dependencies=['a'])
        for patch in [{'start_date': '2026-11-26'}, {'dependencies': ['b']},
                      {'dependencies': ['a']}, {'date': '2026-02-30'}]:
            before = state.state_path().read_bytes()
            with self.assertRaises(ValueError):
                self.change_task('a', **patch)
            self.assertEqual(state.state_path().read_bytes(), before)

    def test_new_card_and_legacy_task_in_same_save_get_project_association(self):
        board = state.read()
        board['cards'].append({'id': 'extra-project-card', 'type': 'project',
            'target': 'synthetic-study', 'title': 'Additional shortcut', 'folder': '',
            'zone': 'inbox', 'x': 0, 'y': 0})
        board['todos'].append({'id': 'new-legacy-task', 'title': 'Legacy client task',
            'date': '2026-11-25', 'card': 'extra-project-card', 'done': False})
        saved = state.save(board)
        task = next(t for t in saved['todos'] if t['id'] == 'new-legacy-task')
        self.assertEqual(task['project_id'], 'synthetic-study')

    def test_milestone_cannot_have_multiple_days(self):
        self.add_task('milestone', milestone=True)
        before = state.state_path().read_bytes()
        with self.assertRaises(ValueError):
            self.change_task('milestone', start_date='2026-11-24')
        self.assertEqual(state.state_path().read_bytes(), before)

    def test_repeated_month_end_completion_is_idempotent(self):
        self.add_task('monthly', start_date='2028-01-31', date='2028-01-31', repeat='monthly')
        self.change_task('monthly', done=True, status='done')
        board = state.read()
        self.assertEqual(len(board['todos']), 2)
        child = next(t for t in board['todos'] if t['id'] != 'monthly')
        self.assertEqual(child['date'], '2028-02-29')
        self.assertEqual(child['project_id'], 'synthetic-study')
        self.change_task(child['id'], notes='User has already edited this occurrence')
        self.change_task('monthly', done=False, status='todo')
        self.change_task('monthly', done=True, status='done')
        current = state.read()['todos']
        self.assertEqual(len(current), 2)
        self.assertEqual(next(t for t in current if t['id'] == child['id'])['notes'],
                         'User has already edited this occurrence')

    def test_stale_board_save_cannot_replace_history_or_user_data(self):
        self.add_task('first')
        stale = state.read()
        self.add_task('second')
        before = state.state_path().read_bytes()
        self.assertIsNone(state.save(stale))
        self.assertEqual(state.state_path().read_bytes(), before)

    def test_atomic_save_failure_keeps_data_and_history_together(self):
        self.add_task('first')
        before = state.state_path().read_bytes()
        board = state.read()
        board['todos'][0]['title'] = 'Must not become visible'
        with mock.patch.object(storage.os, 'replace', side_effect=OSError('Synthetic atomic replace failure')):
            with self.assertRaises(OSError):
                state.save(board)
        self.assertEqual(state.state_path().read_bytes(), before)
        self.assertEqual(state.read()['todos'][0]['title'], 'first')

    def project_patch(self, **patch):
        current = services.execute('project_get', {'project_id': 'synthetic-study'})
        return services.execute('project_update', {'project_id': 'synthetic-study',
            'expected_revision': current['revision'], 'patch': patch})

    def test_project_undo_preserves_later_unrelated_fields(self):
        with mock.patch.object(rt, 'now', return_value='2026-11-25T10:00:00+08:00'):
            self.project_patch(status='Result review underway')
        change = rt.read_json(rt.path('desktop_projects.json'))['_history'][-1]['id']
        with mock.patch.object(rt, 'now', return_value='2026-11-25T10:01:00+08:00'):
            self.project_patch(todo='Send a revised figure for review')
        current = history.listing()
        history.undo(change, current['revision'])
        p = services.execute('project_get', {'project_id': 'synthetic-study'})['project']
        self.assertEqual(p['status'], 'Waiting for review')
        self.assertEqual(p['todo'], 'Send a revised figure for review')
        self.assertEqual(p['observed_at'], '2026-10-01T09:00:00+08:00')

    def test_project_undo_refuses_later_change_to_same_field(self):
        self.project_patch(status='Version two')
        change = rt.read_json(rt.path('desktop_projects.json'))['_history'][-1]['id']
        self.project_patch(status='Version three')
        before = rt.path('desktop_projects.json').read_bytes()
        with self.assertRaises(services.ConflictError):
            history.undo(change, history.listing()['revision'])
        self.assertEqual(rt.path('desktop_projects.json').read_bytes(), before)

    def test_board_undo_keeps_a_later_unrelated_task(self):
        self.add_task('a')
        self.change_task('a', title='Changed title')
        change = rt.read_json(state.state_path())['_history'][-1]['id']
        self.add_task('b')
        history.undo(change, history.listing()['revision'])
        tasks = {t['id']: t for t in state.read()['todos']}
        self.assertEqual(set(tasks), {'a', 'b'})
        self.assertEqual(tasks['a']['title'], 'a')
        self.assertEqual(tasks['b']['title'], 'b')

    def test_portable_archive_preserves_new_task_state_and_starts(self):
        self.add_task('milestone', milestone=True, notes='Ready for author review')
        self.add_task('follow-up', start_date='2026-11-26', date='2026-11-26', dependencies=['milestone'])
        before = copy.deepcopy(state.read())
        with contextlib.redirect_stdout(io.StringIO()):
            manage.pack(self.root / 'portable.zip')
        with zipfile.ZipFile(self.root / 'portable.zip') as bundle:
            self.assertIn('desktop_history.py', bundle.namelist())
            self.assertIn('desktop_tasks.py', bundle.namelist())
            bundle.extractall(self.root / 'restored')
        restored_root = self.root / 'restored'
        rt.configure(restored_root / 'workspace.json')
        self.assertEqual(state.read(), before)
        run = subprocess.run([sys.executable, '-B', str(restored_root / 'desktop_server.py'), '--help'],
                             capture_output=True, timeout=20, cwd=restored_root)
        self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', 'replace'))

    def test_result_version_change_and_run_success_do_not_change_other_adoption(self):
        versions = [
            {'id': 'expression-v1', 'name': 'Expression', 'version': 'v1', 'category': 'paper',
             'status': 'adopted', 'scope': 'Reviewed replicate comparison'},
            {'id': 'network-v2', 'name': 'Network', 'version': 'v2', 'category': 'exploratory',
             'status': 'exploratory', 'scope': 'Candidate generation only'},
        ]
        self.project_patch(result_versions=versions, adoption_status='pending')
        self.project_patch(run_status='succeeded', run_source='run.json',
                           run_observed_at='2026-11-25T08:00:00+08:00')
        project = services.execute('project_get', {'project_id': 'synthetic-study'})['project']
        self.assertEqual(project['result_versions'], versions)
        self.assertEqual(project['adoption_status'], 'pending')
        changed = copy.deepcopy(versions)
        changed[1]['version'] = 'v3'
        changed[1]['scope'] = 'Updated candidate generation'
        self.project_patch(result_versions=changed)
        after = services.execute('project_get', {'project_id': 'synthetic-study'})['project']
        self.assertEqual(after['result_versions'][0], versions[0])
        self.assertEqual(after['result_versions'][1]['category'], 'exploratory')
        self.assertEqual(after['observed_at'], '2026-10-01T09:00:00+08:00')

    def test_mapping_preview_is_readonly_and_remote_stays_unverified(self):
        missing = self.root / 'original-missing-root'
        destination = self.root / 'existing-root'
        destination.mkdir()
        self.project_patch(local=str(missing), remote='/srv/synthetic-study', ssh_alias='synthetic-host')
        before_config = self.config.read_bytes()
        before_projects = rt.path('desktop_projects.json').read_bytes()
        diag = services.execute('workspace_diagnostics', {})
        self.assertEqual(next(l for l in diag['locations'] if l['kind'] == 'server')['status'], 'unverified')
        self.assertEqual(next(l for l in diag['locations'] if l['kind'] == 'local')['status'], 'missing_at_path')
        mappings = [{'host': 'local', 'from': str(missing), 'to': str(destination)}]
        preview = services.execute('path_mappings_preview', {'mappings': mappings})
        self.assertEqual(self.config.read_bytes(), before_config)
        self.assertEqual(rt.path('desktop_projects.json').read_bytes(), before_projects)
        self.assertEqual(next(l for l in preview['locations'] if l['kind'] == 'local')['status'], 'available')
        applied = services.execute('path_mappings_set', {'mappings': mappings,
                                    'expected_revision': preview['config_revision']})
        self.assertGreater(applied['config_revision'], preview['config_revision'])
        self.assertEqual(rt.path('desktop_projects.json').read_bytes(), before_projects)
        self.assertFalse(missing.exists(), 'Mapping must not create/move research directories')
        self.assertTrue(destination.is_dir())
        with self.assertRaises(services.ConflictError):
            services.execute('path_mappings_set', {'mappings': [], 'expected_revision': preview['config_revision']})

    def test_mapping_from_another_process_updates_existing_runtime(self):
        original = self.root / 'old-path'
        destination = self.root / 'new-path'
        destination.mkdir()
        self.project_patch(local=str(original))
        cached_before = copy.deepcopy(rt.CONFIG)
        script = ('import json,sys; import desktop_runtime as rt; import desktop_services as s; '
                  'rt.configure(sys.argv[1]); '
                  's.execute("path_mappings_set", {"expected_revision":0,"mappings":json.loads(sys.argv[2])})')
        mappings = [{'host': 'local', 'from': str(original), 'to': str(destination)}]
        run = subprocess.run([sys.executable, '-B', '-c', script, str(self.config), json.dumps(mappings)],
                             cwd=rt.APP_DIR, capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', 'replace'))
        self.assertEqual(rt.CONFIG, cached_before, 'The test must retain a pre-change runtime cache')
        project = services.execute('project_get', {'project_id': 'synthetic-study'})['project']
        self.assertEqual(pathlib.Path(project['local']), destination)
        self.assertEqual(repository.overrides()['projects'][0]['local'], str(original))

    def test_calendar_export_has_valid_folding_and_inclusive_end(self):
        title = '重复检查样本结果' * 20 + '; comma, backslash\\'
        self.add_task('export-task', title=title, notes='Line one\r\nLine two; comma,',
                      start_date='2028-02-28', date='2028-02-29')
        export = services.execute('workspace_export', {'format': 'ics'})
        content = export['content']
        self.assertTrue(content.startswith('BEGIN:VCALENDAR\r\n'))
        self.assertTrue(content.endswith('END:VCALENDAR\r\n'))
        self.assertIn('DTSTART;VALUE=DATE:20280228', content)
        self.assertIn('DTEND;VALUE=DATE:20280301', content)
        for line in content.split('\r\n'):
            self.assertLessEqual(len(line.encode('utf-8')), 75)
            self.assertNotIn('\r', line)
            self.assertNotIn('\n', line)
        unfolded = content.replace('\r\n ', '')
        self.assertIn('Line one\\nLine two\\; comma\\,', unfolded)
        self.assertIn('SUMMARY:' + title.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,'), unfolded)

    def test_stdio_agent_task_and_folder_journey(self):
        operations = [
            ('tasks_list', {}),
            ('task_create', {'expected_revision': 0, 'task': {'id': 'mcp-review', 'title': 'Weekly review',
                'date': '2026-11-25', 'project_id': 'synthetic-study', 'card': 'p-synthetic-study', 'repeat': 'weekly'}}),
            ('task_create', {'expected_revision': 0, 'task': {'id': 'mcp-review', 'title': 'Weekly review',
                'date': '2026-11-25', 'project_id': 'synthetic-study', 'card': 'p-synthetic-study', 'repeat': 'weekly'}}),
            ('card_create', {'expected_revision': 1, 'card': {'id': 'mcp-folder', 'type': 'folder', 'title': 'Agent folder'}}),
            ('card_update', {'expected_revision': 2, 'card_id': 'p-synthetic-study', 'patch': {'folder': 'mcp-folder'}}),
            ('task_update', {'expected_revision': 3, 'task_id': 'mcp-review', 'patch': {'status': 'done'}}),
            ('card_remove', {'expected_revision': 4, 'card_id': 'p-synthetic-study'}),
            ('tasks_list', {}),
            ('task_update', {'expected_revision': 5, 'task_id': 'mcp-review', 'patch': {'dependencies': ['mcp-review']}}),
        ]
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25',
              'capabilities': {}, 'clientInfo': {'name': 'independent-qa', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        ]
        messages += [{'jsonrpc': '2.0', 'id': 10 + i, 'method': 'tools/call',
                      'params': {'name': name, 'arguments': args}} for i, (name, args) in enumerate(operations)]
        run = subprocess.run([sys.executable, '-B', str(rt.APP_DIR / 'desktop_mcp.py'), '--config', str(self.config)],
            input=(''.join(json.dumps(m) + '\n' for m in messages)).encode('utf-8'),
            capture_output=True, timeout=25)
        self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', 'replace'))
        results = {r['id']: r['result'] for r in map(json.loads, run.stdout.decode('utf-8').splitlines())}
        tools = {t['name'] for t in results[2]['tools']}
        self.assertTrue({'tasks_list', 'task_create', 'task_update', 'task_remove', 'card_create',
                         'card_update', 'card_remove', 'history_list', 'history_undo'} <= tools)
        for i, (name, _) in enumerate(operations[:-1]):
            result = results[10 + i]
            self.assertFalse(result['isError'], result)
            contract.validate(result['structuredContent'], contract.OUTPUTS[name])
        self.assertEqual(results[11]['structuredContent']['revision'], results[12]['structuredContent']['revision'])
        tasks = results[17]['structuredContent']['tasks']
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(t['project_id'] == 'synthetic-study' and t['card'] == '' for t in tasks))
        self.assertTrue(results[18]['isError'])

    def test_two_task_writers_cannot_accept_the_same_revision(self):
        processes = []
        try:
            for i in range(2):
                process = subprocess.Popen([sys.executable, '-B', str(rt.APP_DIR / 'desktop_mcp.py'),
                    '--config', str(self.config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                processes.append(process)
                requests = [
                    {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25',
                     'capabilities': {}, 'clientInfo': {'name': 'race-qa', 'version': '1'}}},
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'task_create',
                     'arguments': {'expected_revision': 0, 'task': {'id': 'racer-' + str(i),
                      'title': 'Concurrent task', 'date': '2026-11-25', 'project_id': 'synthetic-study'}}}}
                ]
                process.stdin.write((''.join(json.dumps(r) + '\n' for r in requests)).encode('utf-8'))
                process.stdin.close()
                process.stdin = None
            outputs = [p.communicate(timeout=20) for p in processes]
            results = [json.loads(out.decode('utf-8').splitlines()[-1])['result'] for out, _ in outputs]
            self.assertEqual(sorted(r['isError'] for r in results), [False, True])
            saved = rt.read_json(state.state_path())
            self.assertEqual(saved['revision'], 1)
            self.assertEqual(len(saved['todos']), 1)
            self.assertEqual(len(saved['_history']), 1)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
