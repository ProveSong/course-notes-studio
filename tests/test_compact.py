import json,unittest
from course_notes.compact import clean_text,pack,formula_candidate
from course_notes.llm import prompt


class CompactTests(unittest.TestCase):
    def test_broken_model_output_keeps_review_region_without_token_noise(self):
        raw={'latex':'\\overrightarrow'*200,'bbox':[0,0,100,100],'status':'candidate-unverified'}
        packed=formula_candidate(raw)
        self.assertNotIn('latex',packed)
        self.assertEqual(packed['bbox'],raw['bbox'])
        self.assertEqual(packed['status'],'needs-visual-review')
        self.assertEqual(len(raw['latex']),len('\\overrightarrow')*200)
        valid={'latex':'\\frac{a+b}{c}','bbox':[0,0,100,100],'status':'candidate-unverified'}
        self.assertEqual(formula_candidate(valid)['latex'],valid['latex'])
    def test_noise_removed_but_question_and_aside_retained(self):
        self.assertEqual(clean_text('继续播放 不知道。\nCopyright 2024 publisher\n不知道为什么这个集合没有上确界？\n老师讲了猜考题的玩笑。'),
                         '不知道为什么这个集合没有上确界？\n老师讲了猜考题的玩笑。')

    def test_visual_changes_reversions_and_blank_frames_not_lost(self):
        evidence={'start':0,'end':100,'speech':[], 'visuals':[
            {'id':str(i),'time':i,'ocr_text':text,'ocr_warning':'redundant diagnostic'}
            for i,text in enumerate(['x=1','x=1','x=2','x=1','',''])]}
        packed,audit=pack(evidence)
        self.assertEqual(['\n'.join(packed.get('ocr_lines',[])[i-1] for i in x['line_ids']) for x in packed['visuals']],['x=1','x=2','x=1','',''])
        self.assertNotIn('alternates',packed['visuals'][0])
        self.assertEqual(audit['visual_aliases'],{'1':'0'})
        self.assertNotIn('ocr_warning',json.dumps(packed))

    def test_formula_coordinates_and_duplicate_candidates_stay_local(self):
        formulas=[{'latex':'x+y','bbox':[i,0,i+2,2],'confidence':0.7,'status':'candidate-unverified'} for i in range(30)]
        evidence={'start':0,'end':10,'visuals':[
            {'id':'V1','time':0,'ocr_text':'方程','local_formulas':formulas},
            {'id':'V2','time':5,'ocr_text':'方程','local_formulas':[dict(f,bbox=[9,9,10,10]) for f in formulas]}]}
        packed,audit=pack(evidence)
        self.assertEqual(packed['formula_candidates'],['x+y'])
        self.assertEqual(packed['visuals'][0]['formula_ids'],[1])
        self.assertEqual(audit['visual_aliases'],{'V2':'V1'})
        self.assertEqual(len(formulas),30)
        self.assertNotIn('bbox',json.dumps(packed))

    def test_watermark_fragments_and_overlay_removed_with_local_audit(self):
        from course_notes.input_cleaner import clean_visual
        regions=[{'text':'11:43','bbox':[794,0,822,26]},
                 {'text':'乱字','bbox':[756,32,805,68]},
                 {'text':'茶','bbox':[57,57,97,127]},
                 {'text':'1898','bbox':[61,109,93,145]},
                 {'text':'向心力','bbox':[200,300,400,360]},
                 {'text':'F=mω²r','bbox':[200,400,400,460]},
                 {'text':'课堂教学视频受知识产权保护，未经某大学报权，不得翻录转载，违者追究法律责任!','bbox':[6,936,710,997]}]
        raw='\n'.join(r['text'] for r in regions)
        item={'ocr_text':raw,'ocr_regions':regions}
        text,audit=clean_visual(item)
        self.assertEqual(text,'向心力\nF=mω²r')
        self.assertEqual(item['ocr_text'],raw)
        self.assertEqual({a['reason'] for a in audit},{'player-overlay','institution-emblem','watermark-or-empty'})
        self.assertEqual(clean_text('向心力\n，违者追究法律责任!'),'向心力')

    def test_line_pool_preserves_signs_numbers_changes_and_reversions(self):
        evidence={'start':0,'end':30,'visuals':[
            {'id':f'V{i}','time':i*5,'ocr_text':text} for i,text in enumerate([
                '共同定义\nF=1N','共同 定义\nF=2N','共同定义\nF=-2N','共同定义\nF=1N'])]}
        packed,_=pack(evidence)
        self.assertEqual(packed['ocr_lines'],['共同定义','F=1N','F=2N','F=-2N'])
        self.assertEqual(packed['visuals'][0]['line_ids'],packed['visuals'][-1]['line_ids'])
        self.assertEqual(len(packed['visuals']),4)

    def test_incomplete_regions_do_not_silently_drop_ocr_text(self):
        from course_notes.input_cleaner import clean_visual
        item={'ocr_text':'能量 E=12J\n角度 θ=30°','ocr_regions':[{'text':'能量 E=12J','bbox':[50,100,200,200]}]}
        text,_=clean_visual(item)
        self.assertIn('θ=30°',text)

    def test_unit_spacing_is_not_treated_as_ocr_noise(self):
        from course_notes.input_cleaner import line_key
        self.assertNotEqual(line_key('m s'),line_key('ms'))
        self.assertNotEqual(line_key('F=-2N'),line_key('F=2N'))

    def test_long_content_preserved_and_context_not_duplicated(self):
        text='推导不可省略。'*1000
        evidence={'start':0,'end':100,'speech':[{'id':'S1','start':0,'end':1,'text':text}], 'visuals':[], 'context_before':[{'text':'先前定义'}]}
        small=prompt(evidence,'重复十分钟前上下文'*100,True)
        self.assertIn(text,small)
        self.assertEqual(small.count('先前定义'),1)
        self.assertNotIn('十分钟前',small)
