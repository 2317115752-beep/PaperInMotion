"""Use spoken segments to drive the shared animation and subtitle timeline."""
import hashlib
import json
import math
from pathlib import Path
import re
import wave

FPS = 24
PAUSE = .12
MIN_PLAYBACK_RATE = .92
MAX_PLAYBACK_RATE = 1.10
MIN_SCENE_TAIL = round(.20 * FPS)
IDEAL_SCENE_TAIL = round(.35 * FPS)
MAX_SCENE_TAIL = round(1.0 * FPS)


def narration_segments(narration, language):
    # Keep decimals, abbreviations, initials and consecutive closing quotation marks intact.
    segments = []
    for paragraph in re.split(r'\n\s*\n', narration):
        text = ' '.join(paragraph.split())
        boundaries = re.split(r'(?<=[。！？；!?])\s*|(?<=\.)\s+(?=[A-Z“"‘])', text)
        parts = []
        for piece in filter(None, boundaries):
            if parts and re.search(r'(?:\b(?:Dr|Mr|Mrs|Fig|Eq|et al|vs|etc)|\b[A-Z])\.$', parts[-1]):
                parts[-1] += ' ' + piece
            else:
                parts.append(piece)
        segments.extend(parts)
    if not segments:
        raise ValueError('Narration is empty.')
    return segments


def estimated_cues(narration, frames, language):
    segments = narration_segments(narration, language)
    total = sum(map(len, segments))
    offset = 0
    cues = []
    for segment in segments:
        start = round(frames * offset / total)
        offset += len(segment)
        end = round(frames * offset / total)
        if end > start:
            cues.append({'text': segment, 'start_frame': start, 'end_frame': end})
    return cues


def join_speech(parts, output):
    cues, frames = [], 0
    sample_rate = 24000
    gap = round(sample_rate * PAUSE)
    temporary = output.with_suffix('.tmp')
    with wave.open(str(temporary), 'wb') as merged:
        merged.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        for i, (text, path) in enumerate(parts):
            if i:
                merged.writeframesraw(bytes(gap * 2))
                frames += gap
            start = frames
            with wave.open(str(path), 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, sample_rate):
                    raise ValueError('Unexpected PCM format in synthesized narration.')
                frames += audio.getnframes()
                merged.writeframesraw(audio.readframes(audio.getnframes()))
            cues.append({'text': text, 'start_frame': round(start * FPS / sample_rate),
                         'end_frame': max(round(start * FPS / sample_rate) + 1,
                                          round(frames * FPS / sample_rate))})
    temporary.replace(output)
    return frames / sample_rate, cues


def produce_scene_audio(scene, folder, index, language, synthesize, cache_signature):
    output = folder/f'audio-{index+1}.wav'
    inputs = narration_segments(scene['narration'], language)
    cache = folder/'speech-cache'
    cache.mkdir(exist_ok=True)
    parts = []
    for text in inputs:
        digest = hashlib.sha256(json.dumps([cache_signature, language, text]).encode()).hexdigest()
        path = cache/f'{digest}.wav'
        if not path.is_file():
            try:
                synthesize(text, language, path, diagnostics_path=folder/'model_calls.jsonl', streaming=True)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        parts.append((text, path))
    seconds, cues = join_speech(parts, output)
    scene.update(audio_path=str(output), audio_duration=seconds,
                 duration_frames=math.ceil((seconds+.35)*FPS), cues=cues)
    return len(parts)


def narration_units(narration, language):
    if language == 'zh':
        return sum(not char.isspace() for char in narration)
    return len(re.findall(r"\w+(?:['’\-]\w+)*", narration))


def narration_shortfalls(scenes, target_seconds, language):
    target_frames = target_seconds * FPS
    total_audio = sum(scene['audio_duration'] for scene in scenes)
    if total_audio * FPS / MIN_PLAYBACK_RATE + len(scenes) * MAX_SCENE_TAIL >= target_frames:
        return [0] * len(scenes)
    unit_count = sum(narration_units(scene['narration'], language) for scene in scenes)
    pace = unit_count / total_audio if total_audio else (5.6 if language == 'zh' else 2.5)
    target_audio = target_seconds - len(scenes) * IDEAL_SCENE_TAIL / FPS
    shortfall = target_audio - total_audio
    weights = [max(0, target_audio / len(scenes) - scene['audio_duration']) for scene in scenes]
    weight_sum = sum(weights)
    return [round(shortfall * pace * weight / weight_sum) for weight in weights]


def fit_scene_durations(scenes, target_seconds):
    """Fit adjusted speech and short chapter pauses into one shared frame schedule."""
    target_frames = target_seconds * FPS
    count = len(scenes)
    audio_seconds = sum(scene['audio_duration'] for scene in scenes)
    natural_frames = sum(math.ceil(scene['audio_duration'] * FPS) for scene in scenes)
    rate = 1.0
    if not natural_frames + MIN_SCENE_TAIL * count <= target_frames <= natural_frames + MAX_SCENE_TAIL * count:
        desired_audio_frames = max(1, target_frames - IDEAL_SCENE_TAIL * count)
        rate = min(MAX_PLAYBACK_RATE, max(MIN_PLAYBACK_RATE, audio_seconds * FPS / desired_audio_frames))
    speech_frames = [math.ceil(scene['audio_duration'] * FPS / rate) for scene in scenes]
    tail_frames = min(MAX_SCENE_TAIL * count, max(MIN_SCENE_TAIL * count, target_frames - sum(speech_frames)))
    pause, extra = divmod(tail_frames, count)
    for index, (scene, speech_end) in enumerate(zip(scenes, speech_frames)):
        scene['duration_frames'] = speech_end + pause + (index < extra)
        if rate != 1.0:
            scene['audio_duration'] /= rate
            scene['audio_playback_rate'] = rate
            previous_end = 0
            for cue in scene['cues']:
                start = max(previous_end, min(speech_end - 1, round(cue['start_frame'] / rate)))
                end = min(speech_end, max(start + 1, round(cue['end_frame'] / rate)))
                cue.update(start_frame=start, end_frame=end)
                previous_end = end


def schedule_beats(scene):
    labels = scene.get('beat_labels') or scene.get('nodes') or scene.get('bullets') or [scene['title']]
    cues = scene['cues']
    requested = scene.get('beat_cues', [])
    if len(requested) != len(labels) or requested != sorted(requested) or any(i < 0 or i >= len(cues) for i in requested):
        requested = []
    if not cues:
        return [{'label': label, 'start_frame': 0} for label in labels]
    # Explicit model associations are preferred. Unspecified steps remain inside the
    # corresponding measured spoken segment, with ordered timing for multi-step cues.
    beats = []
    for i, label in enumerate(labels):
        if requested:
            cue_index = requested[i]
            cue = cues[cue_index]
            count = requested.count(cue_index)
            position = requested[:i].count(cue_index)
            frame = cue['start_frame'] + (cue['end_frame'] - cue['start_frame']) * position // count
        else:
            position = i * len(cues) / len(labels)
            cue = cues[int(position)]
            frame = cue['start_frame'] + round((cue['end_frame'] - cue['start_frame']) * (position % 1))
        beats.append({'label': label, 'start_frame': frame})
    return beats


def dump_srt(path, scenes, language):
    def timestamp(frames):
        ms = round(frames*1000/FPS)
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        seconds, ms = divmod(ms, 1000)
        return f'{h:02}:{m:02}:{seconds:02},{ms:03}'

    blocks, offset = [], 0
    for scene in scenes:
        cues = scene.get('cues')
        if cues is None:
            frames = round(scene.get('audio_duration', scene['duration_frames']/FPS)*FPS)
            cues = estimated_cues(scene['narration'], frames, language)
        for cue in cues:
            start, end = (timestamp(offset+cue[key]) for key in ('start_frame', 'end_frame'))
            blocks.append(f"{len(blocks)+1}\n{start} --> {end}\n{cue['text']}\n")
        offset += scene['duration_frames']
    Path(path).write_text('\n'.join(blocks), encoding='utf-8')
