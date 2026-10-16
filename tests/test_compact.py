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
        self.assertEqual([x['text'] for x in packed['visuals']],['x=1','x=2','x=1','',''])
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

    def test_long_content_preserved_and_context_not_duplicated(self):
        text='推导不可省略。'*1000
        evidence={'start':0,'end':100,'speech':[{'id':'S1','start':0,'end':1,'text':text}], 'visuals':[], 'context_before':[{'text':'先前定义'}]}
        small=prompt(evidence,'重复十分钟前上下文'*100,True)
        self.assertIn(text,small)
        self.assertEqual(small.count('先前定义'),1)
        self.assertNotIn('十分钟前',small)
