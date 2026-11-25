import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from backend.examples import execute_example
from backend.pipeline import verify_sources, write_subtitles, demo_storyboard, read_paper, plan_scenes
from backend.timing import prepare_subtitle_cues
from backend.providers import parse_json, synthesize, ProviderError
from backend.app import app


class NumericalTests(unittest.TestCase):
    def test_low_rank_computes_shared_states(self):
        result=execute_example({'kind':'low_rank','W0':[[1,0,0],[0,1,0]],'A':[[1,0,1]],'B':[[2],[-1]],'x':[1,2,3]})
        self.assertEqual(result['hidden'],[4]);self.assertEqual(result['baseline'],[1,2])
        self.assertEqual(result['delta'],[8,-4]);self.assertEqual(result['output'],[9,-2])
        self.assertEqual(result['params']['adapter'],5)

    def test_scale_is_applied_to_delta(self):
        result=execute_example({'kind':'low_rank','W0':[[1]],'A':[[2]],'B':[[3]],'x':[4],'scale':.5})
        self.assertEqual(result['output'],[16])

    def test_attention_softmax_matches_reference(self):
        result=execute_example({'kind':'scaled_dot_attention','Q':[[1,0]],'K':[[1,0],[0,1]],'V':[[2,0],[0,4]]})
        weight=np.exp(1/np.sqrt(2))/(np.exp(1/np.sqrt(2))+1)
        np.testing.assert_allclose(result['output'],[[2*weight,4*(1-weight)]])
        self.assertAlmostEqual(sum(result['weights'][0]),1)

    def test_invalid_shapes_and_nonfinite_rejected(self):
        for value in (float('nan'),float('inf'),1e9):
            with self.assertRaises(ValueError):
                execute_example({'kind':'low_rank','W0':[[value]],'A':[[1]],'B':[[1]],'x':[1]})
        with self.assertRaises(ValueError):
            execute_example({'kind':'low_rank','W0':[[1,2]],'A':[[1]],'B':[[1]],'x':[1,2]})

    def test_arbitrary_code_rejected(self):
        with self.assertRaises(ValueError):
            execute_example({'kind':'python','code':'print(1)'})


class PipelineTests(unittest.TestCase):
    def test_five_minute_upload_accepts_a_twelve_scene_storyboard(self):
        pages = [{'page': 1, 'text': 'The paper describes its approach and experiments.'}]
        raw = {'title': 'Paper', 'scenes': [
            {'title': f'Scene {i+1}', 'narration': 'A step in the explanation.', 'evidence_ids': ['p1-e1']}
            for i in range(12)
        ]}
        with tempfile.TemporaryDirectory() as temporary, \
             patch('backend.app.DATA', Path(temporary)), patch('backend.app.JOBS', {}), \
             patch('backend.app.config', return_value={'api_configured': True}), \
             patch('backend.app.enqueue', side_effect=lambda job, folder: job), TestClient(app) as client:
            response = client.post('/api/jobs', files={'file': ('paper.pdf', b'%PDF-test', 'application/pdf')},
                                   data={'language': 'en', 'duration': 300})
        self.assertEqual(response.status_code, 202)
        with patch('backend.pipeline.chat_json', return_value=raw):
            plan = plan_scenes({}, None, response.json()['language'], response.json()['duration'], pages)
        self.assertEqual(len(plan['scenes']), 12)
        self.assertEqual(plan['scenes'][-1]['id'], 'scene-12')

    def test_plan_uses_natural_chinese_terms_without_editing_source_or_math(self):
        source_text = '论文使用「玩具输入」这个术语来说明演算过程。'
        pages = [{'page': 1, 'text': source_text}]
        formula = r'f(x) = \underbrace{x}_{\text{玩具输入}}'
        narration = '先看玩具输入。再看玩具示例和玩具数值。'
        raw = {'title': '玩具示例计算', 'scenes': [{
            'title': '玩具输入的计算',
            'visual_type': 'equation',
            'narration': narration,
            'bullets': ['玩具示例', '玩具数值'],
            'formula': formula,
            'evidence_ids': ['p1-e1'],
        } for _ in range(4)]}
        with patch('backend.pipeline.chat_json', return_value=raw):
            chinese = plan_scenes({}, None, 'zh', 60, pages)
            english = plan_scenes({}, None, 'en', 60, pages)

        first = chinese['scenes'][0]
        self.assertEqual(chinese['title'], '演算示例计算')
        self.assertEqual(first['title'], '简化输入的计算')
        self.assertEqual(first['narration'], '先看简化输入。再看演算示例和示例数值。')
        self.assertEqual(first['bullets'], ['演算示例', '示例数值'])
        self.assertEqual(first['formula'], formula)
        self.assertEqual(first['evidence'][0]['quote'], source_text)
        self.assertEqual(english['title'], raw['title'])
        self.assertEqual(english['scenes'][0]['narration'], narration)
        self.assertEqual(english['scenes'][0]['bullets'], ['玩具示例', '玩具数值'])

    def test_evidence_filter_preserves_only_matching_quotes(self):
        method={'claims':[{'claim':'supported','source_pages':[2],'evidence_quote':'The adapter changes the output.'},{'claim':'unsupported','source_pages':[99],'evidence_quote':'Invented measurement.'}]}
        warnings=verify_sources(method,[{'page':2,'text':'The adapter changes the output. More text.'}])
        self.assertEqual(len(method['claims']),1);self.assertTrue(warnings)

    def test_no_valid_evidence_stops_generation(self):
        with self.assertRaises(ValueError):
            verify_sources({'claims':[{'source_pages':[1],'evidence_quote':'This quote does not exist.'}]},[{'page':1,'text':'Different text'}])

    def test_subtitle_time_follows_audio_and_scene_offsets(self):
        scenes=[{'narration':'Hello. World.','duration_frames':72,'audio_duration':2},{'narration':'Next.','duration_frames':48,'audio_duration':1}]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'a.srt';write_subtitles(path,scenes,'en');text=path.read_text()
        self.assertIn('00:00:00,000 --> 00:00:01,000',text)
        self.assertIn('00:00:03,000 --> 00:00:04,000',text)

    def test_subtitle_math_keeps_the_original_frame_interval(self):
        cue = {'text': '观察 gamma_X、x_1 和 J2D_full，在 report_2 中。', 'start_frame': 12, 'end_frame': 36}
        scenes = [{'duration_frames': 48, 'cues': [cue]}]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.srt'
            write_subtitles(path, scenes, 'zh')
            text = path.read_text()
        self.assertIn('00:00:00,500 --> 00:00:01,500', text)
        self.assertIn('观察 γ_X、x₁ 和 J_(2D)^(full)，在 report_2 中。', text)

    def test_chinese_mathematical_quantities_match_rendered_captions_and_srt(self):
        cues = [
            ('朝向分别是负十五度、零度和十五度。', '朝向分别是−15°、0°和15°。'),
            ('输入是二百二十四乘二百二十四。', '输入是224×224。'),
            ('输出一和二的结果。', '输出1和2的结果。'),
            ('结果是零点九和二点四，基线是八十四点零。', '结果是0.9和2.4，基线是84.0。'),
            ('误差是八十五点四毫米，等于另一个结果的三分之二。', '误差是85.4毫米，等于另一个结果的2/3。'),
            ('在3DPW上，二维关键点误差下降百分之十二点五。', '在3DPW上，2D 关键点误差下降12.5%。'),
            ('模型一度校正三点五毫米的偏移，两点之间的距离等于一。', '模型一度校正3.5毫米的偏移，两点之间的距离等于1。'),
            ('一步步看，两个改动缺一不可。', '一步步看，两个改动缺一不可。'),
            ('用公式七修正十五度的偏差，得到二十一维向量。', '用公式7修正15°的偏差，得到21D 向量。'),
            ('代码 ' + chr(96) + '零点五' + chr(96) + ' 保留，公式 $E^2$ 旁边标为二点五。', '代码 ' + chr(96) + '零点五' + chr(96) + ' 保留，公式 $E^2$ 旁边标为2.5。'),
        ]
        scenes = [{'duration_frames': 24, 'cues': [{'start_frame': 0, 'end_frame': 24, 'text': source}]}
                  for source, _ in cues]
        prepare_subtitle_cues(scenes, 'zh')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.srt'
            write_subtitles(path, scenes, 'zh')
            blocks = path.read_text().strip().split('\n\n')
        for index, (scene, (source, expected), block) in enumerate(zip(scenes, cues, blocks, strict=True)):
            cue = scene['cues'][0]
            self.assertEqual(cue['text'], source)
            self.assertEqual(cue.get('caption_text', cue['text']), expected)
            self.assertEqual(block.splitlines()[1], f'00:00:{index:02},000 --> 00:00:{index + 1:02},000')
            self.assertEqual(block.splitlines()[2], expected.replace('$E^2$', 'E²'))

    def test_srt_preserves_filenames_and_simplifies_delimited_math(self):
        cue = {'text': r'Use w_1.npy and `x_1` with \(\Delta_0\) and $E^2$.',
               'start_frame': 0, 'end_frame': 24}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.srt'
            write_subtitles(path, [{'duration_frames': 24, 'cues': [cue]}], 'en')
            text = path.read_text()
        self.assertIn('Use w_1.npy and `x_1` with Δ₀ and E².', text)

    def test_both_demo_languages_have_verified_matrix_and_no_audio(self):
        for language in ('zh','en'):
            result,example=demo_storyboard(language)
            self.assertEqual(example['output'],[9,-2]);self.assertEqual(len(result['scenes']),6)
            self.assertTrue(all('audio_path' not in s and not s['source_pages'] for s in result['scenes']))

    def test_pdf_keeps_source_page_numbers(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'paper.pdf'
            doc=fitz.open();page=doc.new_page();page.insert_textbox(fitz.Rect(30,30,560,700),'This is a research paper about low rank adaptation. '*20);doc.save(path);doc.close()
            pages,images,warnings=read_paper(path)
        self.assertEqual(pages[0]['page'],1);self.assertEqual(images[0]['page'],1)

    def test_model_json_and_invalid_values(self):
        self.assertEqual(parse_json('<think>hidden</think>```json\n{"scenes": []}\n```'),{'scenes':[]})
        for text in ('not json','{"value": NaN}'):
            with self.assertRaises(ProviderError):parse_json(text)

    def test_config_never_exposes_token_and_missing_token_blocks_generation(self):
        with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'','BAILIAN_WORKSPACE_ID':'unit-workspace','BAILIAN_ENDPOINT_MODE':'shared'}),patch('backend.app.load_dotenv'):
            with TestClient(app) as client:
                response=client.get('/api/config')
                self.assertFalse(response.json()['api_configured']);self.assertNotIn('token',response.json())
                self.assertNotIn('DASHSCOPE_API_KEY', response.json())
                self.assertEqual(response.json()['model'], 'qwen3.8-flash')
                self.assertEqual(response.json()['tts_model'], 'qwen-audio-3.1-tts-flash')
                response=client.post('/api/jobs',files={'file':('paper.pdf',b'%PDF-test','application/pdf')},data={'language':'zh','duration':120})
                self.assertEqual(response.status_code,400)
                self.assertEqual(client.post('/api/demo',headers={'Origin':'https://unknown.example'}).status_code,403)

if __name__=='__main__':unittest.main()
