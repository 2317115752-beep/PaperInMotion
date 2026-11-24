import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import app


class JobDeletionTests(unittest.TestCase):
    job_id = 'a' * 32
    child_id = 'b' * 32

    def setUp(self):
        self.data = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch('backend.app.DATA', self.data))
        self.enterContext(patch('backend.app.JOBS', {}))
        self.job_url = f'/api/jobs/{self.job_id}'

    def make_job(self, job_id=None, status='complete', **fields):
        job_id = job_id or self.job_id
        folder = self.data/job_id
        folder.mkdir()
        (folder/'job.json').write_text(json.dumps({
            'id': job_id, 'status': status, 'created_at': '2026-01-01T00:00:00Z',
            **fields,
        }), encoding='utf-8')
        (folder/'assets').mkdir()
        (folder/'assets'/'figure.png').write_bytes(b'demo image')
        (folder/'video.mp4').write_bytes(b'demo video')
        (folder/'paper.pdf').write_bytes(b'%PDF-test')
        return folder

    def test_complete_job_and_files_are_removed_without_removing_revision(self):
        folder = self.make_job()
        child = self.make_job(self.child_id, parent_id=self.job_id)
        with TestClient(app) as client:
            file_url = self.job_url + '/files/video.mp4'
            self.assertEqual(client.get(file_url).content, b'demo video')
            response = client.delete(self.job_url, headers={'Origin': 'http://127.0.0.1:8000'})
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b'')
            self.assertFalse(folder.exists())
            self.assertTrue((child/'video.mp4').is_file())
            self.assertEqual(client.get(self.job_url).status_code, 404)
            self.assertEqual(client.head(file_url).status_code, 404)
            self.assertEqual(client.delete(self.job_url).status_code, 404)
            history = client.get('/api/jobs').json()
            self.assertEqual([job['id'] for job in history], [self.child_id])
            self.assertNotIn('parent_id', history[0])

    def test_failed_job_can_be_removed_and_foreign_origin_is_rejected(self):
        folder = self.make_job(status='failed')
        with TestClient(app) as client:
            self.assertEqual(client.delete(self.job_url, headers={'Origin': 'https://example.com'}).status_code, 403)
            self.assertTrue(folder.is_dir())
            self.assertEqual(client.delete(self.job_url).status_code, 204)
        self.assertFalse(folder.exists())

    def test_active_jobs_cannot_be_removed(self):
        folder = self.make_job()
        for status in ('queued', 'running'):
            with (
                self.subTest(status=status),
                TestClient(app) as client,
                patch.dict('backend.app.JOBS', {self.job_id: {'status': status}}),
            ):
                self.assertEqual(client.delete(self.job_url).status_code, 409)
        self.assertTrue(folder.is_dir())

    def test_partial_deletion_can_be_retried_without_reloading_metadata(self):
        folder = self.make_job()
        pending = self.data/f'.deleting-{self.job_id}'
        with TestClient(app) as client:
            with patch('backend.app.shutil.rmtree', side_effect=PermissionError):
                self.assertEqual(client.delete(self.job_url).status_code, 500)
                self.assertFalse(folder.exists())
                self.assertTrue(pending.is_dir())
            self.assertEqual(client.delete(self.job_url).status_code, 204)
        self.assertFalse(pending.exists())

    def test_restart_finishes_interrupted_deletion_without_restoring_history(self):
        folder = self.make_job()
        pending = self.data/f'.deleting-{self.job_id}'
        with TestClient(app) as client, patch('backend.app.shutil.rmtree', side_effect=PermissionError):
            self.assertEqual(client.delete(self.job_url).status_code, 500)
        self.assertFalse(folder.exists())
        self.assertTrue((pending/'job.json').is_file())
        with patch('backend.app.JOBS', {}), TestClient(app) as restarted:
            self.assertEqual(restarted.get('/api/jobs').json(), [])
        self.assertFalse(pending.exists())

    def test_symbolic_link_cannot_remove_another_job(self):
        target = self.make_job(self.child_id)
        with TestClient(app) as client, patch.dict('backend.app.JOBS', {self.job_id: {'status': 'complete'}}):
            try:
                (self.data/self.job_id).symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest('This host cannot create directory symbolic links.')
            self.assertEqual(client.delete(self.job_url).status_code, 500)
            self.assertTrue((target/'video.mp4').is_file())
