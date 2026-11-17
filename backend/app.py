from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import traceback
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT/'.env')
from .providers import get_config, ProviderError, redact
from .pipeline import run_job, save_json

DATA = ROOT/'data'
DATA.mkdir(exist_ok=True)
JOBS, LOCK = {}, RLock()
POOL = ThreadPoolExecutor(max_workers=1)


@asynccontextmanager
async def lifespan(app):
    for path in DATA.glob('*/job.json'):
        try:
            job = json.loads(path.read_text('utf-8'))
            if job['status'] in ('running', 'queued'):
                job.update(status='failed', error='服务重启中断了任务，请重新生成。', message='任务已中断')
            JOBS[job['id']] = job
        except (ValueError, KeyError, OSError):
            continue
    yield
    POOL.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title='Paper in Motion', version='0.1.0', lifespan=lifespan)


@app.middleware('http')
async def local_guard(request, call_next):
    if request.method == 'POST':
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:5173','http://localhost:5173'):
            return JSONResponse({'detail': '仅允许本机页面提交任务。'}, status_code=403)
    result = await call_next(request)
    result.headers['X-Content-Type-Options'] = 'nosniff'
    return result


@app.get('/api/config')
def config():
    load_dotenv(ROOT/'.env', override=True)
    settings = get_config()
    return {
        'model': settings['chat_model'], 'tts_model': settings['tts_model'],
        'provider': settings['provider'], 'region': settings['region'],
        'endpoint_mode': settings['endpoint_mode'], 'endpoint_label': settings['endpoint_label'],
        'workspace_configured': settings['workspace_configured'],
        'api_configured': not bool(settings['configuration_error']),
        'configuration_error': settings['configuration_error'], 'max_upload_mb': 25,
    }


@app.get('/api/health')
def health():
    return {'status':'ok', 'version':'0.1.0'}


def busy_check():
    if any(job['status'] in ('queued','running') for job in JOBS.values()):
        raise HTTPException(409, '已有任务运行中，请等待完成后再提交。')


def new_job(language, duration, demo, filename):
    job_id = uuid4().hex
    folder = DATA/job_id
    folder.mkdir()
    job = {'id':job_id,'status':'queued','stage':'reading','progress':0,'message':'任务已创建','language':language,'duration':duration,'title':'LoRA 演示' if demo else filename,'is_demo':demo,'scenes':[],'files':{},'warnings':[],'model':get_config()['chat_model'],'created_at':datetime.now(timezone.utc).isoformat()}
    JOBS[job_id] = job
    save_json(folder/'job.json', job)
    return job, folder


def worker(job, folder):
    def update(**changes):
        with LOCK:
            job.update(changes)
            save_json(folder/'job.json', job)
    try:
        update(status='running')
        run_job(job, folder, update)
    except Exception as exc:
        logging.error('Job %s failed (%s); see data/%s/error.log', job['id'], type(exc).__name__, job['id'])
        detail = redact(traceback.format_exc())
        (folder/'error.log').write_text(detail, encoding='utf-8')
        message = redact(exc)[:900] if isinstance(exc, (ValueError, ProviderError)) else f'生成失败（{type(exc).__name__}），请检查依赖或网络。'
        update(status='failed', message='任务未完成', error=message)


@app.post('/api/jobs', status_code=202)
async def generate(file: UploadFile = File(...), language: Literal['zh','en'] = Form('zh'), duration: int = Form(120)):
    if duration not in (60,120,180):
        raise HTTPException(422, '时长请选择60、120或180秒。')
    settings = config()
    if not settings['api_configured']:
        raise HTTPException(400, settings['configuration_error'])
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, '请上传PDF论文。')
    with LOCK:
        busy_check()
    data = await file.read(25*1024*1024+1)
    await file.close()
    if len(data)>25*1024*1024:
        raise HTTPException(413, '文件不能超过25MB。')
    if not data.startswith(b'%PDF-'):
        raise HTTPException(400, '文件内容不是有效PDF。')
    with LOCK:
        busy_check()
        job, folder = new_job(language,duration,False,Path(file.filename).name[:150])
        (folder/'paper.pdf').write_bytes(data)
        result = json.loads(json.dumps(job))
        POOL.submit(worker,job,folder)
    return result


@app.post('/api/demo', status_code=202)
def demo(language: Literal['zh','en']='zh'):
    with LOCK:
        busy_check()
        for existing in reversed(list(JOBS.values())):
            if existing['is_demo'] and existing['language']==language and existing['status']=='complete' and (DATA/existing['id']/'video.mp4').is_file():
                return json.loads(json.dumps(existing))
        job,folder = new_job(language,48,True,'LoRA prepared demo')
        result = json.loads(json.dumps(job))
        POOL.submit(worker,job,folder)
    return result


@app.get('/api/jobs')
def list_jobs():
    with LOCK:
        return json.loads(json.dumps(sorted(JOBS.values(), key=lambda j:j['created_at'],reverse=True)[:20]))


@app.get('/api/jobs/{job_id}')
def get_job(job_id:str):
    with LOCK:
        if job_id not in JOBS:
            raise HTTPException(404,'未找到任务。')
        return json.loads(json.dumps(JOBS[job_id]))


@app.api_route('/api/jobs/{job_id}/files/{filename}', methods=['GET','HEAD'])
def file_response(job_id:str,filename:str):
    types = {'video.mp4':'video/mp4','subtitles.srt':'application/x-subrip','storyboard.json':'application/json','project.zip':'application/zip'}
    if job_id not in JOBS or filename not in types or JOBS[job_id]['status']!='complete':
        raise HTTPException(404,'文件尚未生成。')
    path = DATA/job_id/filename
    if not path.is_file():
        raise HTTPException(404,'文件不存在。')
    return FileResponse(path,media_type=types[filename],filename=filename,content_disposition_type='inline' if filename=='video.mp4' else 'attachment')


if (ROOT/'web/dist').exists():
    app.mount('/', StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
