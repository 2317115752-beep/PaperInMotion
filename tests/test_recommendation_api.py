import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app import app


class RecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self.data = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch('backend.app.DATA', self.data))
        self.enterContext(patch('backend.app.JOBS', {}))
        self.enterContext(patch('backend.app.config', return_value={'api_configured': True}))
        self.client = self.enterContext(TestClient(app))
        self.pool = self.enterContext(patch('backend.app.POOL', Mock()))

    def upload(self):
        response = self.client.post(
            '/api/recommendations',
            data={'language': 'en', 'level': 'advanced'},
            files=[('file', ('paper.pdf', b'%PDF-test', 'application/pdf')),
                   ('supplements', ('extra.pdf', b'%PDF-extra', 'application/pdf'))],
        )
        self.assertEqual(response.status_code, 202)
        job = response.json()
        self.assertEqual(job['status'], 'queued')
        self.assertTrue(job['pending_recommendation'])
        return job['id']

    def run_queued_job(self):
        worker, *args = self.pool.submit.call_args.args
        worker(*args)

    @staticmethod
    def analyze(job, folder, update):
        (folder/'method.json').write_text('{}')
        (folder/'sources.json').write_text('[]')
        update(title='Analyzed paper', stage='understanding', progress=40)
        return {'duration': 215, 'teaching_points': 7}

    def prepare_recommendation(self):
        job_id = self.upload()
        with patch('backend.app.run_recommendation', side_effect=self.analyze), \
             patch('backend.app.run_job') as generate:
            self.run_queued_job()
            generate.assert_not_called()
        return job_id

    def test_analysis_saves_recommendation_and_generation_reuses_job(self):
        job_id = self.prepare_recommendation()
        url = f'/api/jobs/{job_id}'
        job_folder = self.data/job_id
        ready = self.client.get(url).json()
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(ready['recommendation'], {'duration': 215, 'teaching_points': 7})
        self.assertEqual(ready['title'], 'Analyzed paper')
        self.assertEqual(ready['level'], 'advanced')
        self.assertEqual(ready['language'], 'en')
        self.assertEqual(ready['supplement_count'], 1)
        self.assertEqual((job_folder/'supplement-1.pdf').read_bytes(), b'%PDF-extra')
        self.assertEqual(self.client.post(url + '/generate', json={'duration': 90}).status_code, 422)
        response = self.client.post(url + '/generate', json={'style': 'midnight'})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['id'], job_id)
        self.assertEqual(response.json()['duration'], 215)
        self.assertEqual(response.json()['style'], 'midnight')
        self.assertTrue(response.json()['recommended_pacing'])
        self.assertFalse(response.json()['pending_recommendation'])
        self.assertEqual(self.client.post(url + '/generate', json={}).status_code, 409)
        self.assertEqual(self.pool.submit.call_count, 2)
        with patch('backend.app.run_job') as generate, patch('backend.app.run_recommendation') as analyze:
            self.run_queued_job()
            job, folder, _ = generate.call_args.args
            self.assertTrue(job['from_recommendation'])
            self.assertEqual(folder, job_folder)
            analyze.assert_not_called()

    def test_queue_failure_preserves_ready_checkpoint_and_manual_duration(self):
        job_id = self.prepare_recommendation()
        url = f'/api/jobs/{job_id}'
        self.pool.submit.side_effect = RuntimeError
        response = self.client.post(url + '/generate', json={'duration': 60})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(url).json()['status'], 'ready')
        saved = json.loads((self.data/job_id/'job.json').read_text())
        self.assertEqual(saved['status'], 'ready')
        self.assertEqual(saved['duration'], 215)
        self.pool.submit.side_effect = None
        generated = self.client.post(url + '/generate', json={'duration': 60})
        self.assertEqual(generated.status_code, 202)
        self.assertEqual(generated.json()['duration'], 60)
        self.assertFalse(generated.json()['recommended_pacing'])

    def test_explicit_recommended_duration_is_accepted(self):
        job_id = self.prepare_recommendation()
        url = f'/api/jobs/{job_id}/generate'
        self.assertEqual(self.client.post(url, json={'duration': 240}).status_code, 422)
        response = self.client.post(url, json={'duration': 215})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['duration'], 215)
        self.assertTrue(response.json()['recommended_pacing'])

    def test_failed_analysis_retries_same_job_and_ready_job_can_be_deleted(self):
        job_id = self.upload()
        url = f'/api/jobs/{job_id}'
        with patch('backend.app.run_recommendation', side_effect=ValueError('Could not analyze')):
            self.run_queued_job()
        failed = self.client.get(url).json()
        self.assertEqual((failed['status'], failed['error']), ('failed', 'Could not analyze'))
        self.assertTrue(failed['pending_recommendation'])
        retry = self.client.post(url + '/retry')
        self.assertEqual(retry.status_code, 202)
        self.assertEqual(retry.json()['id'], job_id)
        self.assertNotIn('error', retry.json())
        with patch('backend.app.run_recommendation', side_effect=self.analyze):
            self.run_queued_job()
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse((self.data/job_id).exists())
