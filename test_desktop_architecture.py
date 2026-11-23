import desktop_links as links
import desktop_repository as repository
"""Integration checks for empty workspaces, migration and state isolation."""
import json, pathlib, tempfile, unittest, zipfile
import desktop_runtime as rt
import desktop_state as state
import desktop_manage as manage

THREAD='00000000-0000-4000-8000-000000000001'

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ai4s-test-');self.root=pathlib.Path(self.tmp.name)
        manage.init(self.root/'workspace');self.config=self.root/'workspace/workspace.json';rt.configure(self.config)
    def tearDown(self):
        rt.configure();self.tmp.cleanup()
    def project(self,remote=''):
        return repository.save_project({'revision':0,'project':{'id':'experiment','name':'实验项目','summary':'材料表征','local':'.','remote':remote}})
    def test_empty_workspace_without_index_or_domain_adapter(self):
        d=repository.overview();self.assertEqual(d['projects'],[]);self.assertFalse(d['capabilities']['file_index']);self.assertFalse(d['capabilities']['refresh'])
        self.assertEqual(state.read()['cards'],[])
    def test_project_edit_relative_folder_and_optional_server(self):
        self.project();p=repository.overview()['projects'][0]
        self.assertEqual(pathlib.Path(p['local']).resolve(),rt.WORKSPACE_ROOT)
        self.assertEqual(p['remote_id'],'');self.assertEqual(repository.project_location(p['local_id'])['availability'],'available')
        self.assertIsNone(repository.save_project({'revision':0,'project':{'id':'experiment','name':'不应覆盖'}}))
    def test_project_conversation_resolution_and_validation(self):
        self.project();result=links.save_project_links({'project_id':'experiment','revision':0,'threads':[{'id':THREAD,'title':'已有会话'}]})
        self.assertEqual(result['revision'],1);self.assertEqual(links.linked_thread_target('experiment',THREAD),'codex://threads/'+THREAD)
        with self.assertRaises(ValueError):links.linked_thread_target('experiment','unlinked')
        with self.assertRaises(ValueError):links.save_project_links({'project_id':'experiment','revision':1,'threads':[{'id':'../../bad','title':'bad'}]})
        self.assertIsNone(links.save_project_links({'project_id':'experiment','revision':0,'threads':[]}))
    def test_board_state_and_revision_are_workspace_local(self):
        self.project();s=state.read();s['cards'][0].update(zone='plan',x=.4,y=.2)
        self.assertEqual(state.save(s)['revision'],1);self.assertIsNone(state.save(s))
        s=state.read();s['todos']=[{'id':'t','title':'表征实验','date':'2026-11-23','card':'p-experiment','done':False}]
        state.save(s);self.assertTrue(rt.path('desktop_board_state.previous.json').exists())
        self.assertEqual(state.read()['todos'][0]['title'],'表征实验')
    def test_path_mapping_keeps_identifiers_and_original_files(self):
        cfg=rt.read_json(self.config);cfg['path_mappings']=[{'host':'local','from':'D:/old','to':str(rt.WORKSPACE_ROOT)},{'host':'server','from':'/old','to':'/new'}]
        rt.write_json(self.config,cfg);rt.configure(self.config)
        repository.save_project({'revision':0,'project':{'id':'experiment','name':'迁移项目','local':'D:/old','remote':'/old/data'}})
        p=repository.overview()['projects'][0]
        self.assertEqual(pathlib.Path(p['local']),rt.WORKSPACE_ROOT);self.assertEqual(p['remote'],'/new/data');self.assertEqual(p['id'],'experiment')
        self.assertEqual(repository.overrides()['projects'][0]['local'],'D:/old')
    def test_portable_archive_round_trip(self):
        self.project();state.save(state.read());manage.pack(self.root/'workspace.zip')
        with zipfile.ZipFile(self.root/'workspace.zip') as z:
            names=z.namelist();self.assertIn('desktop/details.js',names);self.assertNotIn('catalog.py',names)
            self.assertFalse(any(n.endswith(('.sqlite','.png')) for n in names));z.extractall(self.root/'restored')
        rt.configure(self.root/'restored/workspace.json')
        self.assertEqual(repository.overview()['projects'][0]['name'],'实验项目');self.assertEqual(state.read()['cards'][0]['target'],'experiment')
        self.assertEqual(rt.refresh_args(),[])

if __name__=='__main__':unittest.main()
