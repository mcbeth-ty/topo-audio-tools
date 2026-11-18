"""Regression: large Saved libraries mount once and synthesize only on demand."""
from unittest import TestCase
from unittest.mock import patch
import ambient_saved as saved


class SavedRowsTests(TestCase):
    def test_pagination_boundaries(self):
        records=list(range(520))
        page,current,pages=saved.saved_page(records,1,50)
        self.assertEqual((len(page),current,pages),(50,1,11))
        self.assertEqual(saved.saved_page(records,11,50),(list(range(500,520)),11,11))
        self.assertEqual(saved.saved_page(records,99,50)[1:],(11,11))
        self.assertEqual(saved.saved_page([],10,50),([],1,1))
        self.assertEqual(saved.saved_page(records,3,25)[0],list(range(50,75)))

    def test_large_library_is_one_component_with_lazy_playback(self):
        records=[dict(saved_id=f'{i:032x}',status='saved',notes='',favorite=False,
                      metadata={'rendering':{'duration_seconds':15,'timbre':'Warm Pad'}}) for i in range(520)]
        captured={}
        def mount(**kwargs):captured.update(kwargs)
        state={}
        with patch.object(saved.st,'session_state',state), \
             patch.object(saved,'_registered_library_rows',return_value=mount) as register, \
             patch.object(saved,'reconstruct',return_value=b'exact-wav') as renderer, \
             patch.object(saved,'audio_url',return_value='test-audio-url'):
            saved.render_library_rows(records,{},False,'saved-epoch',None)
            self.assertEqual(register.call_count,1)
            self.assertEqual(len(captured['data']['rows']),520)
            self.assertIsNone(captured['data']['audio'])
            renderer.assert_not_called()
            state['ambient_saved_rows']={'event':{'kind':'play','id':records[0]['saved_id']}}
            captured['on_event_change']()
            renderer.assert_called_once_with(records[0]['metadata'],None)
            saved.render_library_rows(records,{},False,'saved-epoch',None)
            self.assertEqual(captured['data']['audio']['url'],'test-audio-url')
            self.assertEqual(captured['data']['audio']['id'],records[0]['saved_id'])
            renderer.assert_called_once()
            state['ambient_saved_rows']={'event':{'kind':'play','id':'unknown'}}
            captured['on_event_change']();renderer.assert_called_once()

    def test_read_only_candidate_events_allow_only_playback(self):
        record=dict(saved_id='a'*32,status='saved',notes='',metadata={'rendering':{'duration_seconds':15,'timbre':'Warm Pad'}})
        captured={};state={}
        with patch.object(saved.st,'session_state',state), \
             patch.object(saved,'_registered_library_rows',return_value=lambda **kwargs:captured.update(kwargs)), \
             patch.object(saved,'reconstruct',return_value=b'candidate-wav') as renderer, \
             patch.object(saved.library,'set_favorite') as favorite,patch.object(saved.library,'set_tag') as tag:
            saved.render_library_rows([record],{},False,'candidate-epoch',None,key='candidate-list',read_only=True)
            self.assertTrue(captured['data']['read_only'])
            state['candidate-list']={'event':{'kind':'favorite','id':record['saved_id'],'value':True}}
            captured['on_event_change']();favorite.assert_not_called()
            state['candidate-list']={'tag':{'id':record['saved_id'],'value':'no editing'}}
            captured['on_tag_change']();tag.assert_not_called()
            state['candidate-list']={'event':{'kind':'play','id':record['saved_id']}}
            captured['on_event_change']();renderer.assert_called_once()
            self.assertEqual(state['candidate-list_audio'],(record['saved_id'],b'candidate-wav'))
            self.assertNotIn('ambient_library_audio',state)

    def test_flags_tags_and_membership_are_preserved_in_rows(self):
        captured={}
        record=dict(saved_id='a'*32,status='bypassed',notes='',favorite=True,
                    metadata={'rendering':{'duration_seconds':15,'timbre':'Warm Pad'}})
        usage={record['saved_id']:{'studies':[{'name':'Study 1'}],'trials':8,'tags':['contemplative']}}
        with patch.object(saved.st,'session_state',{}), \
             patch.object(saved,'_registered_library_rows',return_value=lambda **kwargs:captured.update(kwargs)):
            saved.render_library_rows([record],usage,False,'saved-epoch',None)
        row=captured['data']['rows'][0]
        self.assertTrue(row['protected']);self.assertTrue(row['favorite'])
        self.assertEqual((row['status'],row['tag'],row['studies'],row['trials']),('bypassed','contemplative',1,8))
