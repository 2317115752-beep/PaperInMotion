import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.pipeline import render


class RenderErrorTests(TestCase):
    def test_browser_exit_shows_phase_and_last_renderer_reason(self):
        events = [
            {'event': 'render_error', 'phase': 'preview', 'message': 'Previous attempt'},
            {'event': 'render_progress', 'percent': 20},
            {'event': 'render_error', 'phase': 'encoding', 'message': 'Protocol error: Target closed'},
        ]
        output = [json.dumps(event) + '\n' for event in events]
        with TemporaryDirectory() as temporary, patch('backend.pipeline.subprocess.Popen') as popen:
            process = popen.return_value
            process.stdout = iter(output)
            process.wait.return_value = 1
            folder = Path(temporary)
            update = Mock()

            with self.assertRaises(ValueError) as failure:
                render(folder / 'manifest.json', folder / 'video.mp4', update)

            self.assertIn('渲染浏览器意外退出（渲染并编码视频）', str(failure.exception))
            self.assertIn('Protocol error: Target closed', str(failure.exception))
            self.assertEqual((folder / 'render.log').read_text(encoding='utf-8'), ''.join(output))
            update.assert_called_once_with(stage='rendering', progress=82, message='正在渲染：20%')

    def test_structured_error_redacts_credentials_and_truncates_reason(self):
        secret = 'renderer-test-credential'
        event = {'event': 'render_error', 'phase': 'bundle', 'message': f'Could not prepare assets {secret}\n' + 'x' * 1000}
        with (
            TemporaryDirectory() as temporary,
            patch.dict('os.environ', {'DASHSCOPE_API_KEY': secret}),
            patch('backend.pipeline.subprocess.Popen') as popen,
        ):
            popen.return_value.stdout = iter([json.dumps(event) + '\n'])
            popen.return_value.wait.return_value = 1
            folder = Path(temporary)

            with self.assertRaises(ValueError) as failure:
                render(folder / 'manifest.json', folder / 'video.mp4', Mock())

            message = str(failure.exception)
            self.assertIn('打包渲染资源', message)
            self.assertIn('[redacted]', message)
            self.assertNotIn(secret, message)
            self.assertLess(len(message), 450)

    def test_unstructured_node_failure_keeps_the_log_reference(self):
        with TemporaryDirectory() as temporary, patch('backend.pipeline.subprocess.Popen') as popen:
            popen.return_value.stdout = iter(['Node startup failed\n', 'null\n'])
            popen.return_value.wait.return_value = 1
            folder = Path(temporary)

            with self.assertRaisesRegex(ValueError, r'render\.log.*Node'):
                render(folder / 'manifest.json', folder / 'video.mp4', Mock())
