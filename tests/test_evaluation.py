from math import log
import unittest
from collections import Counter

from backend.evaluation import independent_example_checks, measure_cost, revision_delta, timing_checks
from backend.examples import execute_example
from backend.research_examples import execute_research_example
from scripts.research import (
    DEFAULT_CORPUS, batch_plan, corpus, correction_dataset, schedule_viewers, summarize, viewer_scores,
)


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papers = corpus(DEFAULT_CORPUS)

    def test_heldout_ablation_and_balanced_study(self):
        plan = batch_plan(self.papers, 'heldout', 2, 25)
        counts = Counter((row['paper_id'], row['condition']) for row in plan)
        self.assertEqual(len(plan), 24)
        self.assertEqual(len(counts), 12)
        self.assertEqual(set(counts.values()), {2})
        full = schedule_viewers(self.papers, 24, 25)
        self.assertEqual(full['first_condition_counts'], {'A': 12, 'C': 12})
        self.assertEqual(set(full['paper_condition_counts'].values()), {6})
        for participant in full['participants']:
            first, second = participant['clips']
            self.assertNotEqual(first['paper_id'], second['paper_id'])
            self.assertEqual({first['condition'], second['condition']}, {'A', 'C'})

    def test_completed_versions_and_second_scorer_stay_separate(self):
        completed = {
            f'{paper}-A-1' for paper, row in self.papers.items() if row['split'] == 'heldout'
        } | {
            f'{paper}-C-2' for paper, row in self.papers.items() if row['split'] == 'heldout'
        }
        schedule = schedule_viewers(self.papers, 18, 25, completed)
        self.assertTrue(all(clip['attempt_id'] in completed for row in schedule['participants'] for clip in row['clips']))
        participant = schedule['participants'][0]
        primary = [{'participant_id': participant['participant_id'], 'attempt_id': clip['attempt_id'],
                    'scorer': 'R01', 'answers': [2 if clip['condition'] == 'C' else 1] * 6}
                   for clip in participant['clips']]
        secondary = {**primary[0], 'scorer': 'R02', 'answers': [0] * 6}
        report = viewer_scores(schedule, [*primary, secondary], self.papers)
        self.assertEqual(report['paired_comprehension']['C_minus_A_mean'], .5)
        self.assertEqual(report['scorer_agreement']['exact_agreement'], 0)

    def test_heldout_and_unverified_corrections_rejected(self):
        record = {'paper_id': 'lora', 'stage': 'understanding', 'verified': True, 'verified_by': 'R01',
                  'source_evidence': [{'page': 2, 'quote': 'The pretrained weights are frozen.'}],
                  'input': 'source text', 'original': {'state': 'unclear'}, 'revised': {'state': 'frozen'}}
        result, = correction_dataset(self.papers, [record])
        self.assertEqual(result['messages'][-1]['role'], 'assistant')
        for bad in ({**record, 'paper_id': 'resnet'}, {**record, 'verified': False}):
            with self.assertRaises(ValueError):
                list(correction_dataset(self.papers, [bad]))

    def test_summary_distinguishes_calibration_and_incomplete_attempts(self):
        attempts = {
            'paper-A-1': {'paper_id': 'paper', 'condition': 'A', 'status': 'complete'},
            'paper-A-2': {'paper_id': 'paper', 'condition': 'A', 'status': 'failed'},
            'paper-C-1': {'paper_id': 'paper', 'condition': 'C', 'status': 'complete'},
        }
        ratings = [
            {'attempt_id': 'paper-A-1', 'judge': 'human', 'clarity': 3, 'supported_claims': 2, 'checked_claims': 4},
            {'attempt_id': 'paper-A-1', 'judge': 'model', 'clarity': 4},
            {'attempt_id': 'paper-C-1', 'judge': 'human', 'clarity': 5},
        ]
        result = summarize(attempts, ratings)
        self.assertEqual(result['by_paper_and_condition'][0]['completion_rate'], .5)
        self.assertEqual(result['model_judge_calibration']['clarity']['mean_bias'], 1)
        self.assertEqual(result['comparisons'][0]['judge_metric_deltas']['human']['clarity'], 2)

    def test_cost_missing_usage_is_labelled(self):
        result = measure_cost({'prompt_tokens': 2_000_000}, {'prompt_tokens': 4, 'currency': 'CNY'})
        self.assertEqual(result['amount'], 8)
        self.assertIn('speech_output_tokens', result['missing_token_fields'])


class JobEvaluationTests(unittest.TestCase):
    def test_timing_does_not_treat_generated_cues_as_ground_truth(self):
        manifest = {'fps': 20, 'scenes': [{'duration_frames': 20, 'cues': [
            {'start_frame': 0, 'end_frame': 10}, {'start_frame': 9, 'end_frame': 20},
        ], 'beats': [{'start_frame': 4}, {'start_frame': 10, 'expected_spoken_frame': 9}]}]}
        result = timing_checks(manifest)
        self.assertEqual(result['median_absolute_offset_ms'], 50)
        self.assertEqual(result['events_with_independent_spoken_reference'], 1)
        self.assertEqual(result['issues'], [{'scene': 1, 'type': 'cue_bounds_or_overlap'}])

    def test_scalar_checkpoint_detects_wrong_video_example_value(self):
        example = execute_example({'kind': 'low_rank', 'W0': [[1, 0]], 'A': [[0, 1]], 'B': [[2]], 'x': [2, 3]})
        self.assertTrue(all(item['passed'] for item in independent_example_checks(example)))
        example['output'] = [9.]
        self.assertIn({'checkpoint': 'output', 'passed': False}, independent_example_checks(example))

    def test_heldout_examples_match_independent_reference_values(self):
        cases = [
            ({'kind': 'residual_add', 'x': [2, -1], 'residual': [-.5, 3]}, [1.5, 2]),
            ({'kind': 'volume_composite', 'alphas': [.5, .5], 'colors': [.8, .2]}, [.45]),
            ({'kind': 'adam_step', 'weights': [1], 'gradient': [2]}, [.9]),
            ({'kind': 'tiled_softmax', 'scores': [0, log(3)], 'values': [2, 6], 'tile_size': 1}, [5]),
        ]
        for plan, expected in cases:
            with self.subTest(kind=plan['kind']):
                result = execute_research_example(plan)
                for computed, reference in zip(result['output'], expected, strict=True):
                    self.assertAlmostEqual(computed, reference, places=7)
                self.assertTrue(all(row['passed'] for row in result['checkpoints']))

    def test_revision_delta_does_not_claim_unmeasured_usage(self):
        before = {'findings': [{'stage': 'example', 'code': 'calculation_checkpoint'}], 'usage': {'prompt_tokens': 15}}
        after = {'findings': [{'stage': 'production', 'code': 'beat_outside_scene'}], 'usage': {'prompt_tokens': 18}}
        result = revision_delta(before, after)
        self.assertEqual(result['resolved'], before['findings'])
        self.assertEqual(result['introduced'], after['findings'])
        self.assertEqual(result['measured_token_delta']['prompt_tokens'], 3)
        self.assertIsNone(result['measured_token_delta']['speech_input_tokens'])


if __name__ == '__main__':
    unittest.main()
