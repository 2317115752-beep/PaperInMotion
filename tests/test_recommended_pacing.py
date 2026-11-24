import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from backend.pipeline import (
    VISUAL_HOLD_TARGET_SECONDS,
    estimated_visual_holds,
    plan_scenes,
    recommend_duration,
    run_job,
    run_recommendation,
    save_json,
    visual_focus_points,
)
from backend.timing import FPS, estimated_cues, narration_units


class RecommendedPacingTests(unittest.TestCase):
    def test_recommendation_counts_distinct_grounded_teaching_points(self):
        pages = [
            {'page': 1, 'text': 'The method applies a shared transform to each feature.'},
            {'page': 2, 'text': 'The second section describes the same shared transform.'},
        ]
        method = {
            'claims': [
                {'claim': 'Shared transform', 'evidence_id': 'p1-e1'},
                {'claim': 'Shared-transform!', 'evidence_id': 'p2-e1'},
                {'claim': 'Unsupported outcome', 'evidence_id': 'p99-e1'},
            ],
            'operations': [
                {'name': 'Shared transform', 'evidence_id': 'p1-e1'},
                {'name': 'Combine features', 'evidence_id': 'p1-e1'},
                {'name': 'Ungrounded step'},
            ],
        }

        recommendation = recommend_duration(method, pages, 'introductory')
        self.assertEqual(recommendation['teaching_points'], 2)
        self.assertEqual(recommendation['duration'], 31)

    def test_lesson_outline_can_recommend_four_minutes_or_partial_minutes(self):
        pages = [{'page': 1, 'text': 'The method applies a shared transform to each feature.'}]
        points = [
            {'title': f'Teaching point {index}', 'evidence_id': 'p1-e1', 'seconds': 24,
             'visual_changes': ['Show input', 'Show output']}
            for index in range(10)
        ]
        method = {'lesson_outline': [*points, {**points[0], 'title': 'Uncited', 'evidence_id': 'p99-e1'}]}
        self.assertEqual(recommend_duration(method, pages, 'advanced'), {'duration': 240, 'teaching_points': 10})
        points[0]['visual_changes'] = ['Show input', 'Show input!']
        points[1]['seconds'] = 23
        self.assertEqual(recommend_duration(method, pages, 'advanced'), {'duration': 227, 'teaching_points': 10})

    def test_storyboard_uses_the_outline_and_its_evidence_at_a_custom_duration(self):
        pages = [
            {'page': 1, 'text': 'The method applies a shared transform to each feature.'},
            {'page': 2, 'text': 'The comparison visualizes independently measured outputs.'},
        ]
        outline = [
            {'title': title, 'evidence_id': 'p2-e1', 'seconds': 29,
             'visual_changes': ['Show input', 'Apply transform', 'Read output']}
            for title in ('Background', 'Mechanism', 'Comparison')
        ]
        method = {'lesson_outline': outline, 'claims': [{'claim': 'Shared transform', 'evidence_id': 'p1-e1'}]}
        raw = {'title': 'Lesson', 'scenes': [
            {'title': point['title'], 'narration': 'Follow the example.', 'evidence_ids': ['p2-e1']}
            for point in outline
        ]}
        with patch('backend.pipeline.chat_json', return_value=raw) as chat:
            plan_scenes(method, None, 'en', 87, pages, recommended_pacing=True)
        prompt, payload = chat.call_args.args
        self.assertIn('Produce exactly 3 scenes', prompt)
        request = json.loads(payload)
        self.assertEqual(request['method']['lesson_outline'], outline)
        self.assertEqual({item['id'] for item in request['available_evidence']}, {'p1-e1', 'p2-e1'})

    def test_visual_focus_requires_unique_labels_at_explicit_cues(self):
        scene = {
            'title': 'The method',
            'narration': (
                'Start by reviewing this method. Compare the two intermediate states. '
                'This cue repeats an existing view. The signals are joined at this point. '
                'Now read the output aloud. Continue to the next example.'
            ),
            'nodes': ['The method', 'Feature map', 'feature-map', 'The signals are joined at this point.'],
            'beat_cues': [0, 1, 2, 3],
            'visual_beats': [{'cue': 4, 'label': 'Output distribution'}],
        }
        cues = [
            {'text': sentence.strip() + '.', 'start_frame': index * 3 * FPS, 'end_frame': (index + 1) * 3 * FPS}
            for index, sentence in enumerate(scene['narration'].rstrip('.').split('. '))
        ]
        self.assertEqual(visual_focus_points({**scene, 'cues': cues}), [
            {'label': 'Feature map', 'start_frame': 3 * FPS},
            {'label': 'Output distribution', 'start_frame': 12 * FPS},
        ])

        frames = round((narration_units(scene['narration'], 'en') / 2.5 + .35) * FPS)
        estimated = estimated_cues(scene['narration'], frames, 'en')
        first_change = estimated[1]['start_frame']
        second_change = estimated[4]['start_frame']
        expected_hold = max(first_change, second_change - first_change, frames - second_change)
        self.assertEqual(estimated_visual_holds({'scenes': [scene]}, 'en'), [expected_hold])
        scene['visual_beats'] = []
        scene['beat_cues'] = []
        self.assertEqual(estimated_visual_holds({'scenes': [scene]}, 'en'), [frames])

    def test_title_can_advance_through_the_existing_leads(self):
        cues = [{'text': f'Opening sentence {index}.', 'start_frame': index * 4 * FPS}
                for index in range(4)]
        scene = {'visual_type': 'title', 'title': 'How it works', 'cues': cues,
                 'bullets': ['Input choices', 'Result comparison']}
        changes = visual_focus_points(scene)
        self.assertEqual(changes, [
            {'label': 'Input choices', 'start_frame': 0},
            {'label': 'Result comparison', 'start_frame': 8 * FPS},
        ])

    def test_generation_reuses_recommendation_and_keeps_natural_speech_length(self):
        pages = [{'page': 1, 'text': 'The method applies a shared transform to each feature.'}]
        analysis = {
            'paper_title': 'Shared features',
            'claims': [
                {'claim': 'Apply a shared transform', 'evidence_id': 'p1-e1'},
                {'claim': 'Unsupported outcome', 'evidence_id': 'p99-e1', 'quote_verified': True},
            ],
        }
        raw_plan = {'title': 'Shared features', 'scenes': [
            {'title': f'View {number}', 'narration': 'Start with the input. Trace the shared transform.',
             'evidence_ids': ['p1-e1'], 'visual_beats': [{'cue': 1, 'label': 'Transformed features'}]}
            for number in range(1, 5)
        ]}

        def extract(folder):
            save_json(folder / 'sources.json', pages)
            return pages, [], []

        def synthesize(_text, _language, path, **_kwargs):
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                audio.writeframes(bytes(3 * 24000 * 2))

        job = {'id': 'recommended-test', 'is_demo': False, 'language': 'en', 'condition': 'B'}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with (
                patch('backend.pipeline.load_job_documents', side_effect=extract) as load_documents,
                patch('backend.pipeline.chat_json', side_effect=[analysis, raw_plan]) as chat,
                patch('backend.pipeline.synthesize', side_effect=synthesize),
                patch('backend.pipeline.fit_scene_durations') as fit_duration,
                patch('backend.pipeline.render'),
                patch('backend.pipeline.export_project'),
            ):
                recommendation = run_recommendation(job, folder, lambda **changes: job.update(changes))
                job.update(duration=recommendation['duration'], from_recommendation=True, recommended_pacing=True)
                run_job(job, folder, lambda **changes: job.update(changes))

            manifest = json.loads((folder / 'manifest.json').read_text())
        load_documents.assert_called_once()
        self.assertEqual([call.kwargs['task'] for call in chat.call_args_list], ['论文理解', '分镜编排'])
        fit_duration.assert_not_called()
        self.assertEqual(recommendation['teaching_points'], 1)
        self.assertEqual(job['status'], 'complete')
        self.assertLess(job['actual_duration'], recommendation['duration'])
        self.assertEqual(manifest['target_duration_seconds'], 30)
        self.assertEqual(manifest['visual_pacing']['target_hold_seconds'], VISUAL_HOLD_TARGET_SECONDS)
        for scene in manifest['scenes']:
            self.assertEqual(scene['pacing_focus'], [
                {'label': 'Transformed features', 'start_frame': scene['cues'][1]['start_frame']},
            ])
