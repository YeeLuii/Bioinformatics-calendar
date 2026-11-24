"""Real stdio transport and public HTTP contract checks in isolated workspaces."""
import json, pathlib, subprocess, sys, tempfile, unittest, zipfile
import desktop_manage as manage
import desktop_runtime as rt
import desktop_contract as contract

class MCPTests(unittest.TestCase):
    def test_real_stdio_all_project_operations_and_exported_runtime(self):
        with tempfile.TemporaryDirectory(prefix='ai4s-mcp-') as temp:
            root=pathlib.Path(temp);manage.init(root/'data-workspace');config=root/'data-workspace/workspace.json'
            rt.configure(config);manage.pack(root/'release.zip');rt.configure()
            with zipfile.ZipFile(root/'release.zip') as z:z.extractall(root/'release')
            requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'acceptance','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'resources/read','params':{'uri':'ai4s://docs/openapi'}}]
            operations=[
                ('projects_list',{}),
                ('project_create',{'expected_revision':0,'project':{'id':'materials','name':'材料表征','local':'.','addresses':[{'id':'archive','kind':'server','path':'/srv/archive','ssh_alias':'backup-host'}]}}),
                ('project_update',{'project_id':'materials','expected_revision':1,'patch':{'status':'质控完成','todo':'重复实验'}}),
                ('project_update',{'project_id':'materials','expected_revision':1,'patch':{'status':'不应覆盖'}}),
                ('project_get',{'project_id':'materials'}),
                ('project_summarize',{'project_id':'materials'}),
                ('project_archive',{'project_id':'materials','expected_revision':2}),
                ('projects_list',{}),
                ('project_restore',{'project_id':'materials','expected_revision':3}),
                ('project_threads_set',{'project_id':'materials','expected_revision':0,'threads':[{'id':'00000000-0000-4000-8000-000000000001','title':'测试关联'}]}),
                ('project_threads_get',{'project_id':'materials'}),
                ('workspace_status',{}),
                ('project_update',{'project_id':'materials','expected_revision':4,'patch':{'unexpected':'invalid'}})
            ]
            for i,(name,args) in enumerate(operations,10):requests.append({'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'name':name,'arguments':args}})
            raw=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in requests).encode()
            run=subprocess.run([sys.executable,'-B',str(root/'release/desktop_mcp.py'),'--config',str(root/'release/workspace.json')],input=raw,capture_output=True,timeout=25,cwd=root)
            self.assertEqual(run.returncode,0,run.stderr.decode('utf8','replace'))
            results={r['id']:r for r in map(json.loads,run.stdout.decode('utf8').splitlines())}
            self.assertEqual(len(results),len(requests)-1)
            self.assertEqual(results[1]['result']['protocolVersion'],'2025-11-25')
            self.assertEqual(len(results[2]['result']['tools']),10)
            self.assertEqual(json.loads(results[3]['result']['contents'][0]['text'])['openapi'],'3.1.0')
            for i in [10,11,12,14,15,16,17,18,19,20,21]:
                self.assertFalse(results[i]['result']['isError'],results[i])
                name=operations[i-10][0]
                contract.validate(results[i]['result']['structuredContent'],contract.OUTPUTS[name],'result')
            self.assertTrue(results[13]['result']['isError']);self.assertTrue(results[22]['result']['isError'])
            self.assertIn('revision_conflict',results[13]['result']['content'][0]['text'])
            self.assertEqual(results[14]['result']['structuredContent']['project']['status'],'质控完成')
            self.assertEqual(results[14]['result']['structuredContent']['project']['addresses'][0]['ssh_alias'],'backup-host')
            self.assertEqual(results[17]['result']['structuredContent']['projects'],[])
            self.assertFalse(results[18]['result']['structuredContent']['project']['archived'])
            self.assertEqual(results[20]['result']['structuredContent']['threads'][0]['title'],'测试关联')
            self.assertEqual(results[15]['result']['structuredContent']['basis']['type'],'registered_metadata')
            # The extracted web adapter must also import successfully, without the original checkout.
            run=subprocess.run([sys.executable,'-B',str(root/'release/desktop_server.py'),'--help'],capture_output=True,timeout=10,cwd=root)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_http_routes_have_matching_tool_contracts(self):
        doc=contract.openapi()
        for method,path,name in contract.ROUTES:
            actual=path.replace('{project_id}','study-1')
            match=contract.route(method,actual)
            self.assertEqual(match[0],name);self.assertEqual(doc['paths'][path][method]['operationId'],name)
        self.assertIsNone(contract.route('GET','/api/v1/projects/study/unknown'))

    def test_two_mcp_processes_cannot_overwrite_same_revision(self):
        with tempfile.TemporaryDirectory(prefix='ai4s-race-') as temp:
            root=pathlib.Path(temp);manage.init(root/'workspace');config=root/'workspace/workspace.json'
            command=[sys.executable,'-B',str(rt.APP_DIR/'desktop_mcp.py'),'--config',str(config)]
            processes=[subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
            for i,p in enumerate(processes):
                messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'race','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'project_create','arguments':{'expected_revision':0,'project':{'id':'study'+str(i),'name':'研究项目'}}}}]
                p.stdin.write((''.join(json.dumps(m)+'\n' for m in messages)).encode());p.stdin.close();p.stdin=None
            outputs=[p.communicate(timeout=15) for p in processes]
            results=[json.loads(o[0].decode().splitlines()[-1])['result']['isError'] for o in outputs]
            self.assertEqual(sorted(results),[False,True])
            saved=rt.read_json(root/'workspace/data/desktop_projects.json');self.assertEqual(saved['revision'],1);self.assertEqual(len(saved['projects']),1)

if __name__=='__main__':unittest.main()
