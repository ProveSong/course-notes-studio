import unittest
from course_notes.formula_regions import candidates


class RegionTests(unittest.TestCase):
    def test_adjacent_terms_and_equality_group_but_columns_stay_separate(self):
        regions=[{'text':'x','bbox':[100,200,135,250]},
                 {'text':'=','bbox':[140,200,160,250]},
                 {'text':'y+1','bbox':[165,200,240,250]},
                 {'text':'z=2','bbox':[700,200,800,250]}]
        groups=list(candidates({'ocr_regions':regions}))
        self.assertEqual(len(groups),2)
        self.assertEqual(len(groups[0]['source_boxes']),3)
        self.assertLess(groups[0]['bbox'][2],300)
    def test_overlapping_padded_lines_do_not_chain_into_whole_board(self):
        regions=[{'text':f'x={i}','bbox':[100,100+i*30,250,150+i*30]} for i in range(8)]
        groups=list(candidates({'ocr_regions':regions}))
        self.assertEqual(len(groups),8)
        self.assertTrue(all(g['bbox'][3]-g['bbox'][1]<80 for g in groups))
    def test_empty_large_detection_does_not_bridge_everything(self):
        rows={'ocr_regions':[{'text':'','bbox':[0,0,1000,1000]},
                             {'text':'x=1','bbox':[100,200,200,240]}],
              'formula_regions':[{'bbox':[500,100,900,400],'proposal':'reviewed-box'}]}
        groups=list(candidates(rows))
        self.assertEqual(len(groups),2)
        self.assertLess(groups[0]['bbox'][2],300)
        self.assertEqual(groups[1]['proposal'],'reviewed-box')
