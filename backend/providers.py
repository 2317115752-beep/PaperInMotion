"""Alibaba Cloud Bailian APIs only; no model weights are downloaded."""
import base64
import binascii
import io
import json
import logging
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import struct
import time
import wave
from urllib.parse import urlsplit, urlunsplit

import httpx

MAX_AUDIO_BYTES = 64 * 1024 * 1024
AUDIO_HOST = 'dashscope-result-bj.oss-cn-beijing.aliyuncs.com'


class ProviderError(RuntimeError):
    pass


def get_config():
    workspace = os.getenv('BAILIAN_WORKSPACE_ID', '').strip()
    mode = os.getenv('BAILIAN_ENDPOINT_MODE', '').strip() or 'shared'
    has_key = bool(os.getenv('DASHSCOPE_API_KEY', '').strip())
    valid_workspace = bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,62}', workspace))
    missing = []
    if not has_key:
        missing.append('DASHSCOPE_API_KEY（北京地域 API Key）')
    if mode == 'workspace':
        if not workspace:
            missing.append('BAILIAN_WORKSPACE_ID（北京地域业务空间 ID）')
        elif not valid_workspace:
            missing.append('有效的 BAILIAN_WORKSPACE_ID（仅填写 ID，不含网址）')
    elif mode != 'shared':
        missing.append('有效的 BAILIAN_ENDPOINT_MODE（shared 或 workspace）')
    return {
        'provider': 'bailian', 'region': 'cn-beijing', 'endpoint_mode': mode,
        'endpoint_label': '北京业务空间专属接口' if mode == 'workspace' else '北京通用接口',
        'chat_model': os.getenv('BAILIAN_CHAT_MODEL', '').strip() or 'qwen3.8-flash',
        'tts_model': os.getenv('BAILIAN_TTS_MODEL', '').strip() or 'qwen-audio-3.1-tts-flash',
        'token_configured': has_key, 'workspace_configured': valid_workspace,
        'configuration_error': '请在项目 .env 中填写 ' + '、'.join(missing) + '。' if missing else '',
    }


def token():
    value = os.getenv('DASHSCOPE_API_KEY', '').strip()
    if not value:
        raise ProviderError('请在项目 .env 中填写 DASHSCOPE_API_KEY（百炼北京地域 API Key）。')
    return value


def api_base():
    config = get_config()
    if config['configuration_error']:
        raise ProviderError(config['configuration_error'])
    if config['endpoint_mode'] == 'shared':
        return 'https://dashscope.aliyuncs.com'
    workspace = os.environ['BAILIAN_WORKSPACE_ID'].strip()
    return f'https://{workspace}.cn-beijing.maas.aliyuncs.com'


def redact(value):
    text = str(value)
    for name in ('DASHSCOPE_API_KEY', 'HF_TOKEN'):
        secret = os.getenv(name, '').strip()
        if secret:
            text = text.replace(secret, '[redacted]')
    text = re.sub(r'\b(?:sk-|hf_)[A-Za-z0-9_\-]+', '[redacted]', text)
    return re.sub(r'(?i)Bearer\s+[^\s"\']+', 'Bearer [redacted]', text)


def service_error_details(response, body=None):
    """Keep bounded service errors, never request headers, prompts or signed URLs."""
    if response is None:
        return {}
    def clean(value, limit=500):
        return re.sub(r'\s+', ' ', redact(value)).strip()[:limit]
    if body is None:
        try:
            body = response.json()
        except (ValueError, RuntimeError):
            body = None
    body = body if isinstance(body, dict) else {}
    error = body.get('error')
    error = error if isinstance(error, dict) else {}
    message = error.get('message') or body.get('message') or body.get('detail')
    if not isinstance(message, str):
        message = body.get('error') if isinstance(body.get('error'), str) else ''
    request = getattr(response, '_request', None)
    host = urlsplit(str(getattr(request, 'url', ''))).hostname
    return {
        'http_status': getattr(response, 'status_code', None), 'host': host,
        'request_id': clean(body.get('request_id') or response.headers.get('x-request-id') or response.headers.get('x-dashscope-request-id') or '', 150),
        'error_code': clean(error.get('code') or body.get('code') or '', 150),
        'server_error': clean(message),
    }


def problem(status, task, response=None):
    details = service_error_details(response)
    reason = {
        400: '服务拒绝了请求参数，请检查模型、音色与输入长度。',
        401: 'API Key 无效，请检查 DASHSCOPE_API_KEY 及北京地域。',
        402: '计费请求被拒绝，请检查百炼账户余额、额度及服务开通状态。',
        403: '访问被拒绝，请检查北京业务空间、API Key 权限及模型服务开通状态。',
        404: '模型或接口不可用，请检查北京业务空间与模型名称。',
        429: '触发请求限流或额度限制，请检查服务说明后重试。',
    }.get(status, '百炼服务未完成请求，请查看服务说明或稍后重试。')
    if 'workspace endpoint is invalid' in details.get('server_error', '').lower():
        reason = '业务空间专属地址无效。请将 .env 中 BAILIAN_ENDPOINT_MODE 设为 shared，使用北京通用接口；或核对专属域名对应的业务空间 ID。'
    suffix = f' HTTP {status}' if status else ''
    if details.get('error_code'):
        suffix += f" code={details['error_code']}"
    if details.get('server_error'):
        suffix += f" 服务说明：{details['server_error']}"
    if details.get('request_id'):
        suffix += f" request_id={details['request_id']}"
    return ProviderError(f'{task}：{reason}{suffix}')


def service_failed(result):
    if not isinstance(result, dict):
        return False
    return bool(result.get('error')) or result.get('code') not in (None, '', 'Success', 'success', '200', 200, 0)


def write_diagnostic(path, event):
    if path is None:
        return
    try:
        with Path(path).open('a', encoding='utf-8') as log:
            log.write(json.dumps(event, ensure_ascii=False) + '\n')
    except OSError:
        logging.warning('Could not write model call metadata')


def record_speech_diagnostic(path, response, attempt, result=None):
    try:
        if result is None:
            result = response.json()
        usage = result.get('usage') if isinstance(result, dict) else None
    except ValueError:
        usage = None
    usage = usage if isinstance(usage, dict) else {}
    counts = {'speech_' + key: usage[key] for key in ('input_tokens', 'output_tokens')
              if type(usage.get(key)) is int and usage[key] >= 0}
    write_diagnostic(path, {
        'created_at': datetime.now(timezone.utc).isoformat(), 'task': '语音合成',
        'provider': 'bailian', 'model': get_config()['tts_model'],
        'attempt': attempt, **service_error_details(response, result), **counts,
    })


def parse_json(text):
    if not isinstance(text, str) or len(text) > 150_000:
        raise ProviderError('模型未返回有效的最终文本，或输出过长。')
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S | re.I).strip()
    if '</think>' in text:
        text = text.split('</think>')[-1]
    start = text.find('{')
    if start < 0:
        raise ProviderError('模型未返回 JSON 计划，请重试。')
    def reject_constant(value):
        raise ValueError('Non-finite JSON number')
    try:
        obj, _ = json.JSONDecoder(parse_constant=reject_constant).raw_decode(text, start)
    except (ValueError, RecursionError):
        raise ProviderError('模型计划的 JSON 格式不完整，请重新生成。') from None
    if not isinstance(obj, dict):
        raise ProviderError('模型计划必须是 JSON 对象。')
    return obj


def output_limit(value=None):
    raw = value if value is not None else os.getenv('BAILIAN_CHAT_MAX_TOKENS', '12000')
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise ProviderError('BAILIAN_CHAT_MAX_TOKENS 必须是1024–32768之间的整数。') from None
    if isinstance(raw, (bool, float)) or not 1024 <= limit <= 32768:
        raise ProviderError('BAILIAN_CHAT_MAX_TOKENS 必须是1024–32768之间的整数。')
    return limit


def record_chat_diagnostic(path, *, task, model, limit, attempt, status, result=None,
                           elapsed_seconds=None, transport_error=None):
    """Save counts only, never credentials, paper text, generated text or reasoning."""
    result = result if isinstance(result, dict) else {}
    choices = result.get('choices')
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get('message')
    message = message if isinstance(message, dict) else {}
    usage = result.get('usage')
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get('completion_tokens_details')
    details = details if isinstance(details, dict) else {}
    count = lambda value: value if type(value) is int and value >= 0 else None
    text_size = lambda value: len(value) if isinstance(value, str) else 0
    write_diagnostic(path, {
        'created_at': datetime.now(timezone.utc).isoformat(), 'task': task, 'provider': 'bailian',
        'model': model, 'max_tokens': limit, 'attempt': attempt, 'http_status': status,
        'finish_reason': str(choice.get('finish_reason', ''))[:50],
        'prompt_tokens': count(usage.get('prompt_tokens')),
        'completion_tokens': count(usage.get('completion_tokens')),
        'reasoning_tokens': count(details.get('reasoning_tokens')),
        'content_chars': text_size(message.get('content')),
        'reasoning_chars': text_size(message.get('reasoning_content') or message.get('reasoning')),
        'elapsed_seconds': round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        'transport_error': transport_error,
    })


def chat_transport_error(exc, timeout):
    if isinstance(exc, httpx.ReadTimeout):
        return f'等待百炼响应超时（连续 {timeout.read:g} 秒未收到数据）。'
    if isinstance(exc, httpx.WriteTimeout):
        return f'向百炼上传请求超时（连续 {timeout.write:g} 秒未能发送数据）。'
    return f'百炼请求传输中断（{type(exc).__name__}）。'


def chat_json(system, user_content, *, max_tokens=None, task='论文规划', diagnostics_path=None):
    limit = output_limit(max_tokens)
    base, key = api_base(), token()
    model = get_config()['chat_model']
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system + '\nReturn exactly one compact valid JSON object. No thinking, markdown, repeated explanations or extra keys.'},
            {'role': 'user', 'content': user_content},
        ],
        'temperature': .3, 'max_tokens': limit,
        'response_format': {'type': 'json_object'},
        # Raw HTTP DashScope parameter, not the OpenAI SDK's extra_body wrapper.
        'enable_thinking': False,
    }
    timeout = httpx.Timeout(600, connect=20, read=600, write=300, pool=30)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for attempt in range(3):
            started = time.monotonic()
            try:
                response = client.post(base + '/compatible-mode/v1/chat/completions', headers={'Authorization': f'Bearer {key}'}, json=payload)
            except httpx.RequestError as exc:
                record_chat_diagnostic(diagnostics_path, task=task, model=model, limit=limit,
                                       attempt=attempt+1, status=None, elapsed_seconds=time.monotonic()-started,
                                       transport_error=type(exc).__name__)
                if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                    if attempt < 2:
                        time.sleep(attempt + 1)
                        continue
                    raise ProviderError(f'{task}：无法建立百炼 API 连接（{type(exc).__name__}）。') from None
                reason = chat_transport_error(exc, timeout)
                raise ProviderError(f'{task}：{reason}本次请求未自动重发，可从历史记录重试。') from None
            try:
                result = response.json()
            except ValueError:
                result = None
            record_chat_diagnostic(diagnostics_path, task=task, model=model, limit=limit, attempt=attempt+1,
                                   status=response.status_code, result=result, elapsed_seconds=time.monotonic()-started)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            if not response.is_success or service_failed(result):
                raise problem(response.status_code, task, response)
            try:
                choice = result['choices'][0]
                finish = choice.get('finish_reason')
                if finish == 'length':
                    raise ProviderError(f'{task}：模型回复在{limit:,} token输出上限被截断，本阶段未完成。请查看任务目录 model_calls.jsonl；可在 .env 调整 BAILIAN_CHAT_MAX_TOKENS 后重试。')
                if finish != 'stop':
                    raise ProviderError(f'{task}：模型未正常结束（finish_reason={redact(finish)[:60]}），本阶段未完成。')
                return parse_json(choice['message']['content'])
            except (KeyError, IndexError, TypeError, ValueError):
                raise ProviderError(f'{task}：百炼服务返回了无效结构。') from None


def audio_url(audio):
    if not isinstance(audio, dict) or not isinstance(audio.get('url'), str) or not audio['url']:
        raise ProviderError('配音服务没有返回音频下载地址，已停止生成。')
    expires = audio.get('expires_at')
    if expires is not None and (type(expires) not in (int, float) or expires <= time.time()):
        raise ProviderError('配音下载地址已过期或有效期无效，请重新生成。')
    try:
        parsed = urlsplit(audio['url'])
        valid = parsed.scheme in ('http', 'https') and parsed.hostname == AUDIO_HOST and parsed.port in (None, 443) and not parsed.username and not parsed.password and not parsed.fragment and parsed.path.startswith('/')
    except ValueError:
        valid = False
    if not valid:
        raise ProviderError('配音服务返回了不受支持的音频下载地址，已停止生成。')
    return urlunsplit(('https', parsed.netloc, parsed.path, parsed.query, ''))


def download_audio(url):
    # A new client carries no API headers/cookies; signed asset URLs are never logged.
    chunks, total = [], 0
    try:
        with httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=False) as assets:
            with assets.stream('GET', url) as response:
                if not response.is_success:
                    raise ProviderError(f'配音文件下载失败（HTTP {response.status_code}），请重新生成。')
                length = response.headers.get('content-length')
                if length and (not length.isdigit() or int(length) > MAX_AUDIO_BYTES):
                    raise ProviderError('配音文件过大或长度无效，已停止生成。')
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_AUDIO_BYTES:
                        raise ProviderError('配音文件超过64MB，已停止生成。')
                    chunks.append(chunk)
    except httpx.RequestError:
        raise ProviderError('无法下载配音文件，请检查网络后重试。') from None
    return b''.join(chunks)


def normalize_wav(data):
    """Finalize the specific unknown-length PCM header emitted by Bailian TTS.

    Only the observed paired sentinel and mono/24kHz/16-bit layout qualify.
    Other incomplete or corrupt WAV files still fail normal decoding below.
    """
    if len(data) <= 44 or data[:4] != b'RIFF' or data[8:16] != b'WAVEfmt ' or data[36:40] != b'data':
        return data
    if struct.unpack_from('<I', data, 16)[0] != 16:
        return data
    if struct.unpack_from('<I', data, 4)[0] != 0x7FFFFFBF or struct.unpack_from('<I', data, 40)[0] != 0x7FFFFF9B:
        return data
    if struct.unpack_from('<HHIIHH', data, 20) != (1, 1, 24000, 48000, 2, 16):
        return data
    if (len(data) - 44) % 2:
        raise ProviderError('配音文件的采样帧不完整，已停止生成。')
    finalized = bytearray(data)
    struct.pack_into('<I', finalized, 4, len(data) - 8)
    struct.pack_into('<I', finalized, 40, len(data) - 44)
    return bytes(finalized)


def speech_stream(base, key, payload, diagnostics_path):
    chunks, size = [], 0
    with httpx.Client(timeout=httpx.Timeout(45, connect=10), follow_redirects=False) as client:
        try:
            with client.stream('POST', base + '/api/v1/services/audio/tts/SpeechSynthesizer',
                               headers={'Authorization': f'Bearer {key}', 'X-DashScope-SSE': 'enable'},
                               json=payload) as response:
                if not response.is_success:
                    response.read()
                    record_speech_diagnostic(diagnostics_path, response, 1)
                    raise problem(response.status_code, '语音合成', response)
                for line in response.iter_lines():
                    if not line.startswith('data:'):
                        continue
                    result = json.loads(line[5:])
                    if service_failed(result):
                        record_speech_diagnostic(diagnostics_path, response, 1, result)
                        code = redact(result.get('code') or 'error')[:80]
                        message = redact(result.get('message') or result.get('error') or '')[:240]
                        raise ProviderError(f'百炼流式语音未完成（{code}）：{message}')
                    event = result.get('output') or {}
                    if event.get('type') == 'sentence-synthesis':
                        encoded = (event.get('audio') or {}).get('data') or ''
                        chunk = base64.b64decode(encoded, validate=True)
                        size += len(chunk)
                        if size > MAX_AUDIO_BYTES:
                            raise ProviderError('配音文件超过64MB。')
                        chunks.append(chunk)
                    if event.get('finish_reason') == 'stop':
                        record_speech_diagnostic(diagnostics_path, response, 1, result)
                        return b''.join(chunks)
        except httpx.RequestError as exc:
            raise ProviderError(f'百炼流式配音连接失败（{type(exc).__name__}），可从已保存的语音片段重试。') from None
        except (ValueError, TypeError, AttributeError, binascii.Error):
            raise ProviderError('百炼流式配音数据格式无效。') from None
    raise ProviderError('百炼流式配音在完成前断开，请重试。')


def synthesize(text, language, output: Path, *, diagnostics_path=None, streaming=False):
    if language not in ('zh', 'en') or not isinstance(text, str) or not 1 <= len(text) <= 10_000:
        raise ProviderError('配音文字或语言无效。')
    base, key = api_base(), token()
    voice = os.getenv('BAILIAN_TTS_VOICE_ZH' if language == 'zh' else 'BAILIAN_TTS_VOICE_EN', '').strip() or 'loongbella_v3.1'
    payload = {'model': get_config()['tts_model'], 'input': {
        'text': text, 'voice': voice, 'format': 'wav', 'sample_rate': 24000,
        'language_hints': [language],
    }}
    if streaming:
        data = speech_stream(base, key, payload, diagnostics_path)
    else:
        data = speech_file(base, key, payload, diagnostics_path)
    return save_speech(data, output)


def speech_file(base, key, payload, diagnostics_path):
    with httpx.Client(timeout=httpx.Timeout(240, connect=20), follow_redirects=False) as client:
        for attempt in range(3):
            try:
                response = client.post(base + '/api/v1/services/audio/tts/SpeechSynthesizer', headers={'Authorization': f'Bearer {key}'}, json=payload)
            except httpx.RequestError:
                raise ProviderError('无法连接百炼语音 API，请检查网络或代理。请求未自动重发。') from None
            record_speech_diagnostic(diagnostics_path, response, attempt+1)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            try:
                result = response.json()
            except ValueError:
                result = None
            if not response.is_success or service_failed(result):
                raise problem(response.status_code, '语音合成', response)
            try:
                generated = result['output']
                if generated.get('finish_reason') != 'stop':
                    raise ProviderError('百炼配音未正常结束，已停止生成。')
                url = audio_url(generated['audio'])
            except (KeyError, TypeError, AttributeError):
                raise ProviderError('百炼配音服务返回了无效结构，已停止生成。') from None
            break
    return download_audio(url)


def save_speech(data, output):
    data = normalize_wav(data)
    if not 44 < len(data) <= MAX_AUDIO_BYTES or data[:4] != b'RIFF' or data[8:12] != b'WAVE' or struct.unpack_from('<I', data, 4)[0] != len(data) - 8:
        raise ProviderError('配音服务没有返回有效 WAV，已停止生成。')
    try:
        with wave.open(io.BytesIO(data)) as audio:
            count, rate = audio.getnframes(), audio.getframerate()
            size = count * audio.getnchannels() * audio.getsampwidth()
            if not count or not rate or size > MAX_AUDIO_BYTES or len(audio.readframes(count)) != size:
                raise ValueError('Empty or truncated audio')
            duration = count / rate
    except (wave.Error, EOFError, ValueError):
        raise ProviderError('配音文件无法解码或音频不完整，已停止生成。') from None
    output = Path(output)
    output.write_bytes(data)
    return duration
