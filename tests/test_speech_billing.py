import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from backend.providers import ProviderError, problem
from backend.pipeline import run_job


class SpeechBillingTests(unittest.TestCase):
    def test_generic_402_does_not_assert_balance_is_empty(self):
        error = str(problem(402, '语音合成'))
        self.assertIn('计费请求被拒绝', error)
        self.assertNotIn('账户额度不足', error)

    def test_speech_failure_preserves_storyboard_before_calling_tts(self):
        quote = 'The method changes model outputs using a compact update.'
        method = {'paper_title': 'Offline paper', 'claims': [{'claim': 'Compact update', 'source_pages': [1], 'evidence_quote': quote}], 'example_plan': None}
        scene = {'title': 'Method', 'narration': 'Test narration', 'visual_type': 'flow', 'source_pages': [1]}
        storyboard = {'title': 'Offline plan', 'scenes': [scene]}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch('backend.pipeline.read_paper', return_value=([{'page': 1, 'text': quote}], [], [])), patch('backend.pipeline.chat_json', return_value=method), patch('backend.pipeline.plan_scenes', return_value=storyboard), patch('backend.pipeline.synthesize', side_effect=ProviderError('Test billing failure')):
                with self.assertRaises(ProviderError):
                    run_job({'is_demo': False, 'language': 'zh', 'duration': 60}, folder, lambda **changes: None)
            self.assertEqual(json.loads((folder/'storyboard-plan.json').read_text()), storyboard)
            self.assertTrue((folder/'method.json').exists())


if __name__ == '__main__':
    unittest.main()
