import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from backend.pipeline import DURATION_SCENES, run_job
from backend.providers import ProviderError
from backend.timing import FPS, MAX_SCENE_TAIL, MIN_PLAYBACK_RATE, fit_scene_durations


def timed_scene(seconds):
    return {
        'audio_duration': seconds,
        'cues': [{'text': 'Narration', 'start_frame': FPS, 'end_frame': round(seconds * FPS)}],
    }


class DurationTests(unittest.TestCase):
    def test_target_frames_and_rescaled_cues_match_adjusted_speech(self):
        for duration, count in DURATION_SCENES.items():
            with self.subTest(duration=duration):
                scenes = [timed_scene(duration * .94 / count) for _ in range(count)]
                fit_scene_durations(scenes, duration)
                self.assertEqual(sum(scene['duration_frames'] for scene in scenes), duration * FPS)
                for scene in scenes:
                    rate = scene.get('audio_playback_rate', 1)
                    self.assertGreaterEqual(rate, MIN_PLAYBACK_RATE)
                    self.assertEqual(scene['cues'][0]['start_frame'], round(FPS / rate))
                    self.assertLessEqual(scene['cues'][0]['end_frame'], scene['duration_frames'])

    def test_large_shortfall_preserves_natural_pacing(self):
        scenes = [timed_scene(6) for _ in range(3)]
        fit_scene_durations(scenes, 60)
        for scene in scenes:
            self.assertEqual(scene['audio_playback_rate'], MIN_PLAYBACK_RATE)
            self.assertLessEqual(scene['duration_frames'] - round(scene['audio_duration'] * FPS),
                                 MAX_SCENE_TAIL + 1)
        self.assertLess(sum(scene['duration_frames'] for scene in scenes), 60 * FPS)

    def test_short_storyboard_expands_once_and_reuses_original_speech(self):
        excerpt = {'id': 'p1-e1', 'text': 'The model has three layers with shared weights.'}
        storyboard = {
            'title': 'Three layers',
            'scenes': [
                {'title': f'Layer {index}', 'narration': f'This layer uses the same weights at step {index}',
                 'evidence': [excerpt]} for index in range(1, 4)
            ],
        }
        additions = {
            f'scene-{index}': f'At step {index}, the input passes through the same transformation again.'
            for index in range(1, 4)
        }
        job = {'id': 'duration-test', 'is_demo': False, 'language': 'en', 'duration': 60, 'condition': 'A'}

        def make_speech(text, _language, path, **_kwargs):
            seconds = 9 if text.startswith('This layer') else 10
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                audio.writeframes(bytes(seconds * 24000 * 2))

        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with (
                patch('backend.pipeline.load_job_documents', return_value=([], [], [])),
                patch('backend.pipeline.plan_scenes', return_value=storyboard),
                patch('backend.pipeline.chat_json', return_value={'additions': additions}) as chat,
                patch('backend.pipeline.synthesize', side_effect=make_speech) as tts,
                patch('backend.pipeline.render'),
                patch('backend.pipeline.export_project'),
            ):
                def fail_second_scene(text, language, path, **kwargs):
                    if text.endswith('step 2'):
                        raise ProviderError('Interrupted speech synthesis')
                    make_speech(text, language, path, **kwargs)

                tts.side_effect = fail_second_scene
                with self.assertRaises(ProviderError):
                    run_job(job, folder, lambda **_changes: None)
                chat.assert_not_called()
                self.assertEqual(tts.call_count, 2)

                resumed = {**job, 'revision': {'stage': 'production', 'calibrate_duration': True}}
                tts.reset_mock()
                tts.side_effect = make_speech
                run_job(resumed, folder, lambda **_changes: None)
                chat.assert_called_once()
                self.assertEqual(tts.call_count, 5)
                plan = json.loads((folder / 'storyboard-plan.json').read_text())
                self.assertTrue(plan['duration_extension_attempted'])
                self.assertTrue(plan['scenes'][0]['narration'].endswith(additions['scene-1']))
                report = json.loads((folder / 'evaluation.json').read_text())
                self.assertEqual(report['timing']['manifest_duration_seconds'], 60.0)
                self.assertEqual(report['timing']['target_delta_seconds'], 0.0)
                self.assertEqual(report['timing']['issues'], [])

                # The production checkpoint reuses both the original and extended speech cache.
                tts.reset_mock()
                chat.reset_mock()
                run_job({**job, 'revision': {'stage': 'production'}}, folder, lambda **_changes: None)
                tts.assert_not_called()
                chat.assert_not_called()

                manual = {**job, 'revision': {
                    'stage': 'production',
                    'narrations': {str(i): f'This layer uses the same weights at step {i}' for i in range(1, 4)},
                }}
                run_job(manual, folder, lambda **_changes: None)
                tts.assert_not_called()
                chat.assert_not_called()
                report = json.loads((folder / 'evaluation.json').read_text())
                self.assertLess(report['timing']['target_delta_seconds'], -20)
                self.assertIn('target_duration_mismatch', [finding['code'] for finding in report['findings']])
