"""Folder organization must preserve tasks and support conflict-aware undo."""
import copy
import pathlib
import tempfile
import unittest

import desktop_manage as manage
import desktop_runtime as rt
import desktop_services as service
import desktop_state as state


class FolderOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ai4s-folder-')
        self.root = pathlib.Path(self.tmp.name) / 'workspace'
        manage.init(self.root)
        rt.configure(self.root / 'workspace.json')
        def card(id, folder='', kind='folder'):
            return dict(id=id, title=id, type=kind, target=str(self.root) if kind=='directory' else '', folder=folder, zone='inbox', x=0, y=0)
        self.original = dict(revision=4, cards=[card('f'),card('g'),card('a','f','directory'),card('b','f','directory'),card('c','g','directory')],
                             todos=[dict(id='task',title='Keep this task',date='2026-11-25',card='a',done=False)],saved_at=None)
        rt.write_json(state.state_path(), self.original)

    def tearDown(self):
        rt.configure()
        self.tmp.cleanup()

    def test_old_read_does_not_write_and_reorder_undo_preserves_later_title(self):
        raw = state.state_path().read_bytes()
        before = state.read()
        self.assertEqual(raw,state.state_path().read_bytes())
        changed = copy.deepcopy(before)
        changed['cards'][2]['order']=1
        changed['cards'][3]['order']=0
        saved=state.save(changed)
        self.assertEqual(saved['todos'],before['todos'])
        self.assertEqual(saved['cards'][4],before['cards'][4])
        history=service.execute('history_list',{})
        entry=history['entries'][0]['id']
        service.execute('card_update',{'card_id':'a','patch':{'title':'Renamed later'},'expected_revision':saved['revision']})
        service.execute('history_undo',{'entry_id':entry,'expected_revision':service.execute('history_list',{})['revision']})
        cards={c['id']:c for c in state.read()['cards']}
        self.assertNotIn('order',cards['a'])
        self.assertNotIn('order',cards['b'])
        self.assertEqual(cards['a']['title'],'Renamed later')
        self.assertEqual(state.read()['todos'],before['todos'])

    def test_stale_order_does_not_overwrite_another_client(self):
        stale=state.read()
        service.execute('card_update',{'card_id':'a','patch':{'order':5},'expected_revision':4})
        raw=state.state_path().read_bytes()
        stale['cards'][3]['order']=0
        self.assertIsNone(state.save(stale))
        self.assertEqual(raw,state.state_path().read_bytes())

    def test_order_validation_on_both_write_paths(self):
        for value in [True,-1,0.5,1000001,'2',None]:
            with self.subTest(value=value):
                doc=state.read();doc['cards'][2]['order']=value
                with self.assertRaises(ValueError):state.save(doc)
                with self.assertRaises(ValueError):service.execute('card_update',{'card_id':'a','patch':{'order':value},'expected_revision':4})
                self.assertEqual(state.read()['revision'],4)

    def test_move_resets_old_rank_and_preserves_navigation_and_task(self):
        result=service.execute('card_update',{'card_id':'a','patch':{'order':0},'expected_revision':4})
        result=service.execute('card_update',{'card_id':'a','patch':{'folder':'g'},'expected_revision':result['revision']})
        self.assertNotIn('order',result['card'])
        self.assertEqual(result['card']['target'],str(self.root))
        self.assertEqual(state.read()['todos'][0]['card'],'a')


if __name__=='__main__':unittest.main()
