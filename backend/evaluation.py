"""Measure rendered artifacts and keep semantic and human scores separate."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
USAGE_FIELDS = ('prompt_tokens', 'completion_tokens', 'speech_input_tokens', 'speech_output_tokens')


def write_json(path, data):
    """Write locally generated reports without leaving partial JSON on interruption."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix=path.name + '.', delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def read_jsonl(path, *, strict=False):
    """Read complete event lines from a potentially interrupted log."""
    try:
        with Path(path).open(encoding='utf-8') as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    if strict:
                        raise ValueError(f'Invalid JSON on line {number} of {path}.') from None
                    continue
                if isinstance(item, dict):
                    yield item
                elif strict:
                    raise ValueError(f'Expected an object on line {number} of {path}.')
    except OSError:
        if strict:
            raise


def measured_usage(path):
    events = list(read_jsonl(path))
    report = {'attempts_logged': len(events)}
    for name in USAGE_FIELDS:
        values = [event[name] for event in events if type(event.get(name)) is int and event[name] >= 0]
        report[name] = sum(values) if values else None
    return report


def measure_cost(usage, rates):
    """Use explicit user-supplied rates per million tokens and label missing usage."""
    available = {}
    for field in USAGE_FIELDS:
        value, rate = usage.get(field), rates.get(field)
        if value is not None and type(rate) in (float, int) and math.isfinite(rate) and rate >= 0:
            available[field] = value * rate / 1_000_000
    return {'currency': rates.get('currency'), 'amount': round(sum(available.values()), 8) if available else None,
            'missing_token_fields': [f for f in USAGE_FIELDS if f not in available]}


def media_binary(name):
    path = shutil.which(name)
    if path:
        return path
    for candidate in (ROOT/'node_modules'/'@remotion').glob('compositor-*/' + name):
        if candidate.is_file():
            return str(candidate)
    return None


def media_environment(binary):
    # Remotion ships the shared libraries beside its executable.
    directory = Path(binary).parent
    if directory.name.startswith('compositor-'):
        key = 'DYLD_LIBRARY_PATH' if (directory/'libavdevice.dylib').is_file() else 'LD_LIBRARY_PATH'
        previous = os.environ.get(key)
        return {**os.environ, key: os.pathsep.join(filter(None, (str(directory), previous)))}
    return None


def probe_video(path):
    path = Path(path)
    report = {'file_bytes': path.stat().st_size if path.is_file() else 0, 'probe_available': False}
    binary = media_binary('ffprobe')
    if not binary or not report['file_bytes']:
        return report
    try:
        process = subprocess.run(
            [binary, '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration',
             '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=25, env=media_environment(binary),
        )
        data = json.loads(process.stdout)
        streams = data.get('streams', [])
        video = next((stream for stream in streams if stream.get('codec_type') == 'video'), {})
        duration = float(data['format']['duration'])
        if not math.isfinite(duration):
            raise ValueError('duration')
        return {**report, 'probe_available': True, 'has_video': bool(video),
                'has_audio': any(stream.get('codec_type') == 'audio' for stream in streams),
                'width': video.get('width'), 'height': video.get('height'), 'duration_seconds': duration}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return {**report, 'probe_error': 'Could not inspect the encoded video.'}


def dot(left, right):
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def independent_example_checks(example):
    """Recompute selected checkpoints using scalar code outside the NumPy executor."""
    if not isinstance(example, dict):
        return []
    fixtures = {}
    try:
        if example.get('kind') == 'low_rank':
            baseline = [dot(row, example['input']) for row in example['base']]
            hidden = [dot(row, example['input']) for row in example['A']]
            delta = [example.get('scale', 1) * dot(row, hidden) for row in example['B']]
            output = [a + b for a, b in zip(baseline, delta, strict=True)]
            fixtures = {'baseline': baseline, 'hidden': hidden, 'delta': delta, 'output': output}
        elif example.get('kind') == 'scaled_dot_attention':
            scores = [[dot(query, key) / math.sqrt(len(query)) for key in example['K']]
                      for query in example['Q']]
            weights = []
            for row in scores:
                exponents = [math.exp(score - max(row)) for score in row]
                weights.append([value / math.fsum(exponents) for value in exponents])
            output = [[dot(row, column) for column in zip(*example['V'], strict=True)] for row in weights]
            fixtures = {'scores': scores, 'weights': weights, 'output': output}
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return [{'checkpoint': 'input_schema', 'passed': False}]

    def close(expected, actual):
        if isinstance(expected, list):
            return (isinstance(actual, list) and len(expected) == len(actual)
                    and all(close(a, b) for a, b in zip(expected, actual)))
        return type(actual) in (int, float) and math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-8)

    return [{'checkpoint': name, 'passed': close(expected, example.get(name))}
            for name, expected in fixtures.items()]


def timing_checks(manifest):
    fps = manifest.get('fps', 24)
    if type(fps) not in (int, float) or fps <= 0:
        raise ValueError('Manifest frame rate must be positive.')
    issues, offsets = [], []
    matched = 0
    required = 0
    total_frames = 0
    for index, scene in enumerate(manifest.get('scenes', []), 1):
        frames = scene.get('duration_frames', 0)
        end_previous = 0
        total_frames += frames
        cues = scene.get('cues') or []
        if not cues:
            issues.append({'scene': index, 'type': 'missing_cues'})
        for cue in cues:
            start, end = cue.get('start_frame'), cue.get('end_frame')
            if (type(start) is not int or type(end) is not int
                    or not end_previous <= start < end <= frames):
                issues.append({'scene': index, 'type': 'cue_bounds_or_overlap'})
            else:
                end_previous = end
        for beat in scene.get('beats', []):
            required += 1
            point = beat.get('start_frame')
            if type(point) is not int or not 0 <= point < frames:
                issues.append({'scene': index, 'type': 'beat_outside_scene'})
                continue
            reference = beat.get('expected_spoken_frame')
            if type(reference) is int and 0 <= reference < frames:
                offsets.append(abs(point - reference) * 1000 / fps)
                matched += 1
    return {'manifest_duration_seconds': round(total_frames / fps, 3), 'issues': issues,
            'required_key_events': required, 'events_with_independent_spoken_reference': matched,
            'median_absolute_offset_ms': round(median(offsets), 2) if offsets else None}


def evaluate_job(folder, manifest):
    """Save repeatable mechanical checks for a completed job on the local machine."""
    folder = Path(folder)
    timing = timing_checks(manifest)
    media = probe_video(folder/'video.mp4')
    evidence = read_json(folder/'evidence-check.json', {}) or {}
    example = read_json(folder/'example.json')
    checks = [] if manifest.get('condition', 'C') != 'C' else independent_example_checks(example)
    findings = []
    for item in timing['issues']:
        findings.append({'stage': 'production', 'code': item['type'], 'scene': item['scene']})
    if not media['file_bytes']:
        findings.append({'stage': 'production', 'code': 'missing_video'})
    if media.get('probe_available'):
        if not media['has_video'] or not (manifest.get('is_demo') or media['has_audio']):
            findings.append({'stage': 'production', 'code': 'missing_stream'})
        requested_size = manifest.get('width'), manifest.get('height')
        if all(requested_size) and requested_size != (media['width'], media['height']):
            findings.append({'stage': 'production', 'code': 'render_size_mismatch'})
        if abs(media['duration_seconds'] - timing['manifest_duration_seconds']) > 0.25:
            findings.append({'stage': 'production', 'code': 'duration_mismatch'})
    target = manifest.get('target_duration_seconds')
    if type(target) in (int, float) and target > 0:
        measured = media.get('duration_seconds', timing['manifest_duration_seconds'])
        timing['target_duration_seconds'] = target
        timing['target_delta_seconds'] = round(measured - target, 3)
        if abs(measured - target) > target * .05:
            findings.append({'stage': 'production', 'code': 'target_duration_mismatch'})
    if any(not check['passed'] for check in checks):
        findings.append({'stage': 'example', 'code': 'calculation_checkpoint'})
    if evidence.get('rejected_claims'):
        findings.append({'stage': 'understanding', 'code': 'unresolved_source_reference'})
    report = {
        'schema_version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'condition': manifest.get('condition', 'C'),
        'runtime_seconds': manifest.get('runtime_seconds'),
        'media': media, 'timing': timing,
        'evidence_reference_checks': {field: evidence.get(field) for field in
                                      ('total_claims', 'verified_claims', 'rejected_claims')},
        'independent_calculation_checks': checks,
        'executor_checkpoints': example.get('checkpoints', []) if isinstance(example, dict) else [],
        'usage': measured_usage(folder/'model_calls.jsonl'),
        'findings': findings,
        'manual_measurements': ['factual_support', 'mechanism_depth', 'content_coverage',
                                'calculation_presentation', 'visual_defect_frame_rate', 'comprehension',
                                'clarity', 'readability', 'pacing', 'visual_appeal'],
    }
    write_json(folder/'evaluation.json', report)
    return report


def revision_delta(before, after):
    """Compare identically defined mechanical findings on two job versions."""
    def identity(row):
        return row['stage'], row['code'], row.get('scene')

    old = {identity(row): row for row in before['findings']}
    new = {identity(row): row for row in after['findings']}
    usage = {}
    for key in USAGE_FIELDS:
        first, second = before['usage'].get(key), after['usage'].get(key)
        usage[key] = second - first if first is not None and second is not None else None
    return {
        'resolved': [row for key, row in old.items() if key not in new],
        'remaining': [row for key, row in new.items() if key in old],
        'introduced': [row for key, row in new.items() if key not in old],
        'measured_token_delta': usage,
        'needs_semantic_recheck': ['factual_support', 'mechanism_depth', 'content_coverage'],
    }


MECHANICAL_ACTIONS = {
    'missing_cues': 'Check narration segmentation and start and end frames.',
    'cue_bounds_or_overlap': 'Rebuild the shared subtitle schedule inside the scene duration.',
    'beat_outside_scene': 'Clamp or reschedule the action inside the scene.',
    'missing_video': 'Inspect the render log and verify the MP4 export.',
    'render_size_mismatch': 'Use the dimensions supplied in the scene manifest.',
    'missing_stream': 'Verify the intended video and narration streams in the export.',
    'duration_mismatch': 'Compare rendered duration to the accumulated scene durations.',
    'target_duration_mismatch': 'Review narration coverage and compare the rendered duration to the requested target.',
    'calculation_checkpoint': 'Recheck the plan inputs and run the example again.',
    'unresolved_source_reference': 'Choose a paper excerpt supporting each disputed claim.',
}


def feedback_plan(evaluation, ratings=()):
    """Route verified observations and propose focused changes for team review."""
    issues = {}
    for finding in evaluation.get('findings', []):
        stage = finding['stage']
        issues.setdefault(stage, []).append({
            'observed_by': 'mechanical_check',
            'issue': finding['code'],
            'evidence': {'scene': finding.get('scene')},
            'suggested_change': MECHANICAL_ACTIONS.get(finding['code'], 'Inspect the relevant export and scene records.'),
        })
    for rating in ratings:
        for note in rating.get('notes') or []:
            if not isinstance(note, dict) or note.get('stage') not in ('understanding', 'example', 'storyboard', 'production'):
                continue
            if any(not isinstance(note.get(key), str) or not note[key].strip()
                   for key in ('issue', 'evidence', 'suggested_change')):
                continue
            stage = note['stage']
            issues.setdefault(stage, []).append({
                **{key: note[key][:600] for key in ('issue', 'evidence', 'suggested_change')},
                'observed_by': rating.get('judge', 'reviewer'),
            })
    return {'stages': [{'stage': stage, 'issues': issues[stage], 'requires_review': True}
                       for stage in ('understanding', 'example', 'storyboard', 'production') if stage in issues]}
