import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from backend.examples import execute_example
from backend.pipeline import verify_sources, write_subtitles, demo_storyboard, read_paper
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
