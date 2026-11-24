"""Use spoken segments to drive the shared animation and subtitle timeline."""
import hashlib
import json
import math
from pathlib import Path
import re
import wave

FPS = 24
PAUSE = .12


def narration_segments(narration, language):
    text = ' '.join(narration.split())
    # Keep decimals, abbreviations, initials and consecutive closing quotation marks intact.
    boundaries = re.split(r'(?<=[。！？；!?])\s*|(?<=\.)\s+(?=[A-Z“"‘])', text)
    segments = []
    for piece in boundaries:
        if not piece:
            continue
        if segments and re.search(r'(?:\b(?:Dr|Mr|Mrs|Fig|Eq|et al|vs|etc)|\b[A-Z])\.$', segments[-1]):
            segments[-1] += ' ' + piece
        else:
            segments.append(piece)
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
