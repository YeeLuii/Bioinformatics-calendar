"""Behavioral checks for portable research task metadata, history and exports."""
import json
import pathlib
import tempfile
import unittest

import desktop_manage as manage
import desktop_runtime as rt
import desktop_services as service
import desktop_contract as contract
import desktop_state as state


class TaskManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ai4s-task-')
        self.root=pathlib.Path(self.tmp.name)
        manage.init(self.root/'workspace');rt.configure(self.root/'workspace/workspace.json')
        service.execute('project_create',{'project':{'id':'study','name':'Test study'},'expected_revision':0})

    def tearDown(self):
        rt.configure();self.tmp.cleanup()

    def create(self,**fields):
        return service.execute('task_create',{'task':{'title':'Review','date':'2026-11-25',**fields},'expected_revision':state.read()['revision']})

    def test_create_retry_and_unsafe_remove(self):
        a=self.create(id='a');revision=a['revision']
        retry=service.execute('task_create',{'task':{'id':'a','title':'Review','date':'2026-11-25'},'expected_revision':0})
        self.assertEqual(retry['revision'],revision)
        self.create(id='b',dependencies=['a'])
        with self.assertRaises(ValueError):service.execute('task_remove',{'task_id':'a','expected_revision':state.read()['revision']})
        self.assertEqual(len(state.read()['todos']),2)

    def test_public_reads_do_not_expose_history(self):
        self.create(id='a')
        self.assertNotIn('_history',state.read())
        import desktop_repository as repo
        self.assertNotIn('_history',repo.overrides())
        self.assertGreater(len(service.execute('history_list',{})['entries']),0)
        self.assertIn('_history',rt.read_json(rt.path('desktop_board_state.json')))

    def test_generated_project_first_edit_undo_preserves_later_field(self):
        rt.write_json(rt.path('desktop_data.json'),{'projects':[{'id':'generated','name':'Generated','status':'Original','scope':'Original scope'}]})
        service.execute('project_update',{'project_id':'generated','expected_revision':1,'patch':{'status':'Reviewed'}})
        entry=service.execute('history_list',{})['entries'][0]
        service.execute('project_update',{'project_id':'generated','expected_revision':2,'patch':{'scope':'New scope'}})
        history=service.execute('history_list',{})
        service.execute('history_undo',{'entry_id':entry['id'],'expected_revision':history['revision']})
        p=service.get_project('generated')['project']
        self.assertEqual(p['status'],'Original');self.assertEqual(p['scope'],'New scope')

    def test_project_versions_independent_of_run_status(self):
        versions=[{'id':'a','name':'Expression','version':'v3','category':'paper','status':'adopted','scope':'Reviewed comparison'}, {'id':'b','name':'Annotation','version':'v4','category':'exploratory','status':'exploratory'}]
        service.execute('project_update',{'project_id':'study','expected_revision':1,'patch':{'result_versions':versions,'adoption_status':'pending'}})
        saved=service.execute('project_update',{'project_id':'study','expected_revision':2,'patch':{'run_status':'succeeded','run_source':'job-log','run_observed_at':'2026-11-25T09:00:00+08:00'}})['project']
        self.assertEqual(saved['result_versions'],versions)
        self.assertEqual(saved['adoption_status'],'pending')
        before=rt.path('desktop_projects.json').read_bytes()
        with self.assertRaises(ValueError):service.execute('project_update',{'project_id':'study','expected_revision':3,'patch':{'observed_at':'not a time'}})
        self.assertEqual(before,rt.path('desktop_projects.json').read_bytes())

    def test_mapping_preview_does_not_write_and_save_preserves_original(self):
        service.execute('project_update',{'project_id':'study','expected_revision':1,'patch':{'local':'D:/old/data','remote':'/old/data'}})
        before=rt.path('desktop_projects.json').read_bytes();config=rt.CONFIG_PATH.read_bytes()
        mapping=[{'host':'local','from':'D:/old','to':str(self.root)},{'host':'server','from':'/old','to':'/new'}]
        preview=service.execute('path_mappings_preview',{'mappings':mapping})
        self.assertEqual(len(preview['changes']),2);self.assertEqual(config,rt.CONFIG_PATH.read_bytes())
        result=service.execute('path_mappings_set',{'mappings':mapping,'expected_revision':0})
        self.assertEqual(result['config_revision'],1);self.assertEqual(before,rt.path('desktop_projects.json').read_bytes())
        self.assertEqual(service.get_project('study')['project']['remote'],'/new/data')
        with self.assertRaises(service.ConflictError):service.execute('path_mappings_set',{'mappings':[],'expected_revision':0})
        contract.validate(result,contract.OUTPUTS['path_mappings_set'])

    def test_export_ics_unicode_escape_and_project_filter(self):
        self.create(id='a',title='复核'*80,project_id='study',start_date='2026-11-24',notes='line1\r\nline2; comma,')
        self.create(id='b',title='Unrelated')
        export=service.execute('workspace_export',{'format':'ics','project_id':'study'})
        lines=export['content'].split('\r\n')
        self.assertTrue(all(len(line.encode('utf-8'))<=75 for line in lines))
        flat=export['content'].replace('\r\n ','')
        self.assertIn('DTEND;VALUE=DATE:20261126',flat)
        self.assertIn('line1\\nline2\\; comma\\,',flat)
        self.assertNotIn('Unrelated',flat)
        for kind in ['markdown','json']:
            result=service.execute('workspace_export',{'format':kind,'project_id':'study'})
            self.assertIn('Test study',result['content']);self.assertNotIn('Unrelated',result['content'])

    def test_new_outputs_obey_shared_schema(self):
        outputs={
            'tasks_list':service.execute('tasks_list',{}),
            'cards_list':service.execute('cards_list',{}),
            'history_list':service.execute('history_list',{}),
            'workspace_diagnostics':service.execute('workspace_diagnostics',{}),
            'path_mappings_preview':service.execute('path_mappings_preview',{'mappings':[]}),
            'workspace_export':service.execute('workspace_export',{'format':'json'}),
        }
        for name,result in outputs.items():contract.validate(result,contract.OUTPUTS[name],name)


if __name__=='__main__':unittest.main()
