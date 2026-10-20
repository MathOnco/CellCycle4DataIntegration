"""Input policies must select largest source objects or exclude whole fragmented labels."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_fucci_component_inputs import select_inputs
from fucci_analysis.data import aggregate_mask_labels, gates, PHASES


class ComponentInputTests(unittest.TestCase):
    def setUp(self):
        rows=[]
        for i,(label,volume,g,r) in enumerate([('1',10,.01,.02),('1',100,.02,.01),
                                                ('2',50,.02,.008),('3',5,.004,.01),('3',5,.02,.008)]):
            row=dict(mask_label_id='date/1/mask_'+label,object_id=f'date/1/object_{i}',field_id='date/1',
                     folder='folder',Date='date',FoF='1',ImageSet='image',FileName_mask='mask',CellposeLabel=label,
                     volume=volume,green=g,red=r,green_sum=g*volume,red_sum=r*volume,green_gate=.005,red_gate=.009,
                     tiny_object=volume<=8,saturated_voxel=False,green_median=g,red_median=r,green_core=g,red_core=r,
                     cellCycle=PHASES[gates(g,r,.005,.009)])
            for axis in 'xyz': row[axis]=10;row[f'{axis}_min']=9;row[f'{axis}_max']=12
            rows.append(row)
        self.objects=pd.DataFrame(rows)
        self.labels=aggregate_mask_labels(self.objects)

    def test_largest_component_uses_its_actual_measurement_and_stable_tie(self):
        chosen,labels=select_inputs(self.objects,self.labels,'dominant')
        self.assertEqual(chosen.object_id.tolist(),['date/1/object_1','date/1/object_2','date/1/object_3'])
        self.assertEqual(len(labels),3)
        self.assertAlmostEqual(labels.green.iloc[0],.02)
        self.assertEqual(labels.volume.iloc[0],100)
        self.assertEqual(labels.original_mask_volume.iloc[0],110)
        self.assertEqual(labels.original_n_components.iloc[0],2)
        self.assertTrue(labels.n_components.eq(1).all())

    def test_singletons_exclude_entire_fragmented_labels(self):
        chosen,labels=select_inputs(self.objects,self.labels,'singletons')
        self.assertEqual(chosen.object_id.tolist(),['date/1/object_2'])
        self.assertEqual(labels.CellposeLabel.tolist(),['2'])
        self.assertEqual(labels.baseline_phase.tolist(),['G1'])


if __name__=='__main__':unittest.main()
