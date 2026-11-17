"""API-free audio/video integration check using a synthetic tone, never speech."""
from pathlib import Path
import json
import math
import struct
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.pipeline import demo_storyboard, save_json

folder = ROOT/'data/qa/audio'
folder.mkdir(parents=True, exist_ok=True)
audio = folder/'synthetic-tone.wav'
rate = 24000
with wave.open(str(audio), 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(rate)
    wav.writeframes(b''.join(struct.pack('<h', round(3000*math.sin(2*math.pi*440*i/rate))) for i in range(rate*2)))
scene = demo_storyboard('en')[0]['scenes'][2]
scene.update(title='Audio/video integration check', narration='Synthetic test tone. This is not generated speech.', duration_frames=60, audio_duration=2, audio_path=str(audio))
manifest = dict(title='Synthetic tone integration test', paper_title='Synthetic tone integration test', language='en', is_demo=False, scenes=[scene])
save_json(folder/'manifest.json', manifest)
subprocess.run(['node', str(ROOT/'renderer/render.mjs'), str(folder/'manifest.json'), str(folder/'video.mp4')], cwd=ROOT, check=True)
print('Render complete. Verify the MP4 contains h264 video and AAC audio, duration 2.5 seconds.')
