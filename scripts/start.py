from pathlib import Path
from datetime import datetime
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser

root = Path(__file__).resolve().parent.parent
python = root/'.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
url = 'http://127.0.0.1:8000'
if not python.exists():
    sys.exit('Install dependencies first: uv venv --python 3.12 && uv pip install -r requirements.txt')
if not (root/'web/dist/index.html').exists():
    sys.exit('Build the interface first: npm install && npm run build')

def healthy():
    try:
        with urllib.request.urlopen(url+'/api/health', timeout=1) as response:
            return b'"status":"ok"' in response.read()
    except OSError:
        return False

if healthy():
    print('Paper in Motion is already running: '+url, flush=True)
    if '--no-browser' not in sys.argv:
        webbrowser.open(url)
    sys.exit(0)

if '--no-browser' not in sys.argv:
    def open_when_ready():
        import time
        for _ in range(30):
            if healthy():
                webbrowser.open(url)
                return
            time.sleep(.5)
    threading.Thread(target=open_when_ready, daemon=True).start()

(root/'data').mkdir(exist_ok=True)
log_path = root/'data/server.log'
print('Paper in Motion: '+url+'\nLog: '+str(log_path)+'\nPress Ctrl+C to stop.', flush=True)
with log_path.open('a', encoding='utf-8', buffering=1) as log:
    log.write('\nStartup '+datetime.now().isoformat()+'\n')
    process = subprocess.Popen([str(python), '-u', '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000'], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        code = 0
sys.exit(code)
