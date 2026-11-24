"""Exercise Bailian HTTP contracts offline; no requests leave MockTransport."""
import base64
from contextlib import contextmanager
import io
import json
import os
import struct
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

import httpx

from backend.providers import ProviderError, api_base, chat_json, get_config, synthesize


WORKSPACE = 'unit-workspace'
SECRET = 'sk-unit-test-key-never-log'
API_HOST = 'dashscope.aliyuncs.com'
AUDIO_HOST = 'dashscope-result-bj.oss-cn-beijing.aliyuncs.com'
AUDIO_URL = f'https://{AUDIO_HOST}/pre/test/audio.wav?signature=private-signed-value'
REAL_CLIENT = httpx.Client


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\0\0' * 12000)
    return stream.getvalue()


def speech_result(url=AUDIO_URL, **audio_fields):
    return {'request_id': 'offline-request-id', 'output': {
        'finish_reason': 'stop', 'audio': {
            'url': url, 'expires_at': int(time.time()) + 3600, **audio_fields,
        }}, 'usage': {'input_tokens': 5, 'output_tokens': 12}}


@contextmanager
def settings(**overrides):
    with patch.dict(os.environ, {
        'DASHSCOPE_API_KEY': SECRET,
        'BAILIAN_WORKSPACE_ID': WORKSPACE,
        'BAILIAN_ENDPOINT_MODE': 'shared',
        'BAILIAN_CHAT_MODEL': 'qwen3.8-flash',
        'BAILIAN_TTS_MODEL': 'qwen-audio-3.1-tts-flash',
        'BAILIAN_CHAT_MAX_TOKENS': '12000',
        'BAILIAN_TTS_VOICE_ZH': 'loongbella_v3.1',
        'BAILIAN_TTS_VOICE_EN': 'loongbella_v3.1',
        **overrides,
    }):
        yield


@contextmanager
def transport(handler):
    def client(*args, **kwargs):
        return REAL_CLIENT(*args, **kwargs, transport=httpx.MockTransport(handler))
    with patch('backend.providers.httpx.Client', side_effect=client):
        yield


class BailianProviderTests(unittest.TestCase):
    def test_punctuation_only_speech_input_is_rejected_before_request(self):
        with settings(), patch('backend.providers.httpx.Client') as client:
            with self.assertRaisesRegex(ProviderError, '配音文字或语言无效'):
                synthesize(' 。！？ ', 'zh', Path('unused.wav'), streaming=True)
            client.assert_not_called()

    def test_streamed_audio_is_validated_without_downloading_the_temporary_url(self):
        audio = wav_bytes()
        results = [
            {'output': {'type': 'sentence-synthesis',
                        'audio': {'data': base64.b64encode(chunk).decode()}}}
            for chunk in (audio[:57], audio[57:])
        ]
        final = {'request_id': 'speech-stream-test',
                 'output': {'finish_reason': 'stop', 'audio': {'url': AUDIO_URL}},
                 'usage': {'input_tokens': 2, 'output_tokens': 10}}
        seen = []

        def handle(request):
            seen.append(request.method)
            self.assertEqual(request.headers['x-dashscope-sse'], 'enable')
            body = ''.join('data: ' + json.dumps(result) + '\n\n' for result in [*results, final])
            return httpx.Response(200, text=body, headers={'content-type': 'text/event-stream'})

        with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/'speech.wav'
            logs = Path(temporary)/'calls.jsonl'
            self.assertEqual(synthesize('Streaming test.', 'en', target, streaming=True, diagnostics_path=logs), .5)
            self.assertEqual(target.read_bytes(), audio)
            self.assertEqual(json.loads(logs.read_text())['speech_output_tokens'], 10)
        self.assertEqual(seen, ['POST'])

    def test_interrupted_stream_leaves_no_audio_checkpoint(self):
        def handle(request):
            item = {'output': {'type': 'sentence-synthesis',
                               'audio': {'data': base64.b64encode(wav_bytes()).decode()}}}
            return httpx.Response(200, text='data: ' + json.dumps(item) + '\n\n')

        with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/'speech.wav'
            with self.assertRaises(ProviderError):
                synthesize('Interrupted stream.', 'en', target, streaming=True)
            self.assertFalse(target.exists())

    def test_tts_contract_both_languages_and_download_never_receives_auth_or_cookie(self):
        for language, text in [('zh', '欢迎学习这篇论文。'), ('en', 'Welcome to this paper lesson.')]:
            with self.subTest(language=language):
                requests = []
                def handle(request):
                    requests.append(request)
                    if request.method == 'POST':
                        self.assertEqual(str(request.url), f'https://{API_HOST}/api/v1/services/audio/tts/SpeechSynthesizer')
                        self.assertEqual(request.headers['authorization'], f'Bearer {SECRET}')
                        payload = json.loads(request.content)
                        self.assertEqual(payload['model'], 'qwen-audio-3.1-tts-flash')
                        self.assertEqual(payload['input']['text'], text)
                        self.assertEqual(payload['input']['voice'], 'loongbella_v3.1')
                        self.assertEqual(payload['input']['language_hints'], [language])
                        self.assertEqual(payload['input']['format'], 'wav')
                        self.assertEqual(payload['input']['sample_rate'], 24000)
                        # A wide cookie domain must not carry from API to asset download.
                        return httpx.Response(200, json=speech_result(), headers={
                            'set-cookie': 'api_session=private; Domain=.aliyuncs.com; Path=/; Secure'})
                    self.assertEqual(request.method, 'GET')
                    self.assertEqual(str(request.url), AUDIO_URL)
                    self.assertNotIn('authorization', request.headers)
                    self.assertNotIn('cookie', request.headers)
                    return httpx.Response(200, content=wav_bytes(), headers={'content-type': 'audio/wav'})
                with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary)/'speech.wav'
                    self.assertEqual(synthesize(text, language, output), .5)
                    self.assertEqual(output.read_bytes(), wav_bytes())
                self.assertEqual(len(requests), 2)

    def test_documented_http_oss_url_is_upgraded_to_https(self):
        urls = []
        def handle(request):
            urls.append(str(request.url))
            if request.method == 'POST':
                return httpx.Response(200, json=speech_result(AUDIO_URL.replace('https:', 'http:')))
            return httpx.Response(200, content=wav_bytes())
        with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
            synthesize('Test', 'en', Path(temporary)/'speech.wav')
        self.assertEqual(urls[-1], AUDIO_URL)

    def test_missing_key_or_invalid_explicit_endpoint_config_stops_before_http(self):
        for overrides in ({'DASHSCOPE_API_KEY': ''},
                          {'BAILIAN_ENDPOINT_MODE': 'invalid'},
                          {'BAILIAN_ENDPOINT_MODE': 'https://example.com'},
                          {'BAILIAN_ENDPOINT_MODE': 'workspace', 'BAILIAN_WORKSPACE_ID': ''},
                          {'BAILIAN_ENDPOINT_MODE': 'workspace', 'BAILIAN_WORKSPACE_ID': 'unit.example/path'},
                          {'BAILIAN_ENDPOINT_MODE': 'workspace', 'BAILIAN_WORKSPACE_ID': '../127.0.0.1'}):
            with self.subTest(overrides=overrides), settings(**overrides), patch('backend.providers.httpx.Client') as client:
                for operation in (lambda: chat_json('JSON', 'Test'),
                                  lambda: synthesize('Test', 'en', Path('/tmp/unused-bailian-test.wav'))):
                    with self.assertRaises(ProviderError):
                        operation()
                client.assert_not_called()

    def test_shared_endpoint_requires_only_key_and_ignores_unused_workspace_id(self):
        for workspace in ('', '1234567', 'unit.example/path', '../127.0.0.1'):
            with self.subTest(workspace=workspace), settings(BAILIAN_WORKSPACE_ID=workspace):
                config = get_config()
                self.assertEqual(config['endpoint_mode'], 'shared')
                self.assertEqual(config['configuration_error'], '')
                self.assertEqual(api_base(), 'https://dashscope.aliyuncs.com')

    def test_absent_endpoint_mode_defaults_to_shared(self):
        with settings(BAILIAN_WORKSPACE_ID=''):
            os.environ.pop('BAILIAN_ENDPOINT_MODE', None)
            self.assertEqual(api_base(), 'https://dashscope.aliyuncs.com')
            self.assertEqual(get_config()['configuration_error'], '')

    def test_explicit_workspace_endpoint_is_used_for_chat_and_speech(self):
        requests = []
        def handle(request):
            requests.append(request)
            if request.url.host == AUDIO_HOST:
                return httpx.Response(200, content=wav_bytes())
            self.assertEqual(request.url.host, f'{WORKSPACE}.cn-beijing.maas.aliyuncs.com')
            if request.url.path == '/compatible-mode/v1/chat/completions':
                return httpx.Response(200, json={'choices': [{
                    'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]})
            self.assertEqual(request.url.path, '/api/v1/services/audio/tts/SpeechSynthesizer')
            return httpx.Response(200, json=speech_result())
        with settings(BAILIAN_ENDPOINT_MODE='workspace'), transport(handle), tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(chat_json('Return JSON.', 'Test.'), {'ok': True})
            self.assertEqual(synthesize('Test.', 'en', Path(temporary)/'speech.wav'), .5)
        self.assertEqual(len(requests), 3)

    def test_invalid_workspace_endpoint_has_specific_message_and_no_silent_fallback(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(400, json={
                'code': 'invalid_parameter_error', 'message': 'Workspace endpoint is invalid.',
                'request_id': 'workspace-error-request'})
        with settings(BAILIAN_ENDPOINT_MODE='workspace'), transport(handle):
            with self.assertRaises(ProviderError) as raised:
                chat_json('Return JSON.', 'Test.')
        self.assertEqual(len(requests), 1)
        message = str(raised.exception)
        self.assertIn('业务空间', message)
        self.assertIn('BAILIAN_ENDPOINT_MODE', message)
        self.assertIn('shared', message)
        self.assertIn('workspace-error-request', message)
        self.assertNotIn('音色', message)

    def test_missing_foreign_and_expired_audio_url_stops_before_download(self):
        cases = [speech_result(''), speech_result('http://127.0.0.1/private.wav'),
                 speech_result('https://example.com/audio.wav'),
                 speech_result(f'https://{AUDIO_HOST}.example.com/audio.wav'),
                 speech_result(expires_at=1)]
        for result in cases:
            with self.subTest(result=result):
                requests = []
                def handle(request):
                    requests.append(request)
                    return httpx.Response(200, json=result)
                with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary)/'speech.wav'
                    with self.assertRaises(ProviderError):
                        synthesize('Test', 'en', output)
                    self.assertFalse(output.exists())
                self.assertEqual(len(requests), 1)

    def test_audio_redirect_and_oversize_and_invalid_wav_are_rejected_without_output(self):
        for response in [httpx.Response(302, headers={'location': 'http://127.0.0.1/private'}),
                         httpx.Response(200, headers={'content-length': str(64*1024*1024+1)}, content=b''),
                         httpx.Response(200, content=b'not a wav'),
                         httpx.Response(200, content=wav_bytes()[:-10])]:
            with self.subTest(status=response.status_code, size=len(response.content)):
                requests = []
                def handle(request):
                    requests.append(request)
                    return httpx.Response(200, json=speech_result()) if request.method == 'POST' else response
                with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary)/'speech.wav'
                    with self.assertRaises(ProviderError):
                        synthesize('Test', 'en', output)
                    self.assertFalse(output.exists())
                self.assertEqual(len(requests), 2)

    def test_real_tts_streaming_wav_sentinels_are_normalized_without_changing_samples(self):
        original = wav_bytes()
        streaming = bytearray(original)
        struct.pack_into('<I', streaming, 4, 2147483583)
        struct.pack_into('<I', streaming, 40, 2147483547)
        requests = []
        def handle(request):
            requests.append(request)
            if request.method == 'POST':
                return httpx.Response(200, json=speech_result())
            return httpx.Response(200, content=bytes(streaming), headers={'content-type': 'audio/wav'})
        with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'speech.wav'
            self.assertEqual(synthesize('Test.', 'en', output), .5)
            normalized = output.read_bytes()
            self.assertEqual(normalized, original, 'Only the streaming length fields should change.')
            self.assertEqual(struct.unpack_from('<I', normalized, 4)[0], len(normalized)-8)
            self.assertEqual(struct.unpack_from('<I', normalized, 40)[0], len(normalized)-44)
        self.assertEqual(len(requests), 2)

    def test_streaming_wav_fix_does_not_accept_corrupt_headers_or_odd_payload(self):
        original = wav_bytes()
        corruptions = {}
        ordinary = bytearray(original)
        struct.pack_into('<I', ordinary, 4, len(original)+200-8)
        struct.pack_into('<I', ordinary, 40, len(original)+200-44)
        corruptions['ordinary truncated data and RIFF'] = ordinary
        riff_only = bytearray(original)
        struct.pack_into('<I', riff_only, 4, len(original)+200-8)
        corruptions['ordinary oversized RIFF only'] = riff_only
        wrong_pair = bytearray(original)
        struct.pack_into('<I', wrong_pair, 4, 2147483582)
        struct.pack_into('<I', wrong_pair, 40, 2147483547)
        corruptions['unrecognized sentinel pair'] = wrong_pair
        wrong_format = bytearray(original)
        struct.pack_into('<I', wrong_format, 4, 2147483583)
        struct.pack_into('<I', wrong_format, 40, 2147483547)
        struct.pack_into('<I', wrong_format, 24, 16000)
        struct.pack_into('<I', wrong_format, 28, 32000)
        corruptions['unrecognized streaming format'] = wrong_format
        odd_payload = bytearray(original+b'\0')
        struct.pack_into('<I', odd_payload, 4, 2147483583)
        struct.pack_into('<I', odd_payload, 40, 2147483547)
        corruptions['odd sample payload'] = odd_payload
        empty_payload = bytearray(original[:44])
        struct.pack_into('<I', empty_payload, 4, 2147483583)
        struct.pack_into('<I', empty_payload, 40, 2147483547)
        corruptions['empty sample payload'] = empty_payload
        for case, data in corruptions.items():
            with self.subTest(case=case):
                def handle(request):
                    return httpx.Response(200, json=speech_result()) if request.method == 'POST' else httpx.Response(200, content=bytes(data))
                with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary)/'speech.wav'
                    with self.assertRaises(ProviderError):
                        synthesize('Test.', 'en', output)
                    self.assertFalse(output.exists())

    def test_bailian_billing_error_preserves_service_code_request_id_but_no_secrets_or_retry(self):
        private_text = 'Private narration must not be logged'
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(402, json={
                'code': 'Arrearage', 'message': 'Account service is unavailable. '+SECRET,
                'request_id': 'offline-request-id'}, headers={'x-request-id': 'offline-request-id'})
        with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary)/'calls.jsonl'
            with self.assertRaises(ProviderError) as raised:
                synthesize(private_text, 'zh', Path(temporary)/'speech.wav', diagnostics_path=log)
            raw = log.read_text()
            event = json.loads(raw)
        self.assertEqual(len(requests), 1)
        message = str(raised.exception)
        self.assertIn('Account service is unavailable.', message)
        self.assertIn('Arrearage', message)
        self.assertIn('offline-request-id', message)
        self.assertNotIn(SECRET, message+raw)
        self.assertNotIn(private_text, raw)
        self.assertEqual(event['host'], API_HOST)
        self.assertEqual(event['request_id'], 'offline-request-id')
        self.assertEqual(event['http_status'], 402)

    def test_http_200_service_error_is_not_mistaken_for_success_or_retried(self):
        for operation in ('chat', 'speech'):
            with self.subTest(operation=operation):
                requests = []
                def handle(request):
                    requests.append(request)
                    return httpx.Response(200, json={
                        'code': 'InvalidApiKey', 'message': 'Invalid API key: '+SECRET,
                        'request_id': 'semantic-error-id'})
                with settings(), transport(handle), tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaises(ProviderError) as raised:
                        if operation == 'chat':
                            chat_json('Return JSON.', 'Test.')
                        else:
                            synthesize('Test.', 'en', Path(temporary)/'speech.wav')
                self.assertEqual(len(requests), 1)
                self.assertIn('InvalidApiKey', str(raised.exception))
                self.assertIn('semantic-error-id', str(raised.exception))
                self.assertNotIn(SECRET, str(raised.exception))

    def test_provider_config_uses_bailian_and_never_returns_key(self):
        with settings():
            config = get_config()
        self.assertEqual(config['chat_model'], 'qwen3.8-flash')
        self.assertEqual(config['tts_model'], 'qwen-audio-3.1-tts-flash')
        self.assertTrue(config['token_configured'])
        self.assertTrue(config['workspace_configured'])
        self.assertNotIn(SECRET, json.dumps(config))


if __name__ == '__main__':
    unittest.main()
