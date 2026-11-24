import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import {
  ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, ChevronDown, CircleAlert,
  CircleCheck, Clapperboard, Clock3, FileText, Film, Globe2, History, Layers3,
  LoaderCircle, Play, Plus, Settings2, Trash2, Upload, X,
} from 'lucide-react';
import { messages, readUiLanguage, translateBackendMessage, type Language, type Messages } from './i18n';

type Stage = 'reading' | 'understanding' | 'examples' | 'storyboard' | 'speech' | 'rendering' | 'complete';
type Status = 'queued' | 'running' | 'complete' | 'failed';
type Style = 'editorial' | 'midnight' | 'classroom';
type Level = 'introductory' | 'advanced';
type Topic = 'lora' | 'cliff';
type RevisionStage = 'understanding' | 'example' | 'storyboard' | 'production';
type Revision = { stage: RevisionStage; notes?: string; style?: Style; narrations?: Record<string, string> };
type UploadError = 'invalidPdf' | 'emptyPdf' | 'sizeError' | 'supplementCountError' | 'totalSizeError';

interface Evidence {
  id: string;
  document: string;
  physical_page: number;
  quote?: string;
  text?: string;
}

interface Config {
  model: string;
  tts_model: string;
  region: string;
  endpoint_mode: 'shared' | 'workspace';
  workspace_configured: boolean;
  api_configured: boolean;
  configuration_error?: string;
  max_upload_mb: number;
}

interface Scene {
  id: string | number;
  title: string;
  narration: string;
  visual_type: string;
  bullets: string[];
  source_pages: number[];
  formula?: unknown;
  evidence?: Evidence[];
  [key: string]: unknown;
}

interface Job {
  id: string;
  status: Status;
  stage: Stage;
  progress: number;
  message?: string;
  language: Language;
  duration: number;
  actual_duration?: number;
  title: string;
  error?: string;
  is_demo: boolean;
  demo_topic?: Topic;
  condition?: 'A' | 'B' | 'C';
  style?: Style;
  parent_id?: string;
  scenes: Scene[];
  files: {
    video?: string;
    subtitles?: string;
    project?: string;
    storyboard?: string;
    audio?: string;
    evaluation?: string;
    poster?: string;
  };
  warnings?: string[];
  model: string;
  created_at: string;
}

const stages = [
  ['reading', 'reading'],
  ['understanding', 'understanding'],
  ['examples', 'examples'],
  ['storyboard', 'storyboardStage'],
  ['speech', 'speech'],
  ['rendering', 'rendering'],
] as const;

const styles: Style[] = ['editorial', 'midnight', 'classroom'];
const levels: Level[] = ['introductory', 'advanced'];
const sourceFields = new Set(['id', 'title', 'narration', 'visual_type', 'bullets', 'source_pages', 'formula', 'evidence']);

function setLocalPreference(key: string, value?: string) {
  try {
    if (value === undefined) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // The studio still works when storage is disabled.
  }
}

function initialJobId() {
  try {
    const requested = new URLSearchParams(window.location.search).get('job');
    if (requested && /^[a-f0-9]{32}$/.test(requested)) return requested;
    const saved = localStorage.getItem('pim-last-job');
    return saved && /^[a-f0-9]{32}$/.test(saved) ? saved : null;
  } catch {
    return null;
  }
}

function forgetJob(id: string) {
  try {
    if (localStorage.getItem('pim-last-job') === id) setLocalPreference('pim-last-job');
  } catch {
    // The studio still works when storage is disabled.
  }
  const url = new URL(window.location.href);
  if (url.searchParams.get('job') === id) {
    url.searchParams.delete('job');
    window.history.replaceState(null, '', url);
  }
}

function activeJob(job: Job | null) {
  return job?.status === 'queued' || job?.status === 'running';
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '';
}

async function readResponse<T>(response: Response): Promise<T> {
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error('unreadable-response');
  }
  if (!response.ok) {
    const detail = body?.detail;
    const value = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map(item => item?.msg).filter(Boolean).join(' · ')
        : body?.error || body?.message;
    throw new Error(value || `HTTP ${response.status}`);
  }
  return body as T;
}

function ServiceMessage({ value, lang, fallback }: { value: string; lang: Language; fallback?: string }) {
  const t = messages[lang];
  if (value === 'unreadable-response') return <>{t.responseError}</>;
  const translated = translateBackendMessage(value, lang);
  const hasDetails = translated !== value && Boolean(value) && (!translated || /\b(?:HTTP|code=|request_id=)/i.test(value));
  return <>
    {translated || fallback || t.requestError}
    {hasDetails && <details className="service-details"><summary>{t.serverDetails}</summary><p lang={/[\u3400-\u9fff]/.test(value) ? "zh-CN" : "en"}>{value}</p></details>}
  </>;
}

function OptionGroup<T extends string | number>({ label, options, value, choose, disabled, className = '' }: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  choose: (value: T) => void;
  disabled: boolean;
  className?: string;
}) {
  return (
    <fieldset className={`control-group ${className}`} disabled={disabled}>
      <legend>{label}</legend>
      <div className="segments">
        {options.map(option => (
          <button
            key={option.value}
            type="button"
            aria-pressed={option.value === value}
            onClick={() => choose(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function Modal({ title, close, closeLabel, children, closeDisabled = false, initialFocus }: {
  title: string; close: () => void; closeLabel: string; children: ReactNode;
  closeDisabled?: boolean; initialFocus?: RefObject<HTMLButtonElement | null>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    initialFocus?.current?.focus();
    return () => element?.close();
  }, [initialFocus]);
  return (
    <dialog
      ref={dialog}
      className="modal"
      aria-labelledby="dialog-heading"
      onCancel={event => { event.preventDefault(); if (!closeDisabled) close(); }}
      onClick={event => { if (!closeDisabled && event.target === event.currentTarget) close(); }}
    >
      <div className="modal-body">
        <div className="modal-heading">
          <h2 id="dialog-heading">{title}</h2>
          <button className="icon-button" onClick={close} aria-label={closeLabel} autoFocus={!initialFocus} disabled={closeDisabled}><X size={20} /></button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

function EmptyPreview({ title, detail, icon }: { title: string; detail: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty-preview">
      <span className="preview-icon" aria-hidden="true">{icon || <Film size={30} strokeWidth={1.5} />}</span>
      <h3>{title}</h3>
      <div>{detail}</div>
    </div>
  );
}

function displayJobTitle(job: Job, t: Messages) {
  return job.is_demo ? (job.demo_topic === 'cliff' ? t.cliffDemo : t.loraDemo) : job.title || t.preparing;
}

function SceneCard({ scene, index, t }: { scene: Scene; index: number; t: Messages }) {
  const fields = Object.entries(scene).filter(([key, value]) =>
    !sourceFields.has(key) && value !== null && value !== undefined && value !== '' && !(Array.isArray(value) && !value.length));
  return (
    <details className="scene-card">
      <summary>
        <span className="scene-number">{String(index + 1).padStart(2, '0')}</span>
        <span className="scene-heading">
          <strong>{scene.title || `${t.scene} ${index + 1}`}</strong>
          <span>{t.visualTypes[scene.visual_type] || scene.visual_type}
            {' · '}
            {scene.source_pages?.length ? `${t.sourcePages} ${scene.source_pages.join(', ')}` : t.noPages}
          </span>
        </span>
        <ChevronDown size={16} />
      </summary>
      <div className="scene-detail">
        <p>{scene.narration}</p>
        {!!scene.bullets?.length && <ul>{scene.bullets.map((point, i) => <li key={i}>{point}</li>)}</ul>}
        {Boolean(scene.formula) && <div className="formula-box"><strong>{t.formulaLabel}</strong><pre>{String(scene.formula)}</pre></div>}
        {!!scene.evidence?.length && <details className="source-excerpts">
          <summary>{t.evidenceLabel}</summary>
          {scene.evidence.map((item, index) => (
            <blockquote key={item.id || index}>
              <cite>{item.document} · {t.physicalPage} {item.physical_page}</cite>
              <p>{item.quote || item.text}</p>
            </blockquote>
          ))}
        </details>}
        {!!fields.length && <details><summary>{t.sceneDetails}</summary>
          <dl>{fields.map(([key, value]) => <div key={key}>
            <dt>{t.fields[key] || key.replaceAll('_', ' ')}</dt>
            <dd><pre>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre></dd>
          </div>)}</dl>
        </details>}
      </div>
    </details>
  );
}

function JobSummary({ job, lang, pollError, openRevision, retryJob, retryError, busy }: {
  job: Job;
  lang: Language;
  pollError: boolean;
  openRevision: () => void;
  retryJob: () => void;
  retryError: string | null;
  busy: boolean;
}) {
  const t = messages[lang];
  const step = job.status === 'complete' || job.stage === 'complete'
    ? stages.length
    : Math.max(0, stages.findIndex(([id]) => id === job.stage));
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  const progressMessage = activeJob(job) && job.message
    ? translateBackendMessage(job.message, lang) || t.generationProgress
    : t.generationProgress;
  const links = [
    ['subtitles', t.subtitleFile, FileText],
    ['storyboard', t.storyboardFile, Layers3],
    ['project', t.projectFile, FileText],
    ['audio', t.audioFile, FileText],
    ['evaluation', t.evaluationFile, FileText],
  ] as const;
  return (
    <section className="panel job-panel">
      <div className="job-heading">
        <div>
          <p className="field-label">{t.currentJob}</p>
          <h2>{displayJobTitle(job, t)}</h2>
        </div>
        <span className={`status ${job.status}`}>{t[job.status]}</span>
      </div>
      <div className="job-meta">
        <span><Globe2 size={14} />{job.language === 'zh' ? t.chinese : t.english}</span>
        <span><Clock3 size={14} />{t.target} {job.duration} {t.seconds}</span>
        {typeof job.actual_duration === 'number' && <span>{t.actual} {job.actual_duration.toFixed(0)} {t.seconds}</span>}
      </div>
      <div className="progress-label"><span>{progressMessage}</span><strong>{progress}%</strong></div>
      <progress className={job.status === 'failed' ? 'failed' : ''} aria-label={t.generationProgress} value={progress} max={100} />
      <ol className="stage-grid">
        {stages.map(([id, label], index) => (
          <li key={id} className={index < step ? 'done' : index === step && activeJob(job) ? 'current' : ''} aria-current={index === step && activeJob(job) ? 'step' : undefined}>
            <span className="stage-dot" aria-hidden="true" />
            {job.is_demo && id === 'speech' ? t.noSpeech : t[label]}
          </li>
        ))}
      </ol>
      {pollError && <p className="notice" role="status">{t.progressLost}</p>}
      {job.is_demo && <p className="job-note">{t.demoNote}</p>}
      {job.parent_id && <a className="source-job" href={`/?job=${encodeURIComponent(job.parent_id)}`}>{t.revisionOf} {job.parent_id.slice(0, 8)}</a>}
      {job.warnings?.map((warning, index) => (
        <div className="warning-row" key={index}><CircleAlert size={15} /><div><ServiceMessage value={warning} lang={lang} /></div></div>
      ))}
      {job.status === 'complete' && <div className="export-list">
        {links.map(([key, label, Icon]) => job.files[key] && (
          <a key={key} href={job.files[key]} download><Icon size={15} />{label}<ArrowDownToLine size={14} /></a>
        ))}
      </div>}
      {job.status === 'complete' && !job.is_demo && (
        <button className="secondary-button revise-button" onClick={openRevision} disabled={busy}>
          <Settings2 size={15} />{t.revise}
        </button>
      )}
      {job.status === 'failed' && (
        <button className="secondary-button revise-button" onClick={retryJob} disabled={busy}>
          {t.retryJob}
        </button>
      )}
      {retryError !== null && <div className="notice error" role="alert"><ServiceMessage value={retryError} lang={lang} /></div>}
    </section>
  );
}

function RevisionForm({ job, t, submitRevision, submitting }: {
  job: Job; t: Messages; submitRevision: (revision: Revision) => void; submitting: boolean;
}) {
  const [stage, setStage] = useState<RevisionStage>('storyboard');
  const [style, setStyle] = useState<Style>(job.style || 'editorial');
  const [notes, setNotes] = useState('');
  const [sceneIndex, setSceneIndex] = useState('');
  const [narration, setNarration] = useState('');
  const [error, setError] = useState<'feedbackRequired' | 'narrationRequired' | null>(null);
  const stageOptions: { value: RevisionStage; label: string }[] = [
    { value: 'understanding', label: t.reviseUnderstanding },
    ...(job.condition === 'A' || job.condition === 'B' ? [] : [{ value: 'example' as const, label: t.reviseExample }]),
    { value: 'storyboard', label: t.reviseStoryboard },
    { value: 'production', label: t.reviseProduction },
  ];
  return (
    <form className="revision-form" onSubmit={event => {
      event.preventDefault();
      if (stage === 'production') {
        if (sceneIndex && !narration.trim()) return setError('narrationRequired');
        const changed = sceneIndex && narration.trim() !== job.scenes[Number(sceneIndex) - 1].narration.trim();
        submitRevision({ stage, style, narrations: changed ? { [sceneIndex]: narration.trim() } : {} });
      } else {
        if (!notes.trim()) return setError('feedbackRequired');
        submitRevision({ stage, notes: notes.trim() });
      }
    }}>
      <label>{t.revisionStage}
        <select value={stage} disabled={submitting} onChange={event => {
          setStage(event.target.value as RevisionStage);
          setError(null);
        }}>
          {stageOptions.map(option => <option value={option.value} key={option.value}>{option.label}</option>)}
        </select>
      </label>
      {stage === 'production' ? <>
        <p>{t.reviseProductionHint}</p>
        <OptionGroup label={t.style} options={styles.map(value => ({ value, label: t[value] }))}
          value={style} choose={setStyle} disabled={submitting} />
        <label>{t.sceneToEdit}
          <select value={sceneIndex} disabled={submitting} onChange={event => {
            const next = event.target.value;
            setSceneIndex(next);
            setNarration(next ? job.scenes[Number(next)-1].narration : '');
            setError(null);
          }}>
            <option value="">{t.noNarrationEdit}</option>
            {job.scenes.map((scene, i) => <option key={scene.id || i} value={i+1}>{i+1}. {scene.title}</option>)}
          </select>
        </label>
        {sceneIndex && <label>{t.revisedNarration}
          <textarea maxLength={2200} rows={5} disabled={submitting} value={narration}
            onChange={event => { setNarration(event.target.value); setError(null); }} />
        </label>}
      </> : <label>{t.revisionNotes}
        <textarea maxLength={2000} rows={5} disabled={submitting} value={notes} placeholder={t.revisionNotesHint}
          onChange={event => { setNotes(event.target.value); setError(null); }} />
      </label>}
      {error && <p className="notice error" role="alert">{t[error]}</p>}
      <button className="primary-button" disabled={submitting} type="submit">
        {submitting && <LoaderCircle className="spin" size={16} />}{submitting ? t.submitting : t.submitRevision}
      </button>
    </form>
  );
}

export default function App() {
  const [lang, setLang] = useState<Language>(readUiLanguage);
  const t = messages[lang];
  const [language, setLanguage] = useState<Language>('en');
  const [duration, setDuration] = useState(120);
  const [style, setStyle] = useState<Style>('editorial');
  const [level, setLevel] = useState<Level>('introductory');
  const [file, setFile] = useState<File | null>(null);
  const [supplements, setSupplements] = useState<File[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [configError, setConfigError] = useState(false);
  const [configLoading, setConfigLoading] = useState(true);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<UploadError | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [pollError, setPollError] = useState(false);
  const [lastJobError, setLastJobError] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [tab, setTab] = useState<'preview' | 'storyboard'>('preview');
  const [modal, setModal] = useState<'settings' | 'guide' | 'history' | 'revision' | null>(null);
  const [revisionError, setRevisionError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [history, setHistory] = useState<Job[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [deleteCandidate, setDeleteCandidate] = useState<Job | null>(null);
  const [deletingJob, setDeletingJob] = useState(false);
  const [deleteError, setDeleteError] = useState<'deleteJobError' | 'deleteJobActive' | null>(null);
  const [mediaError, setMediaError] = useState(false);
  const deletedJobIds = useRef(new Set<string>());
  const cancelDeleteButton = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const supplementInput = useRef<HTMLInputElement>(null);
  const jobId = job?.id;
  const jobRunning = activeJob(job);
  const busy = submitting || jobRunning;
  const videoUrl = job?.status === 'complete' ? job.files.video : undefined;
  const maxUpload = config?.max_upload_mb || 25;

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.title = `Paper in Motion · ${t.workspace}`;
    setLocalPreference('pim-ui-language', lang);
  }, [lang, t.workspace]);

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    setConfigError(false);
    try {
      setConfig(await readResponse<Config>(await fetch('/api/config')));
    } catch {
      setConfigError(true);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => { void loadConfig(); }, [loadConfig]);

  useEffect(() => {
    const id = initialJobId();
    if (!id) return;
    const controller = new AbortController();
    fetch(`/api/jobs/${id}`, { signal: controller.signal })
      .then(async response => {
        if (controller.signal.aborted || deletedJobIds.current.has(id)) return;
        if (response.status === 404) {
          forgetJob(id);
          return;
        }
        const result = await readResponse<Job>(response);
        if (!controller.signal.aborted && !deletedJobIds.current.has(id)) setJob(current => current ?? result);
      })
      .catch(() => { if (!controller.signal.aborted && !deletedJobIds.current.has(id)) setLastJobError(true); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (jobId) setLocalPreference('pim-last-job', jobId);
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !jobRunning) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await readResponse<Job>(await fetch(`/api/jobs/${encodeURIComponent(jobId!)}`, { signal: controller.signal }));
        if (controller.signal.aborted || deletedJobIds.current.has(result.id)) return;
        if (result.parent_id && deletedJobIds.current.has(result.parent_id)) delete result.parent_id;
        setJob(result);
        setPollError(false);
        if (activeJob(result)) timer = setTimeout(poll, 1500);
      } catch {
        if (controller.signal.aborted) return;
        setPollError(true);
        timer = setTimeout(poll, 4000);
      }
    }
    timer = setTimeout(poll, 500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [jobId, jobRunning]);

  useEffect(() => { setMediaError(false); }, [videoUrl]);

  const loadHistory = useCallback(async (signal: AbortSignal) => {
    setHistory(null);
    setHistoryError(false);
    try {
      const jobs = await readResponse<Job[]>(await fetch('/api/jobs', { signal }));
      if (!signal.aborted) setHistory(jobs);
    } catch {
      if (!signal.aborted) setHistoryError(true);
    }
  }, []);

  useEffect(() => {
    if (modal !== 'history') return;
    const controller = new AbortController();
    void loadHistory(controller.signal);
    return () => controller.abort();
  }, [modal, loadHistory, historyVersion]);

  function validateFile(candidate: File): UploadError | null {
    if (!candidate.name.toLowerCase().endsWith('.pdf')) return 'invalidPdf';
    if (!candidate.size) return 'emptyPdf';
    if (candidate.size > maxUpload * 1024 * 1024) return 'sizeError';
    return null;
  }

  function validateTotal(primary: File | null, extras: File[]): UploadError | null {
    const total = extras.reduce((bytes, item) => bytes + item.size, primary?.size || 0);
    return total > 50 * 1024 * 1024 ? 'totalSizeError' : null;
  }

  function selectSupplements(chosen: File[]) {
    if (!chosen.length || busy) return;
    setRequestError(null);
    const next = [...supplements, ...chosen];
    const error = next.length > 3 ? 'supplementCountError'
      : chosen.map(validateFile).find(Boolean) || validateTotal(file, next);
    setUploadError(error);
    if (!error) setSupplements(next);
  }

  function selectFile(candidate?: File) {
    if (!candidate || busy) return;
    setRequestError(null);
    const error = validateFile(candidate) || validateTotal(candidate, supplements);
    setUploadError(error);
    if (!error) setFile(candidate);
  }

  function showJob(next: Job) {
    setJob(next);
    setTab('preview');
    setPollError(false);
    setLastJobError(false);
    setRetryError(null);
    window.history.replaceState(null, '', window.location.pathname);
  }

  async function deleteHistoryJob() {
    if (!deleteCandidate || deletingJob) return;
    const id = deleteCandidate.id;
    setDeletingJob(true);
    setDeleteError(null);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (response.status === 409) {
        setDeleteError('deleteJobActive');
        return;
      }
      if (response.status !== 204 && response.status !== 404) throw new Error('job-delete-failed');
      deletedJobIds.current.add(id);
      forgetJob(id);
      setJob(current => {
        if (current?.id === id) return null;
        if (current?.parent_id === id) return { ...current, parent_id: undefined };
        return current;
      });
      if (jobId === id) {
        setTab('preview');
        setPollError(false);
        setLastJobError(false);
        setRetryError(null);
      }
      setHistory(current => current?.filter(item => item.id !== id) ?? null);
      setHistoryVersion(version => version + 1);
      setDeleteCandidate(null);
    } catch {
      setDeleteError('deleteJobError');
    } finally {
      setDeletingJob(false);
    }
  }

  async function submit(demo?: Topic) {
    if (busy || (!demo && (!file || uploadError || !config?.api_configured))) return;
    setSubmitting(true);
    setRequestError(null);
    try {
      if (demo) {
        const query = new URLSearchParams({ language, style, topic: demo });
        showJob(await readResponse<Job>(await fetch(`/api/demo?${query}`, { method: 'POST' })));
      } else {
        const data = new FormData();
        data.set('file', file!);
        data.set('language', language);
        data.set('duration', String(duration));
        data.set('style', style);
        data.set('level', level);
        supplements.forEach(item => data.append('supplements', item));
        showJob(await readResponse<Job>(await fetch('/api/jobs', { method: 'POST', body: data })));
      }
    } catch (error) {
      setRequestError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitRevision(revision: Revision) {
    if (busy || !jobId) return;
    setSubmitting(true);
    setRevisionError(null);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/revise`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(revision),
      });
      showJob(await readResponse<Job>(response));
      setModal(null);
    } catch (error) {
      setRevisionError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function retryJob() {
    if (busy || job?.status !== 'failed') return;
    setSubmitting(true);
    setRetryError(null);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(job.id)}/retry`, { method: 'POST' });
      showJob(await readResponse<Job>(response));
    } catch (error) {
      setRetryError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    if (busy) return;
    setLocalPreference('pim-last-job');
    window.history.replaceState(null, '', window.location.pathname);
    setJob(null);
    setFile(null);
    setSupplements([]);
    setTab('preview');
    setUploadError(null);
    setRequestError(null);
    setPollError(false);
    setLastJobError(false);
    setRetryError(null);
  }

  function closeModal() { setModal(null); }

  const locale = lang === 'zh' ? 'zh-CN' : 'en';
  const dateDisplay = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-content">
          <a href="/" className="brand" aria-label={`Paper in Motion · ${t.workspace}`}>
            <span className="brand-mark"><Clapperboard size={23} strokeWidth={1.8} /></span>
            <strong>Paper in Motion</strong>
          </a>
          <nav className="topbar-actions" aria-label={t.workspace}>
            <button className="topbar-button" onClick={() => setModal('history')} aria-label={t.history}><History size={17} /><span>{t.history}</span></button>
            <button className="topbar-button" onClick={() => setModal('settings')} aria-label={t.settings}><Settings2 size={17} /><span>{t.settings}</span></button>
            <label className="language-picker">
              <Globe2 size={16} aria-hidden="true" />
              <span className="sr-only">{t.interfaceLanguage}</span>
              <select value={lang} onChange={event => setLang(event.target.value as Language)}>
                <option value="en" lang="en">English</option>
                <option value="zh" lang="zh-CN">中文</option>
              </select>
            </label>
          </nav>
        </div>
      </header>
      <main className="workspace">
        <div className="page-heading">
          <div><h1>{t.headline}</h1><p>{t.intro}</p></div>
          <button className="secondary-button" onClick={reset} disabled={busy}><Plus size={17} />{t.newVideo}</button>
        </div>
        <div className="workspace-grid">
          <section className="panel creation-panel" aria-labelledby="create-title">
            <div className="panel-heading"><h2 id="create-title">{t.create}</h2><FileText size={19} /></div>
            <form onSubmit={event => { event.preventDefault(); void submit(); }}>
              <div className="creation-content">
                <div className="field-label" id="paper-label">{t.paper}</div>
                <input
                  ref={input}
                  id="paper-upload"
                  className="sr-only"
                  type="file"
                  accept=".pdf,application/pdf"
                  tabIndex={-1}
                  aria-labelledby="paper-label"
                  disabled={busy}
                  onChange={event => { selectFile(event.target.files?.[0]); event.target.value = ''; }}
                />
                <button
                  type="button"
                  className={`upload-zone ${dragging ? 'dragging' : ''}`}
                  onClick={() => input.current?.click()}
                  onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={event => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0]); }}
                  disabled={busy}
                >
                  <span className="upload-icon">{file ? <CircleCheck size={23} /> : <Upload size={23} />}</span>
                  <strong>{file?.name || t.drop}</strong>
                  <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · ${t.replace}` : t.browse}</span>
                  {!file && <small>{t.uploadLimit} {maxUpload} MB</small>}
                </button>
                <details className="supplement-control">
                  <summary>{t.supplements}{supplements.length > 0 && ` (${supplements.length})`}</summary>
                  <p>{t.supplementLimit}</p>
                  <ul>{supplements.map((item, index) => (
                    <li key={`${item.name}-${index}`}>{item.name}
                      <button type="button" className="icon-button" disabled={busy} aria-label={`${t.remove} ${item.name}`}
                        onClick={() => { setSupplements(items => items.filter((_, i) => i !== index)); setUploadError(null); }}>
                        <X size={15} />
                      </button>
                    </li>
                  ))}</ul>
                  <input ref={supplementInput} className="sr-only" tabIndex={-1} type="file" multiple
                    aria-label={t.supplements} accept=".pdf,application/pdf" disabled={busy}
                    onChange={event => { selectSupplements(Array.from(event.target.files || [])); event.target.value = ''; }} />
                  <button type="button" className="text-button" disabled={busy || supplements.length >= 3} onClick={() => supplementInput.current?.click()}>
                    <Plus size={15} />{t.addSupplement}
                  </button>
                </details>
                <OptionGroup label={t.videoLanguage} options={[
                  { value: 'en', label: t.english }, { value: 'zh', label: t.chinese },
                ]} value={language} choose={setLanguage} disabled={busy} />
                <OptionGroup label={t.duration} options={[1, 2, 3, 5].map(minutes => ({
                  value: minutes * 60, label: `${minutes} ${t.minute}`,
                }))} value={duration} choose={setDuration} disabled={busy} />
                <OptionGroup className="style-group" label={t.style} options={styles.map(value => ({
                  value, label: t[value],
                }))} value={style} choose={setStyle} disabled={busy} />
                <OptionGroup label={t.level} options={levels.map(value => ({
                  value, label: t[value],
                }))} value={level} choose={setLevel} disabled={busy} />
                {configError && <div className="notice"><CircleAlert size={16} /><div>{t.apiUnavailable} <button type="button" onClick={() => void loadConfig()}>{t.retry}</button></div></div>}
                {!configLoading && !configError && !config?.api_configured && (
                  <div className="notice"><CircleAlert size={16} /><div><ServiceMessage value={config?.configuration_error || ''} lang={lang} fallback={t.apiMissing} /></div></div>
                )}
                {uploadError && <div className="notice error" role="alert">
                  <CircleAlert size={16} />{t[uploadError]}{uploadError === 'sizeError' && ` ${maxUpload} MB.`}
                </div>}
                {requestError !== null && <div className="notice error" role="alert"><CircleAlert size={16} /><div><ServiceMessage value={requestError} lang={lang} /></div></div>}
                <button className="primary-button" type="submit" disabled={busy || !file || !!uploadError || !config?.api_configured || configError || configLoading}>
                  {busy ? <LoaderCircle size={18} className="spin" /> : <Film size={18} />}
                  {submitting ? t.submitting : jobRunning ? t.generating : t.generate}
                  {!busy && <ArrowRight size={17} />}
                </button>
              </div>
            </form>
            <div className="demo-section">
              <span className="field-label">{t.demo}</span>
              <div>{(['lora', 'cliff'] as const).map(topic => (
                <button key={topic} className="demo-button" onClick={() => void submit(topic)} disabled={busy || configError || configLoading}>
                  <Play size={13} fill="currentColor" />
                  {topic === 'lora' ? t.loraDemo : t.cliffDemo}
                  <ArrowUpRight size={14} />
                </button>
              ))}</div>
            </div>
          </section>
          <div className="results">
            <section className="panel preview-panel">
              <div className="preview-heading">
                <div className="preview-tabs" aria-label={t.preview}>
                  <button aria-pressed={tab === 'preview'} onClick={() => setTab('preview')}><Film size={17} />{t.preview}</button>
                  <button aria-pressed={tab === 'storyboard'} onClick={() => setTab('storyboard')}><Layers3 size={17} />{t.storyboard}{!!job?.scenes?.length && <span>{job.scenes.length}</span>}</button>
                </div>
                {videoUrl && !mediaError && <a className="download-link" href={videoUrl} download><ArrowDownToLine size={16} />{t.download}</a>}
              </div>
              {tab === 'preview'
                ? <div className="preview-surface" aria-live="polite">
                    {videoUrl && !mediaError
                      ? <video key={videoUrl} src={videoUrl} poster={job?.files.poster} controls playsInline preload="metadata"
                          aria-label={t.videoLabel} onError={() => setMediaError(true)} />
                      : job?.status === 'failed'
                        ? <EmptyPreview title={t.jobFailed} detail={<ServiceMessage value={job.error || job.message || ''} lang={lang} />} icon={<CircleAlert size={30} />} />
                        : mediaError
                          ? <EmptyPreview title={t.mediaError} detail={t.mediaErrorText} icon={<CircleAlert size={30} />} />
                          : job?.status === 'complete'
                            ? <EmptyPreview title={t.jobNoVideo} detail={<button className="text-button" onClick={() => setTab('storyboard')}>{t.openStoryboard}</button>} />
                            : busy
                              ? <EmptyPreview title={t.generating} detail={job ? `${job.progress}%` : t.submitting} icon={<LoaderCircle size={30} className="spin" />} />
                              : <EmptyPreview title={t.emptyTitle} detail={t.emptyText} />}
                  </div>
                : <div className="storyboard-panel">
                    {job?.scenes?.length ? <>
                      <p>{t.scenesText}</p>
                      <div className="scene-list">{job.scenes.map((scene, index) => <SceneCard key={scene.id || index} scene={scene} index={index} t={t} />)}</div>
                    </> : <EmptyPreview title={t.emptyScenes} detail={t.emptyScenesText} icon={<Layers3 size={30} />} />}
                  </div>}
            </section>
            {lastJobError && <p role="alert" className="notice">{t.lastJobLost}</p>}
            {job && <JobSummary key={job.id} job={job} lang={lang} pollError={pollError} busy={busy}
              retryJob={() => void retryJob()} retryError={retryError}
              openRevision={() => { setRevisionError(null); setModal('revision'); }} />}
          </div>
        </div>
        <footer className="workspace-footer">
          <span>{t.local}</span>
          <button className="text-button" onClick={() => setModal('guide')}><BookOpen size={16} />{t.guide}</button>
        </footer>
      </main>
      {modal === 'settings' && <Modal title={t.settings} close={closeModal} closeLabel={t.close}>
        <dl className="settings-list">
          <div><dt>{t.paperModel}</dt><dd>{config?.model || t.notConnected}</dd></div>
          <div><dt>{t.speechModel}</dt><dd>{config?.tts_model || t.notConnected}</dd></div>
          <div><dt>{t.apiRegion}</dt><dd>{t.provider} · {config?.region || 'cn-beijing'}</dd></div>
          <div><dt>{t.endpoint}</dt><dd>{config?.endpoint_mode === 'workspace' ? t.dedicated : t.shared}</dd></div>
          <div><dt>{t.businessSpace}</dt><dd>{config?.endpoint_mode === 'workspace'
            ? (config.workspace_configured ? t.spaceSet : t.spaceMissing) : t.spaceKey}</dd></div>
          <div><dt>{t.status}</dt><dd>{configLoading ? t.checking : configError ? t.apiUnavailable
            : config?.api_configured ? t.apiReady : t.apiMissing}</dd></div>
        </dl>
        <p>{t.settingsIntro}</p>
        {config?.endpoint_mode === 'workspace' && <p>{t.dedicatedHelp}</p>}
        <button className="secondary-button" onClick={() => void loadConfig()} disabled={configLoading} aria-live="polite">{configLoading ? t.loading : t.refresh}</button>
      </Modal>}
      {modal === 'guide' && <Modal title={t.guide} close={closeModal} closeLabel={t.close}>
        <p>{t.guideIntro}</p>
        <ul className="guide-list">
          <li><strong>{t.guideUpload}</strong><p>{t.guideUploadText}</p></li>
          <li><strong>{t.guideReview}</strong><p>{t.guideReviewText}</p></li>
          <li><strong>{t.guideExport}</strong><p>{t.guideExportText}</p></li>
        </ul>
        <p className="job-note">{t.guidePrivacy}</p>
      </Modal>}
      {modal === 'revision' && job && <Modal title={t.revise} close={closeModal} closeLabel={t.close}>
        <RevisionForm job={job} t={t} submitting={submitting} submitRevision={revision => void submitRevision(revision)} />
        {revisionError !== null && <div className="notice error" role="alert"><ServiceMessage value={revisionError} lang={lang} /></div>}
      </Modal>}
      {modal === 'history' && !deleteCandidate && <Modal title={t.history} close={closeModal} closeLabel={t.close}>
        {historyError ? <p role="alert">{t.historyError}</p>
          : !history ? <p role="status">{t.loading}</p>
          : history.length === 0 ? <p>{t.noHistory}</p>
          : <ul className="history-list">
              {history.map(previous => {
                const date = new Date(previous.created_at);
                const title = displayJobTitle(previous, t);
                return (
                  <li key={previous.id}>
                    <button
                      className="history-open-job"
                      disabled={busy && jobId !== previous.id}
                      onClick={() => { showJob(previous); closeModal(); }}
                    >
                      <span>
                        <strong>{title}</strong>
                        <small>{Number.isFinite(date.getTime()) ? dateDisplay.format(date) : ''}</small>
                      </span>
                      <span className={`status ${previous.status}`}>{t[previous.status]}</span>
                    </button>
                    {!activeJob(previous) && <button
                      className="history-delete-job"
                      aria-label={`${t.deleteJob} · ${title}`}
                      title={t.deleteJob}
                      onClick={() => { setDeleteError(null); setDeleteCandidate(previous); }}
                    >
                      <Trash2 size={17} aria-hidden="true" />
                    </button>}
                  </li>
                );
              })}
            </ul>}
      </Modal>}
      {modal === 'history' && deleteCandidate && <Modal
        title={t.deleteJobTitle}
        close={() => setDeleteCandidate(null)}
        closeLabel={t.close}
        closeDisabled={deletingJob}
        initialFocus={cancelDeleteButton}
      >
        <p><strong>{displayJobTitle(deleteCandidate, t)}</strong></p>
        <p>{t.deleteJobWarning}</p>
        {deleteError && <div className="notice error" role="alert">{t[deleteError]}</div>}
        <div className="history-delete-actions">
          <button ref={cancelDeleteButton} className="secondary-button" onClick={() => setDeleteCandidate(null)} disabled={deletingJob}>{t.cancelDeleteJob}</button>
          <button className="primary-button delete-job-confirm" onClick={() => void deleteHistoryJob()} disabled={deletingJob}>
            {deletingJob && <LoaderCircle className="spin" size={16} aria-hidden="true" />}
            <span aria-live="polite">{deletingJob ? t.deletingJob : t.confirmDeleteJob}</span>
          </button>
        </div>
      </Modal>}
    </div>
  );
}
