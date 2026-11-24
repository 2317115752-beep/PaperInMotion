from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import re
import shutil
import traceback
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT/'.env')
from .providers import get_config, ProviderError, redact
from .pipeline import DURATION_SCENES, run_job, run_recommendation, save_json

DATA = ROOT/'data'
DATA.mkdir(exist_ok=True)
JOBS, LOCK = {}, RLock()
POOL: ThreadPoolExecutor | None = None
Style = Literal['editorial', 'midnight', 'classroom']
Level = Literal['introductory', 'advanced']
Condition = Literal['A', 'B', 'C']
MAX_UPLOAD = 25 * 1024 * 1024
JOB_ID = re.compile(r'[0-9a-f]{32}')
DELETING_PREFIX = '.deleting-'


class Revision(BaseModel):
    stage: Literal['understanding', 'example', 'storyboard', 'production']
    notes: str = Field(default='', max_length=2000)
    style: Style | None = None
    narrations: dict[str, str] = Field(default_factory=dict, max_length=max(DURATION_SCENES.values()))


class RecommendedGeneration(BaseModel):
    duration: int | None = None
    style: Style = 'editorial'


@asynccontextmanager
async def lifespan(app):
    global POOL
    POOL = ThreadPoolExecutor(max_workers=1)
    for folder in DATA.glob(DELETING_PREFIX + '*'):
        if JOB_ID.fullmatch(folder.name.removeprefix(DELETING_PREFIX)) and not folder.is_symlink():
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                logging.warning('Could not finish deleting job files (%s)', type(exc).__name__)
    for path in DATA.glob('*/job.json'):
        if not JOB_ID.fullmatch(path.parent.name) or path.parent.is_symlink():
            continue
        try:
            job = json.loads(path.read_text('utf-8'))
            if job['id'] != path.parent.name:
                continue
            if job['status'] in ('running', 'queued'):
                job.update(status='failed', error='服务重启中断了任务，请重新生成。', message='任务已中断')
            JOBS[job['id']] = job
        except (ValueError, KeyError, OSError):
            continue
    yield
    POOL.shutdown(wait=True, cancel_futures=True)
    POOL = None


app = FastAPI(title='Paper in Motion', version='1.0.0', lifespan=lifespan)


@app.middleware('http')
async def local_guard(request, call_next):
    if request.method in ('POST', 'DELETE'):
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
    return {'status':'ok', 'version':'1.0.0'}


def busy_check():
    if any(job['status'] in ('queued','running') for job in JOBS.values()):
        raise HTTPException(409, '已有任务运行中，请等待完成后再提交。')


def new_job(language, duration, demo, filename, **options):
    job_id = uuid4().hex
    folder = DATA/job_id
    folder.mkdir()
    job = {'id':job_id,'status':'queued','stage':'reading','progress':0,'message':'任务已创建','language':language,'duration':duration,'title':'LoRA 演示' if demo else filename,'is_demo':demo,'scenes':[],'files':{},'warnings':[],'model':get_config()['chat_model'],'created_at':datetime.now(timezone.utc).isoformat(), **options}
    return job, folder


def worker(job, folder):
    def update(**changes):
        with LOCK:
            job.update(changes)
            save_json(folder/'job.json', job)
    try:
        update(status='running')
        if job.get('pending_recommendation'):
            recommendation = run_recommendation(job, folder, update)
            update(status='ready', stage='understanding', progress=100,
                   recommendation=recommendation, duration=recommendation['duration'],
                   message='Paper analysis ready')
        else:
            run_job(job, folder, update)
    except Exception as exc:
        logging.error('Job %s failed (%s); see data/%s/error.log', job['id'], type(exc).__name__, job['id'])
        detail = redact(traceback.format_exc())
        (folder/'error.log').write_text(detail, encoding='utf-8')
        task = 'Paper analysis' if job.get('pending_recommendation') else 'Generation'
        message = (redact(exc)[:900] if isinstance(exc, (ValueError, ProviderError))
                   else f'{task} failed ({type(exc).__name__}). See the local job log.')
        update(status='failed', message='任务未完成', error=message)



def enqueue(job, folder):
    if POOL is None:
        raise HTTPException(503, 'The rendering worker is unavailable.')
    previous = JOBS.get(job['id'])
    save_json(folder/'job.json', job)
    try:
        POOL.submit(worker, job, folder)
    except RuntimeError:
        if previous is None:
            (folder/'job.json').unlink(missing_ok=True)
        else:
            save_json(folder/'job.json', previous)
        raise HTTPException(503, 'The rendering worker is unavailable.') from None
    JOBS[job['id']] = job
    return json.loads(json.dumps(job))


async def pdf_bytes(file):
    try:
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(400, 'Upload a PDF.')
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, 'Each PDF must be 25 MB or smaller.')
        if not data.startswith(b'%PDF-'):
            raise HTTPException(400, 'The file is not a valid PDF.')
        return data
    finally:
        await file.close()


async def submit_paper(file, supplements, language, duration, **options):
    settings = config()
    if not settings['api_configured']:
        raise HTTPException(400, settings['configuration_error'])
    with LOCK:
        busy_check()
    supplements = supplements or []
    if len(supplements) > 3:
        raise HTTPException(400, 'Upload up to three PDF supplements.')
    data = await pdf_bytes(file)
    additions = [await pdf_bytes(extra) for extra in supplements]
    if len(data) + sum(map(len, additions)) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Total PDF upload must be 50 MB or smaller.')
    with LOCK:
        busy_check()
        job, folder = new_job(language, duration, False, Path(file.filename).name[:150],
                              supplement_count=len(additions), **options)
        (folder/'paper.pdf').write_bytes(data)
        for index, extra in enumerate(additions, 1):
            (folder/f'supplement-{index}.pdf').write_bytes(extra)
        return enqueue(job, folder)


@app.post('/api/jobs', status_code=202)
async def generate(
    file: UploadFile = File(...), language: Literal['zh', 'en'] = Form('zh'),
    duration: int = Form(120), style: Style = Form('editorial'), level: Level = Form('introductory'),
    condition: Condition = Form('C'), supplements: list[UploadFile] | None = File(None),
):
    if duration not in DURATION_SCENES:
        raise HTTPException(422, 'Choose a target length of 60, 120, 180 or 300 seconds.')
    return await submit_paper(file, supplements, language, duration, style=style, level=level, condition=condition)


@app.post('/api/recommendations', status_code=202)
async def recommend(
    file: UploadFile = File(...), language: Literal['zh', 'en'] = Form('zh'),
    level: Level = Form('introductory'), condition: Literal['B', 'C'] = Form('C'),
    supplements: list[UploadFile] | None = File(None),
):
    return await submit_paper(file, supplements, language, 120, level=level, condition=condition,
                              pending_recommendation=True)


@app.post('/api/jobs/{job_id}/generate', status_code=202)
def generate_recommendation(job_id: str, generation: RecommendedGeneration):
    with LOCK:
        original = JOBS.get(job_id)
        if original is None:
            raise HTTPException(404, 'Job not found.')
        if original['status'] != 'ready' or not original.get('pending_recommendation'):
            raise HTTPException(409, 'Wait for the paper analysis before generating a video.')
        busy_check()
        recommended = original['recommendation']['duration']
        duration = generation.duration if generation.duration is not None else recommended
        if duration != recommended and duration not in DURATION_SCENES:
            raise HTTPException(422, 'Choose a target length of 60, 120, 180 or 300 seconds.')
        folder = DATA/job_id
        if not all((folder/name).is_file() for name in ('paper.pdf', 'method.json', 'sources.json')):
            raise HTTPException(409, 'The saved paper analysis is unavailable.')
        settings = config()
        if not settings['api_configured']:
            raise HTTPException(400, settings['configuration_error'])
        job = dict(original, status='queued', stage='storyboard', progress=0, message='任务已创建',
                   duration=duration, style=generation.style, pending_recommendation=False,
                   from_recommendation=True, recommended_pacing=duration == recommended)
        return enqueue(job, folder)


@app.post('/api/demo', status_code=202)
def demo(language: Literal['zh', 'en'] = 'zh', style: Style = 'editorial',
         topic: Literal['lora', 'cliff'] = 'lora'):
    with LOCK:
        busy_check()
        for existing in reversed(list(JOBS.values())):
            if (existing['is_demo'] and existing['language'] == language and existing.get('demo_topic') == topic
                    and existing.get('style') == style and existing['status'] == 'complete'
                    and (DATA/existing['id']/'video.mp4').is_file()):
                return json.loads(json.dumps(existing))
        job, folder = new_job(language, 32 if topic == 'cliff' else 48, True, topic.upper(),
                              style=style, demo_topic=topic)
        return enqueue(job, folder)


@app.post('/api/jobs/{job_id}/revise', status_code=202)
def revise(job_id: str, revision: Revision):
    with LOCK:
        busy_check()
        original = JOBS.get(job_id)
        if not original or original['status'] != 'complete' or original['is_demo']:
            raise HTTPException(404, 'Choose a completed paper video to revise.')
        condition = original.get('condition', 'C')
        if revision.stage == 'example' and condition != 'C':
            raise HTTPException(422, 'Example execution is available in condition C.')
        if revision.stage != 'production' and not revision.notes.strip():
            raise HTTPException(422, 'Describe the change you want to make.')
        if revision.narrations and revision.stage != 'production':
            raise HTTPException(422, 'Direct narration edits apply to production revisions.')
        for index, text in revision.narrations.items():
            if index not in {str(i+1) for i in range(len(original.get('scenes', [])))} or not 1 <= len(text.strip()) <= 2200:
                raise HTTPException(422, 'Choose a valid scene and enter 1–2200 characters of narration.')
        source = DATA/job_id
        required = ['paper.pdf', 'method.json']
        if revision.stage == 'production':
            required.append('storyboard-plan.json')
        if any(not (source/name).is_file() for name in required):
            raise HTTPException(409, 'The original job is missing files required for revision.')
        if (revision.stage != 'production' or revision.narrations or not (source/'speech-cache').is_dir()) and not config()['api_configured']:
            raise HTTPException(400, config()['configuration_error'])
        job, folder = new_job(original['language'], original['duration'], False, original['title'],
                              style=revision.style or original.get('style', 'editorial'),
                              level=original.get('level', 'introductory'), condition=condition,
                              parent_id=job_id, revision=revision.model_dump(exclude_none=True))
        if original.get('recommended_pacing') and not revision.narrations:
            job['recommended_pacing'] = True
        for path in [source/'paper.pdf', source/'method.json', source/'storyboard-plan.json',
                     source/'example.json', source/'sources.json', source/'evidence-excerpts.json',
                     source/'evidence-check.json', *source.glob('supplement-*.pdf')]:
            if path.is_file():
                shutil.copy2(path, folder/path.name)
        for name in ('speech-cache', 'assets'):
            if (source/name).is_dir():
                shutil.copytree(source/name, folder/name)
        return enqueue(job, folder)


@app.post('/api/jobs/{job_id}/retry', status_code=202)
def retry_job(job_id: str):
    with LOCK:
        busy_check()
        original = JOBS.get(job_id)
        if not original or original['status'] != 'failed':
            raise HTTPException(404, 'Choose a failed job to retry.')
        source = DATA/job_id
        if not original['is_demo'] and not (source/'paper.pdf').is_file():
            raise HTTPException(409, 'The original PDF is unavailable.')
        if not original['is_demo']:
            settings = config()
            if not settings['api_configured']:
                raise HTTPException(400, settings['configuration_error'])
        if original.get('pending_recommendation'):
            job = dict(original, status='queued', stage='reading', progress=0, message='任务已创建')
            job.pop('error', None)
            return enqueue(job, source)
        job, folder = new_job(original['language'], original['duration'], original['is_demo'],
                              original['title'], style=original.get('style', 'editorial'),
                              level=original.get('level', 'introductory'),
                              condition=original.get('condition', 'C'), parent_id=job_id,
                              demo_topic=original.get('demo_topic', 'lora'),
                              supplement_count=original.get('supplement_count', 0))
        for name in ('from_recommendation', 'recommendation', 'recommended_pacing', 'analysis_warnings'):
            if name in original:
                job[name] = original[name]
        # Checkpoints from the first release use a different storyboard format.
        options = original.get('revision') or {}
        if (source/'storyboard-plan.json').is_file() and 'style' in original:
            job['revision'] = (options if options.get('stage') == 'production'
                               else {'stage': 'production', 'calibrate_duration': True})
        elif options:
            job['revision'] = options
        elif (source/'method.json').is_file() and original.get('stage') == 'storyboard':
            job['revision'] = {'stage': 'storyboard'}
        for name in ('paper.pdf', 'method.json', 'storyboard-plan.json', 'example.json',
                     'sources.json', 'evidence-excerpts.json', 'evidence-check.json'):
            if (source/name).is_file():
                shutil.copy2(source/name, folder/name)
        for path in source.glob('supplement-*.pdf'):
            shutil.copy2(path, folder/path.name)
        for name in ('speech-cache', 'assets'):
            if (source/name).is_dir():
                shutil.copytree(source/name, folder/name)
        return enqueue(job, folder)


@app.get('/api/jobs')
def list_jobs():
    with LOCK:
        jobs = sorted(JOBS.values(), key=lambda job: job['created_at'], reverse=True)[:20]
        return [public_job(job) for job in jobs]


@app.get('/api/jobs/{job_id}')
def get_job(job_id:str):
    with LOCK:
        if job_id not in JOBS:
            raise HTTPException(404,'未找到任务。')
        return public_job(JOBS[job_id])


def public_job(job):
    result = json.loads(json.dumps(job))
    if result.get('parent_id') not in JOBS:
        result.pop('parent_id', None)
    return result


@app.delete('/api/jobs/{job_id}', status_code=204, response_class=Response)
def delete_job(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
        if not JOB_ID.fullmatch(job_id) or job is None:
            raise HTTPException(404, 'Job not found.')
        if job['status'] not in ('complete', 'failed', 'ready'):
            raise HTTPException(409, 'Wait for the job to finish before deleting it.')

        folder = DATA/job_id
        pending = DATA/(DELETING_PREFIX + job_id)
        try:
            if folder.is_symlink() or pending.is_symlink():
                raise OSError('Unexpected task directory')
            if folder.exists():
                # Keep interrupted deletions out of the history loaded on startup.
                folder.rename(pending)
            if pending.exists():
                shutil.rmtree(pending)
        except OSError as exc:
            logging.warning('Could not delete job %s files (%s)', job_id, type(exc).__name__)
            raise HTTPException(500, 'Could not delete the job files. Try again.') from None
        del JOBS[job_id]


@app.api_route('/api/jobs/{job_id}/files/{filename}', methods=['GET','HEAD'])
def file_response(job_id:str,filename:str):
    types = {'video.mp4':'video/mp4','subtitles.srt':'application/x-subrip','storyboard.json':'application/json','project.zip':'application/zip', 'audio.zip':'application/zip', 'evaluation.json':'application/json', 'poster.png':'image/png'}
    with LOCK:
        job = JOBS.get(job_id)
        if job is None or filename not in types or job['status'] != 'complete':
            raise HTTPException(404,'文件尚未生成。')
        path = DATA/job_id/filename
        if not path.is_file():
            raise HTTPException(404,'文件不存在。')
        return FileResponse(path,media_type=types[filename],filename=filename,content_disposition_type='inline' if filename in ('video.mp4', 'poster.png') else 'attachment')


if (ROOT/'web/dist').exists():
    app.mount('/', StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
