"""Offline regressions for source-backed evidence; never call model APIs."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from backend.pipeline import (
    build_evidence_excerpts, normalize_source_text, run_job, verify_sources,
)


class EvidenceSourceTests(unittest.TestCase):
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
