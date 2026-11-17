"""Check local setup; --live explicitly makes one chat and two short TTS calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from backend.providers import ProviderError, chat_json, get_config, output_limit, redact, synthesize


def main(argv=None):
    parser = argparse.ArgumentParser(description='百炼北京配置检查。默认不发送 API 请求；--live 会产生少量用量。')
    parser.add_argument('--live', action='store_true', help='真实验证：一次短文本调用、中文与英文各一次短配音。')
    args = parser.parse_args(argv)
    load_dotenv(ROOT/'.env', override=True)
    settings = get_config()
    print('Provider: Alibaba Cloud Bailian / cn-beijing')
    print('Chat model: ' + settings['chat_model'])
    print('TTS model: ' + settings['tts_model'])
    print('Endpoint: ' + settings['endpoint_label'])
    if settings['configuration_error']:
        print(settings['configuration_error'], file=sys.stderr)
        print('No API requests made.')
        return 2
    try:
        print('Planning output budget: ' + str(output_limit()))
        if not args.live:
            print('Local configuration is ready. No API requests made; credentials have not been verified.')
            print('To make minimal real calls: .venv/bin/python scripts/check_bailian.py --live')
            return 0
        folder = ROOT/'data'/'bailian-check'
        folder.mkdir(parents=True, exist_ok=True)
        diagnostics = folder/'model_calls.jsonl'
        print('Checking chat API…', flush=True)
        result = chat_json('Return one JSON object with a single boolean field named ok.',
                           'Return {"ok":true}.', max_tokens=1024, task='百炼连接检查', diagnostics_path=diagnostics)
        if result.get('ok') is not True:
            raise ProviderError('文本接口未返回预期验证结果。')
        print('Chat API: OK', flush=True)
        for language, text in (('zh', '你好，这是论文讲解的中文配音测试。'),
                               ('en', 'Hello. This is an English narration test.')):
            output = folder/(language+'.wav')
            seconds = synthesize(text, language, output, diagnostics_path=diagnostics)
            print(f'TTS {language}: OK ({seconds:.2f}s) {output}', flush=True)
        (folder/'result.json').write_text(json.dumps({'provider': 'bailian', 'models': {
            'chat': settings['chat_model'], 'tts': settings['tts_model']}, 'languages': ['zh', 'en']}, indent=2))
        print('Minimal real API checks passed. Paper-to-video rendering is checked separately.')
        return 0
    except (ProviderError, OSError) as exc:
        print(redact(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
