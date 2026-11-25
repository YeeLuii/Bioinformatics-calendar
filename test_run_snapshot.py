"""Read-only adapter boundaries and stale-observation protection."""
import copy
import datetime
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from examples.import_run_snapshot import prepare


class RunSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'sample', 'research_stage': 'review', 'adoption_status': 'exploratory'}
        self.now = datetime.datetime(2026, 11, 25, 9, tzinfo=datetime.timezone.utc)
        self.snapshot = {'schema_version': 1, 'project_id': 'sample', 'run_status': 'succeeded',
                         'observed_at': '2026-11-25T16:00:00+08:00', 'source': 'run-status.json', 'run_id': '123'}

    def test_patch_does_not_promote_research_results(self):
        patch = prepare(self.snapshot, self.project, self.now)
        self.assertEqual(set(patch), {'run_status', 'run_source', 'run_observed_at'})
        self.assertEqual(patch['run_status'], 'succeeded')
        self.assertEqual(self.project['adoption_status'], 'exploratory')

    def test_replay_is_noop(self):
        patch = prepare(self.snapshot, self.project, self.now)
        self.assertEqual(prepare(self.snapshot, dict(self.project, **patch), self.now), {})

    def test_stale_and_same_time_conflict_rejected(self):
        for stamp in ['2026-11-25T16:01:00+08:00', self.snapshot['observed_at']]:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                prepare(self.snapshot, dict(self.project, run_observed_at=stamp, run_status='running'), self.now)

    def test_bad_sources_dates_and_states_rejected(self):
        cases = [('project_id', 'other'), ('run_status', 'complete'), ('source', ''),
                 ('source', 'a\nb'), ('observed_at', '2026-11-25'),
                 ('observed_at', '2099-01-01T00:00:00+00:00'), ('command', 'anything')]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                item = copy.deepcopy(self.snapshot)
                item[key] = value
                prepare(item, self.project, self.now)

    def test_cli_preview_apply_conflict_and_replay(self):
        import desktop_manage as manage
        import desktop_runtime as runtime
        root = pathlib.Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='ai4s-run-adapter-') as tmp:
            workspace = pathlib.Path(tmp) / 'workspace'
            manage.init(workspace)
            projects = workspace / 'data/desktop_projects.json'
            projects.write_text(json.dumps({'schema_version': 1, 'revision': 1,
                'projects': [dict(self.project, name='Example', current_version='v2')]}), encoding='utf-8')
            snapshot_path = pathlib.Path(tmp) / 'run.json'
            snapshot = dict(self.snapshot, observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            snapshot_path.write_text(json.dumps(snapshot), encoding='utf-8')
            command = [sys.executable, '-B', str(root / 'examples/import_run_snapshot.py'),
                       '--config', str(workspace / 'workspace.json'), '--snapshot', str(snapshot_path)]
            original = projects.read_bytes()
            source_bytes = snapshot_path.read_bytes()
            preview = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual(json.loads(preview.stdout)['expected_revision'], 1)
            self.assertEqual(projects.read_bytes(), original)
            applied = subprocess.run(command + ['--apply', '--expected-revision', '1'], capture_output=True, timeout=15)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            saved = json.loads(projects.read_text(encoding='utf-8'))
            self.assertEqual(saved['projects'][0]['run_status'], 'succeeded')
            self.assertEqual(saved['projects'][0]['adoption_status'], 'exploratory')
            self.assertTrue(saved['_history'])
            after = projects.read_bytes()
            replay = subprocess.run(command + ['--apply', '--expected-revision', '2'], capture_output=True, timeout=15)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertFalse(json.loads(replay.stdout)['applied'])
            self.assertEqual(projects.read_bytes(), after)
            conflict = subprocess.run(command + ['--apply', '--expected-revision', '1'], capture_output=True, timeout=15)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertEqual(projects.read_bytes(), after)
            self.assertEqual(snapshot_path.read_bytes(), source_bytes)


if __name__ == '__main__':
    unittest.main()
