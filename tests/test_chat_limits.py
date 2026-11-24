"""Offline regressions for output truncation; never contact a provider."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from backend.pipeline import run_job
from backend.providers import ProviderError, chat_json


class ChatLimitTests(unittest.TestCase):
    def settings(self, **overrides):
        return patch.dict(os.environ, {
            'DASHSCOPE_API_KEY': 'sk_unit_test_secret_do_not_log',
            'BAILIAN_WORKSPACE_ID': 'unit-workspace',
            'BAILIAN_ENDPOINT_MODE': 'shared',
            'BAILIAN_CHAT_MODEL': 'qwen3.8-flash',
            'BAILIAN_CHAT_MAX_TOKENS': '12000',
            **overrides,
        })

    @staticmethod
    def response(*, finish_reason='stop', content='{"title":"A compact plan"}', reasoning_content='private reasoning must not be logged'):
        return httpx.Response(200, json={
            'choices': [{'finish_reason': finish_reason, 'message': {
                'content': content, 'reasoning_content': reasoning_content,
            }}],
            'usage': {'prompt_tokens': 123, 'completion_tokens': 456,
                      'completion_tokens_details': {'reasoning_tokens': 321}},
        })

    def test_qwen_request_disables_thinking_and_uses_configured_budget(self):
        with self.settings(BAILIAN_CHAT_MAX_TOKENS='16384'), patch('backend.providers.httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = self.response()
            result = chat_json('Generate a plan.', 'Input data.', task='分镜规划')
        self.assertEqual(result, {'title': 'A compact plan'})
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['max_tokens'], 16384)
        self.assertIs(payload['enable_thinking'], False)
        self.assertNotIn('chat_template_kwargs', payload)
        self.assertEqual(payload['model'], 'qwen3.8-flash')
        self.assertEqual(post.call_args.args[0], 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(post.call_count, 1)

    def test_explicit_output_budget_is_respected(self):
        with self.settings(), patch('backend.providers.httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = self.response()
            chat_json('Plan.', 'Data.', max_tokens=4096)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 4096)

    def test_length_finish_never_accepts_even_parseable_json_or_retries(self):
        with self.settings(), patch('backend.providers.httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = self.response(finish_reason='length', content='{"valid_json":true}')
            with self.assertRaises(ProviderError) as raised:
                chat_json('Plan.', 'Data.', task='分镜规划')
        self.assertIn('分镜规划', str(raised.exception))
        self.assertIn('12000', str(raised.exception).replace(',', ''))
        self.assertEqual(post.call_count, 1, 'Truncation must not silently create more paid requests.')

    def test_read_timeout_records_the_failure_without_resending(self):
        with tempfile.TemporaryDirectory() as temporary, self.settings(), patch('backend.providers.httpx.Client') as client:
            log_path = Path(temporary)/'api.jsonl'
            post = client.return_value.__enter__.return_value.post
            post.side_effect = httpx.ReadTimeout('private transport details')
            with self.assertRaisesRegex(ProviderError, '论文理解.*等待百炼响应超时.*未自动重发'):
                chat_json('Plan.', 'Data.', task='论文理解', diagnostics_path=log_path)
            post.assert_called_once()
            raw = log_path.read_text(encoding='utf-8')
        row = json.loads(raw)
        self.assertEqual(row['transport_error'], 'ReadTimeout')
        self.assertIsNone(row['http_status'])
        self.assertGreaterEqual(row['elapsed_seconds'], 0)
        self.assertNotIn('private transport details', raw)

    def test_invalid_budget_configuration_stops_before_paid_request(self):
        for budget in ('0', '-1', '1023', '32769', 'unlimited', '12000.5'):
            with self.subTest(budget=budget), self.settings(BAILIAN_CHAT_MAX_TOKENS=budget), patch('backend.providers.httpx.Client') as client:
                with self.assertRaises(ProviderError):
                    chat_json('Plan.', 'Data.')
                client.return_value.__enter__.return_value.post.assert_not_called()

    def test_diagnostics_record_usage_without_prompts_response_or_secret(self):
        private_body = '{"title":"private generated title 923473"}'
        private_reasoning = 'private reasoning 298473'
        with tempfile.TemporaryDirectory() as temporary, self.settings(), patch('backend.providers.httpx.Client') as client:
            log_path = Path(temporary)/'api.jsonl'
            client.return_value.__enter__.return_value.post.return_value = self.response(
                finish_reason='length', content=private_body, reasoning_content=private_reasoning)
            with self.assertRaises(ProviderError):
                chat_json('private system prompt 678903', 'private paper text 876343',
                          task='分镜规划', diagnostics_path=log_path)
            raw = log_path.read_text(encoding='utf-8')
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['task'], '分镜规划')
        self.assertEqual(row['max_tokens'], 12000)
        self.assertEqual(row['finish_reason'], 'length')
        self.assertEqual(row['prompt_tokens'], 123)
        self.assertEqual(row['completion_tokens'], 456)
        self.assertEqual(row['reasoning_tokens'], 321)
        self.assertEqual(row['content_chars'], len(private_body))
        self.assertEqual(row['reasoning_chars'], len(private_reasoning))
        self.assertIn('attempt', row)
        for sensitive in ('sk_unit_test_secret_do_not_log', private_body, private_reasoning,
                          'private system prompt 678903', 'private paper text 876343'):
            self.assertNotIn(sensitive, raw)
        self.assertNotIn('Authorization', raw)
        self.assertNotIn('Bearer', raw)


class PlanningCheckpointTests(unittest.TestCase):
    def test_storyboard_failure_preserves_completed_paper_analysis(self):
        quote = 'The method adds a compact trainable update to frozen model weights.'
        pages = [{'page': 1, 'text': quote+' This text is used only by the offline test.'}]
        method = {'paper_title': 'Offline test paper', 'claims': [{
            'claim': 'Adds a compact update.', 'source_pages': [1], 'evidence_quote': quote,
        }], 'example_plan': None}
        job = {'is_demo': False, 'language': 'zh', 'duration': 60}
        updates = []
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch('backend.pipeline.read_paper', return_value=(pages, [], [])), \
                 patch('backend.pipeline.chat_json', return_value=method) as understand, \
                 patch('backend.pipeline.plan_scenes', side_effect=ProviderError('分镜规划输出被截断')) as plan:
                with self.assertRaises(ProviderError):
                    run_job(job, folder, lambda **changes: updates.append(changes))
            checkpoint = folder/'method.json'
            self.assertTrue(checkpoint.is_file(), 'Completed analysis must survive a later planner failure.')
            saved = json.loads(checkpoint.read_text(encoding='utf-8'))
        self.assertEqual(saved['paper_title'], 'Offline test paper')
        self.assertTrue(saved['claims'][0]['quote_verified'])
        self.assertEqual(understand.call_count, 1)
        self.assertEqual(plan.call_count, 1)
        self.assertTrue(any(update.get('stage') == 'storyboard' for update in updates))


if __name__ == '__main__':
    unittest.main()
