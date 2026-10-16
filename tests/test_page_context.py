import unittest
from course_notes.page_context import delta_visuals,page_signature,representative


class PageContextTests(unittest.TestCase):
    def test_same_page_text_inherited_but_changed_signs_and_reversion_retained(self):
        baseline=list(range(1,13))
        frames=[{'id':'a','line_ids':baseline,'formula_ids':[1]},
                {'id':'b','line_ids':baseline,'formula_ids':[2]},
                {'id':'c','line_ids':baseline,'formula_ids':[1]},
                {'id':'d','line_ids':baseline[:-1]+[13],'formula_ids':[1]}]
        output=delta_visuals(frames)
        self.assertEqual(output[1]['page_delta']['base_visual_id'],'a')
        self.assertEqual(output[1]['formula_ids'],[2])
        self.assertEqual(output[2]['formula_ids'],[1])
        self.assertEqual(output[3]['line_ids'],baseline[:-1]+[13])
        self.assertNotIn('page_delta',frames[1])
    def test_reordering_and_sparse_text_are_not_removed(self):
        frames=[{'id':'a','line_ids':list(range(10))},
                {'id':'b','line_ids':list(reversed(range(10)))},
                {'id':'c','line_ids':[1]}]
        self.assertEqual(delta_visuals(frames),frames)
    def test_exact_page_signature_distinguishes_math_sign(self):
        self.assertNotEqual(page_signature({'ocr_text':'x=-1'}),page_signature({'ocr_text':'x=1'}))
        self.assertEqual(page_signature({'ocr_text':'x=1'}),page_signature({'ocr_text':'x=1'}))
    def test_representative_prefers_useful_full_page(self):
        blank={'id':'a','ocr_text':'='};full={'id':'b','ocr_text':'牛顿第二定律\nF=ma\n加速度与合力'}
        self.assertEqual(representative([blank,full])['id'],'b')
