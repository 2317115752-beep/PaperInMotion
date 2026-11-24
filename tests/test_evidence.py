"""Offline regressions for source-backed evidence; never call model APIs."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from backend.pipeline import (
    build_evidence_excerpts, compile_storyboard, normalize_source_text, plan_scenes, run_job, verify_sources,
)


class EvidenceSourceTests(unittest.TestCase):
    def test_generic_visual_beats_follow_bounded_distinct_narration_cues(self):
        pages = [{'page': 1, 'text': 'The experiment isolates the effect of two independent changes.'}]
        scene = {'title': '结果解读', 'narration': '交代基线。检查数据。改变第一项。比较结果。'
                 '控制其它因素。改变第二项。比较输出。说明局限。', 'evidence_ids': ['p1-e1']}
        labels = ['基线', '数据', '第一项', '初次对照', '控制因素', '第二项', '输出', '局限']
        plan = {'title': '控制变量', 'scenes': [
            {**scene, 'visual_beats': [
                {'cue': index, 'label': f' {labels[index]} '} for index in range(7, -1, -1)
            ]},
            {**scene, 'visual_beats': [
                {'cue': 4, 'label': '控制因素'},
                {'cue': 4, 'label': '重复时间'},
                {'cue': 2, 'label': '第一项'},
                {'cue': 8, 'label': '旁白中没有此句'},
                {'cue': True, 'label': '错误类型'},
                {'cue': 1, 'label': ' '},
                {'cue': -1, 'label': '错误序号'},
                {'cue': 0, 'label': '长' * 57},
            ]},
            {**scene, 'visual_beats': {'cue': 1, 'label': '错误容器'}},
        ]}
        scenes = compile_storyboard(plan, None, pages, 'zh')['scenes']
        self.assertEqual(scenes[0]['visual_beats'], [
            {'cue': index, 'label': label} for index, label in enumerate(labels[:6])
        ])
        self.assertEqual(scenes[1]['visual_beats'], [
            {'cue': 2, 'label': '第一项'}, {'cue': 4, 'label': '控制因素'},
        ])
        self.assertNotIn('visual_beats', scenes[2])

    def test_cliff_demonstrations_require_the_source_paper_and_compatible_scenes(self):
        pages = [{'page': 1, 'text': 'CLIFF: Carrying Location Information in Full Frames into Human\n'
                  'Pose and Shape Estimation. Cropped person images are encoded as appearance features.'}]
        scene = {'title': 'Follow the pose estimation pipeline', 'narration': 'First encode the crop.',
                 'visual_type': 'flow', 'evidence_ids': ['p1-e1']}
        raw = {'title': 'Pose estimation', 'scenes': [
            {**scene, 'visual_demo': 'crop-encode'},
            {**scene, 'visual_demo': 'crop-encode'},
            {**scene, 'visual_demo': 'reprojection', 'visual_type': 'title'},
            {**scene, 'visual_demo': 'unknown-demo'},
        ]}
        other_paper = [{'page': 1, 'text': 'Image features are estimated from the input image.'},
                       {'page': 2, 'text': pages[0]['text']}]
        with patch('backend.pipeline.chat_json', return_value=raw) as model:
            scenes = plan_scenes({}, None, 'en', 60, pages)['scenes']
            self.assertIn('crop-encode', model.call_args.args[0])
            self.assertEqual(scenes[0]['visual_demo'], 'crop-encode')
            self.assertTrue(all('visual_demo' not in item for item in scenes[1:]))

            scenes = plan_scenes({}, None, 'en', 60, other_paper)['scenes']
            self.assertNotIn('crop-encode', model.call_args.args[0])
            self.assertTrue(all('visual_demo' not in item for item in scenes))

    def test_scene_layouts_vary_repeated_visuals_after_compilation(self):
        figure = {'id': 'p1-figure1', 'kind': 'figure', 'file': 'assets/p1-figure1.png',
                  'caption': 'Figure 1. A sequence of inputs and outputs'}
        pages = [{'page': 1, 'text': 'The figure documents the inputs and outputs of each operation.',
                  'assets': [figure]}]
        scene = {'title': 'Follow the method', 'narration': 'Start with the input. Track the output.',
                 'evidence_ids': ['p1-e1']}
        figure_scene = {**scene, 'visual_type': 'figure', 'visual_id': figure['id']}
        plan = {'title': 'Inputs and outputs', 'scenes': [
            {**scene, 'visual_type': 'flow', 'layout': ' BRANCH '},
            {**scene, 'visual_type': 'flow', 'layout': 'branch'},
            {**scene, 'visual_type': 'matrix', 'layout': {'unknown': 'shape'}},
            {**scene, 'visual_type': 'bullets', 'nodes': ['Input', 'Output'], 'layout': 'recap'},
            {**scene, 'visual_type': 'flow', 'layout': 'alternating'},
            {**figure_scene, 'layout': 'detail'},
            {**figure_scene, 'layout': 'detail'},
            {**figure_scene, 'layout': 'split'},
            {**figure_scene, 'visual_id': 'missing', 'layout': 'full'},
            {**scene, 'visual_type': 'result', 'layout': 'spotlight'},
            {**scene, 'visual_type': 'equation', 'layout': 'callout', 'formula': 'y = x'},
            {**scene, 'visual_type': 'equation', 'layout': 'callout', 'formula': 'x = y'},
        ]}
        compiled = compile_storyboard(plan, None, pages)['scenes']
        self.assertEqual([item['layout'] for item in compiled], [
            'branch', 'route', 'stack', 'alternating', 'route',
            'detail', 'full', 'split', 'spotlight', 'sequence', 'callout', 'derive',
        ])
        self.assertEqual([item['figure_path'] for item in compiled[5:8]], [figure['file']] * 3)
        self.assertEqual(compiled[8]['visual_type'], 'bullets')
        self.assertNotIn('figure_path', compiled[8])

    def test_storyboard_preserves_supplement_page_and_checks_reference_ids(self):
        pages = [{'page': 102, 'physical_page': 2, 'document': 'Supplement 1',
                  'text': 'The supplement documents the training ablation and its settings.'}]
        scene = {'title': 'Ablation', 'narration': 'The supplement describes the training settings.',
                 'evidence_ids': ['p102-e1']}
        raw = {'title': 'Ablation study', 'scenes': [scene.copy() for _ in range(3)]}
        compiled = compile_storyboard(raw, None, pages)
        evidence = compiled['scenes'][0]['evidence'][0]
        self.assertEqual((evidence['document'], evidence['physical_page']), ('Supplement 1', 2))
        raw['scenes'][1]['evidence_ids'] = ['p402-e1']
        with self.assertRaisesRegex(ValueError, 'Scene 2'):
            compile_storyboard(raw, None, pages)

    def test_executed_example_drives_the_same_values_in_video_and_narration(self):
        pages = [{'page': 4, 'text': 'The low-rank branch adds an update to the frozen layer output.'}]
        example = {'kind': 'low_rank', 'baseline': [1, 2], 'output': [9, -2]}
        scene = {'title': 'LoRA update', 'narration': 'Follow the two branches.',
                 'evidence_ids': ['p4-e1'], 'visual_type': 'matrix'}
        raw = {'title': 'LoRA', 'scenes': [
            {**scene, 'use_example': True},
            {**scene, 'visual_type': 'flow', 'use_example': True},
            {**scene, 'visual_type': 'equation', 'use_example': True},
        ]}
        scenes = compile_storyboard(raw, example, pages)['scenes']
        first = scenes[0]
        self.assertEqual(first['example'], example)
        self.assertIn('baseline result is 1, 2', first['narration'])
        self.assertIn('proposed method gives 9, -2', first['narration'])
        self.assertEqual(first['visual_type'], 'matrix')
        self.assertNotIn('layout', first)
        self.assertEqual([item['visual_type'] for item in scenes], ['matrix', 'flow', 'equation'])
        self.assertTrue(all('example' not in item for item in scenes[1:]))
        chart = first['chart']
        self.assertEqual([point['value'] for point in chart['points']], [1, 9, 2, -2])
        self.assertEqual(chart['source_label'], 'Computed teaching example')

    def test_equation_steps_and_camera_focus_follow_scene_purpose_and_narration(self):
        pages = [{'page': 1, 'text': 'An update is added to the baseline value to calculate the final output.'}]
        equations = [{'label': 'Baseline', 'expression': 'y_0 = W x'},
                     {'label': 'Update', 'expression': 'y = y_0 + d'}]
        scene = {'title': 'Apply the update', 'narration': 'Compute the baseline. Add the update.',
                 'evidence_ids': ['p1-e1']}
        plan = {'title': 'An additive update', 'scenes': [
            {**scene, 'visual_type': 'equation', 'equations': equations, 'focus_cue': 1},
            {**scene, 'visual_type': 'flow', 'equations': equations, 'focus_cue': 1},
            {**scene, 'visual_type': 'title', 'focus_cue': 2},
            {**scene, 'visual_type': 'figure', 'focus_cue': True},
        ]}
        compiled = compile_storyboard(plan, None, pages)['scenes']
        self.assertEqual(compiled[0]['equations'], equations)
        self.assertEqual(compiled[0]['focus_cue'], 1)
        for fallback in compiled[1:]:
            self.assertNotIn('equations', fallback)
            self.assertNotIn('focus_cue', fallback)

    def test_table_chart_copies_data_and_cites_original_table(self):
        asset = {'id': 'p102-table1', 'kind': 'table', 'file': 'assets/p102-table1.png',
                 'caption': 'Table 4. Benchmark results', 'table': {
                     'headers': ['Method', 'Accuracy'],
                     'rows': [['Baseline', '82.40%'], ['Adapter', '85.16%']],
                 }}
        pages = [{'page': 102, 'physical_page': 2, 'document': 'Supplement 1',
                  'text': 'Table 4 reports accuracy measurements from the evaluation.', 'assets': [asset]},
                 {'page': 1, 'text': 'This independent excerpt describes a different part of the study.'}]
        scene = {'title': 'Compare accuracy', 'narration': 'Compare the results in the source table.',
                 'visual_type': 'chart', 'visual_id': asset['id'], 'chart_column': 1,
                 'evidence_ids': ['p102-e1'], 'chart': {'points': [{'label': 'Fake', 'value': 100}]}}
        raw = {'title': 'Benchmark', 'scenes': [scene, {**scene, 'evidence_ids': ['p1-e1']}, scene]}
        compiled = compile_storyboard(raw, None, pages)['scenes']
        self.assertEqual(compiled[0]['visual_type'], 'chart')
        self.assertNotIn('layout', compiled[0])
        self.assertEqual(compiled[0]['chart'], {
            'kind': 'bar', 'title': 'Accuracy', 'unit': '%',
            'source_label': 'Supplement 1 · p. 2 · Table 4',
            'points': [{'label': 'Baseline', 'value': 82.4, 'display_value': '82.40%'},
                       {'label': 'Adapter', 'value': 85.16, 'display_value': '85.16%'}],
        })
        self.assertNotIn('chart', compiled[1])
        for ambiguous in ('0.86 ± 0.02', '85.16', '0.82–0.89', '85.16*'):
            with self.subTest(ambiguous=ambiguous):
                asset['table']['rows'][1][1] = ambiguous
                dropped_chart = compile_storyboard(raw, None, pages)['scenes'][0]
                self.assertEqual(dropped_chart['visual_type'], 'table')
                self.assertNotIn('chart', dropped_chart)

    def test_chinese_pdf_line_wrapping_does_not_reject_a_verbatim_quote(self):
        pages = [{'page': 2, 'text': '为了提高预测精度，本研究引入了遗传算法对多元线性回\n归模型的参数进行优化。'}]
        quote = '遗传算法对多元线性回归模型的参数进行优化'
        method = {'claims': [{'claim': 'Uses genetic optimization.',
                              'source_pages': [2], 'evidence_quote': quote}]}
        verify_sources(method, pages)
        self.assertEqual(method['claims'][0]['source_pages'], [2])
        self.assertTrue(method['claims'][0]['quote_verified'])

    def test_layout_normalization_preserves_words_numbers_negations_and_math(self):
        self.assertEqual(normalize_source_text('The para-\nmeter uses a ﬁxed coef\u00adficient.'),
                         'The parameter uses a fixed coefficient.')
        self.assertEqual(normalize_source_text('We are not\nable to improve 5% at x² − 1.'),
                         'We are not able to improve 5% at x² − 1.')
        self.assertNotEqual(normalize_source_text('We are not able to improve 5%.'),
                            normalize_source_text('We are notable to improve 5%.'))
        self.assertEqual(normalize_source_text('回\n归模\u200b型'), '回归模型')
        self.assertEqual(normalize_source_text('coef\u00ad\nficient'), 'coefficient')

    def test_paraphrases_translations_changed_numbers_and_negation_are_rejected(self):
        source = 'The method does not improve accuracy by 5 percent on this benchmark.'
        quotes = [
            'The method improves accuracy by 5 percent on this benchmark.',
            'The method does not improve accuracy by 50 percent on this benchmark.',
            'The method does not...improve accuracy by 5 percent.',
            'This technique cannot raise benchmark accuracy by five percent.',
            '该方法在此基准上没有将准确率提高百分之五。',
        ]
        for quote in quotes:
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                verify_sources({'claims': [{'claim': 'Unverified.', 'source_pages': [1],
                                            'evidence_quote': quote}]},
                               [{'page': 1, 'text': source}])

    def test_excerpt_registry_is_deterministic_and_owned_by_physical_source_pages(self):
        pages = [
            {'page': 2, 'text': '原文证据必须可以定位。\n' + '遗传算法优化回归参数并改善拟合效果。' * 80},
            {'page': 7, 'text': 'A separate physical page provides another source passage.'},
        ]
        excerpts = build_evidence_excerpts(pages)
        self.assertEqual(excerpts, build_evidence_excerpts(copy.deepcopy(pages)))
        self.assertTrue(excerpts)
        self.assertEqual(len({item['id'] for item in excerpts}), len(excerpts))
        self.assertTrue(any(item['page'] == 7 for item in excerpts))
        indexed = {page['page']: normalize_source_text(page['text']) for page in pages}
        for item in excerpts:
            self.assertRegex(item['id'], rf'^p{item["page"]}-e[1-9][0-9]*$')
            self.assertTrue(item['text'].strip())
            self.assertLessEqual(len(item['text']), 600)
            self.assertIn(item['text'], indexed[item['page']])

    def test_valid_excerpt_id_uses_source_quote_and_page_instead_of_model_copy(self):
        pages = [{'page': 2, 'text': '遗传算法对多元线性回\n归模型的参数进行优化。'}]
        excerpt = build_evidence_excerpts(pages)[0]
        method = {'claims': [{'claim': 'Uses genetic optimization.',
                              'evidence_id': excerpt['id'],
                              'evidence_quote': 'A model-generated paraphrase is not the quote.',
                              'source_pages': [99]}]}
        verify_sources(method, pages)
        verified = method['claims'][0]
        self.assertEqual(verified['evidence_quote'], excerpt['text'])
        self.assertEqual(verified['source_pages'], [2])
        self.assertTrue(verified['quote_verified'])
        self.assertEqual(verified['evidence_id'], excerpt['id'])

    def test_unknown_excerpt_id_is_rejected_even_when_model_also_copies_real_quote(self):
        quote = 'The original source contains a valid and complete passage.'
        for evidence_id in ('p99-e1', 'p2-e1', 'p1-e999', 'invented-evidence'):
            with self.subTest(evidence_id=evidence_id), self.assertRaises(ValueError):
                verify_sources({'claims': [{'claim': 'Cannot validate an invented ID.',
                                            'evidence_id': evidence_id,
                                            'evidence_quote': quote,
                                            'source_pages': [1]}]},
                               [{'page': 1, 'text': quote}])

    def test_exact_quote_can_repair_wrong_page_and_removes_nonmatching_pages(self):
        quote = 'The method learns a compact update to frozen weights.'
        pages = [{'page': 2, 'text': 'An unrelated page with no matching evidence.'},
                 {'page': 7, 'text': quote}]
        for supplied in ([99], [2], [2, 7]):
            with self.subTest(supplied=supplied):
                method = {'claims': [{'claim': 'Learns an update.',
                                      'source_pages': supplied, 'evidence_quote': quote}]}
                verify_sources(method, pages)
                self.assertEqual(method['claims'][0]['source_pages'], [7])
                self.assertTrue(method['claims'][0]['quote_verified'])

    def test_rejected_evidence_writes_diagnostics_before_raising(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'evidence-check.json'
            with self.assertRaises(ValueError) as raised:
                verify_sources({'claims': [{'claim': 'Unverified.',
                                            'evidence_id': 'p999-e1'}]},
                               [{'page': 1, 'text': 'This is the actual source passage for the document.'}],
                               diagnostics_path=report)
            self.assertTrue(report.is_file())
            self.assertIsInstance(json.loads(report.read_text()), (dict, list))
            self.assertNotIn('带可选文本', str(raised.exception))


class EvidenceCheckpointTests(unittest.TestCase):
    def test_invalid_model_evidence_keeps_raw_draft_and_source_registry(self):
        pages = [{'page': 2, 'text': 'A selectable PDF passage supplies valid paper text for this offline check.'}]
        draft = {'paper_title': 'Offline evidence failure', 'claims': [{
            'claim': 'The model supplied an invalid evidence ID.', 'evidence_id': 'p999-e1',
        }], 'example_plan': None}
        job = {'is_demo': False, 'language': 'zh', 'duration': 60}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch('backend.pipeline.read_paper', return_value=(pages, [], [])), \
                 patch('backend.pipeline.chat_json', return_value=copy.deepcopy(draft)) as understand, \
                 patch('backend.pipeline.plan_scenes') as plan, \
                 patch('backend.pipeline.synthesize') as speech:
                with self.assertRaises(ValueError):
                    run_job(job, folder, lambda **changes: None)
            self.assertEqual(json.loads((folder/'method-draft.json').read_text()), draft)
            self.assertTrue((folder/'evidence-excerpts.json').is_file())
            self.assertTrue((folder/'evidence-check.json').is_file())
            self.assertFalse((folder/'method.json').exists())
            self.assertEqual(understand.call_count, 1)
            plan.assert_not_called()
            speech.assert_not_called()


if __name__ == '__main__':
    unittest.main()
