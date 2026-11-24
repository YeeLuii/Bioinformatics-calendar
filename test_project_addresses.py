"""Multi-location metadata, API validation and registered navigation."""
import pathlib
import tempfile
import unittest
import desktop_runtime as rt
import desktop_manage as manage
import desktop_services as services
import desktop_repository as repository


class AddressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai4s-address-')
        self.root = pathlib.Path(self.temp.name)
        self.original = rt.CONFIG, rt.DATA_DIR, rt.WORKSPACE_ROOT
        manage.init(self.root / 'workspace')
        rt.configure(self.root / 'workspace/workspace.json')

    def tearDown(self):
        rt.CONFIG, rt.DATA_DIR, rt.WORKSPACE_ROOT = self.original
        self.temp.cleanup()

    def test_multiserver_roundtrip_partial_update_and_removal(self):
        entries = [
            {'id': 'compute', 'label': 'Compute', 'kind': 'server', 'path': '/srv/results', 'ssh_alias': 'compute-host'},
            {'id': 'backup', 'kind': 'server', 'path': '/archive/results', 'ssh_alias': 'backup-host'},
            {'id': 'local-copy', 'kind': 'local', 'path': '.'},
            {'id': 'web', 'kind': 'url', 'path': 'https://example.org/report?q=1&v=2'}
        ]
        result = services.execute('project_create', {'expected_revision': 0, 'project': {
            'id': 'study', 'name': 'Study', 'local': '.', 'remote': '/primary', 'ssh_alias': 'primary-host', 'addresses': entries}})
        self.assertEqual(len(result['project']['addresses']), 4)
        self.assertEqual(repository.project_location('project:study:server')['ssh_alias'], 'primary-host')
        self.assertEqual(repository.project_location('project:study:address:compute')['ssh_alias'], 'compute-host')
        self.assertEqual(repository.project_location('project:study:address:backup')['ssh_alias'], 'backup-host')
        self.assertEqual(pathlib.Path(repository.project_location('project:study:address:local-copy')['path']), rt.WORKSPACE_ROOT)
        services.execute('project_update', {'project_id': 'study', 'expected_revision': 1, 'patch': {'status': 'Reviewed'}})
        self.assertEqual(len(services.get_project('study')['project']['addresses']), 4)
        self.assertEqual(repository.overrides()['projects'][0]['addresses'][2]['path'], '.')
        with self.assertRaises(services.ConflictError):
            services.execute('project_update', {'project_id': 'study', 'expected_revision': 1, 'patch': {'addresses': []}})
        services.execute('project_update', {'project_id': 'study', 'expected_revision': 2, 'patch': {'addresses': []}})
        self.assertIsNone(repository.project_location('project:study:address:compute'))
        self.assertIsNotNone(repository.project_location('project:study:server'))

    def test_unsafe_and_duplicate_addresses_rejected_without_writes(self):
        invalid = [
            [{'id': 'x', 'kind': 'url', 'path': 'javascript:alert(1)'}],
            [{'id': 'x', 'kind': 'url', 'path': 'https://user:secret@example.org'}],
            [{'id': 'x', 'kind': 'server', 'path': '/data', 'ssh_alias': '-oProxyCommand=bad'}],
            [{'id': 'x', 'kind': 'server', 'path': 'relative/path'}],
            [{'id': 'x', 'kind': 'local', 'path': '.'}] * 2
        ]
        for entries in invalid:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                services.execute('project_create', {'expected_revision': 0, 'project': {'id': 'study', 'name': 'Study', 'addresses': entries}})
        self.assertEqual(repository.overrides()['revision'], 0)


if __name__ == '__main__':
    unittest.main()
