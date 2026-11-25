import React, {useCallback, useId, useMemo, useState} from 'react';
import {Img, interpolate, staticFile, useVideoConfig} from 'remotion';
import './source-figure.css';
import {sourceFocusPlan} from './source-figure-motion.mjs';

function timedNotes(steps, duration) {
  const notes = steps.filter(({text, start}) => typeof text === 'string' && text.trim() &&
    Number.isFinite(start) && start >= 0 && start < duration)
    .map(({text, start}) => ({text: text.trim(), start}))
    .sort((first, second) => first.start - second.start);
  const distinct = [];
  for (const note of notes) {
    const previous = distinct.at(-1);
    if (previous?.start !== note.start && previous?.text !== note.text) distinct.push(note);
  }
  return distinct;
}

function sourceLabel(scene) {
  const source = typeof scene.figure_source === 'string' ? scene.figure_source.trim() : '';
  const match = /^(.+?)\s*·\s*p\.\s*(\d+)$/i.exec(source);
  if (!match) return source;

  const [, document, page] = match;
  const key = `${document.toLowerCase()}:${page}`;
  const evidence = Array.isArray(scene.evidence) ? scene.evidence : [];
  const references = evidence.map(item => {
    const name = (item?.document ?? 'PDF').toLowerCase();
    return `${name}:${item?.physical_page ?? item?.page}`;
  });
  if ([...new Set(references)].slice(0, 3).includes(key)) return '';
  if (references.length === 0 && document.toLowerCase() === 'paper' &&
      scene.source_pages?.some?.(sourcePage => String(sourcePage) === page)) return '';
  return source;
}

function sameDisplayText(first, second) {
  const normalize = text => (typeof text === 'string' ? text : '')
    .normalize('NFKC').toLowerCase().replace(/[\p{P}\p{Z}\p{S}]/gu, '');
  const label = normalize(first);
  const cue = normalize(second);
  return label.length > 0 && cue.length > 0 && (label === cue || cue.includes(label));
}

export function SourceFigure({scene, zh, frame, CaptionText, focus, paced}) {
  const {fps} = useVideoConfig();
  const maskId = useId().replaceAll(':', '');
  const [ratio, setRatio] = useState(null);
  const readImageSize = useCallback(image => {
    if (image.naturalWidth && image.naturalHeight) setRatio(image.naturalWidth / image.naturalHeight);
  }, []);
  const duration = scene.duration_frames;
  const split = scene.layout === 'split' || !scene.layout;
  const planned = timedNotes((scene.visual_beats ?? []).filter(beat => Number.isInteger(beat?.cue)).map(beat => ({
    text: beat.label,
    start: scene.cues?.[beat.cue]?.start_frame,
  })), duration);
  const bullets = split && Array.isArray(scene.bullets) ? scene.bullets : [];
  const bulletNotes = timedNotes(bullets.map((text, index) => ({
    text,
    start: scene.beats?.[index]?.start_frame ?? scene.cues?.[index]?.start_frame ??
      Math.round(duration * index / bullets.length),
  })), duration);
  const notes = planned.length ? planned : bulletNotes;
  const active = focus ? {start: focus.start_frame, text: focus.label} : notes.findLast(note => note.start <= frame);
  const source = sourceLabel(scene);
  const plannedFocus = useMemo(() => sourceFocusPlan({
    caption: scene.figure_caption,
    cues: scene.cues,
    beats: scene.beats,
    durationFrames: duration,
    zh,
  }), [scene, duration, zh]);
  const activePlan = plannedFocus.find(plan => plan.start <= frame && frame < plan.end);
  const focusRegions = activePlan?.regions ?? [];
  const cueProgress = activePlan ? interpolate(frame, [activePlan.start, activePlan.end], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  }) : 0;
  const spotlight = focusRegions.length ? Math.min(1, cueProgress * 7, (1 - cueProgress) * 7) : 0;
  const cueCaption = scene.cues?.find(cue => cue.start_frame <= frame && frame < cue.end_frame)?.text ?? '';
  const noteText = activePlan?.label ?? active?.text;
  const focusText = typeof noteText === 'string' && noteText.trim() &&
    !sameDisplayText(noteText, cueCaption) && !sameDisplayText(noteText, scene.title) ? noteText : '';
  const showNotes = paced || notes.length > 0 || plannedFocus.some(plan => plan.label);
  const noteStart = (activePlan?.label ? activePlan.start : active?.start) ?? 0;
  const enter = interpolate(frame - noteStart, [0, Math.max(1, Math.round(fps * .3))], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const scale = focusRegions.length || !activePlan ? 1 : 1 + .035 * Math.sin(Math.PI * cueProgress);
  const layout = split ? 'split' : scene.layout === 'detail' ? 'detail' : 'full';
  const chapters = [...new Set(plannedFocus.flatMap(plan => plan.label ? [plan.label] : []))];
  return (
    <div className={'pim-source-figure is-' + layout}>
      <figure className="pim-source-figure-plate">
        <div className="pim-source-figure-media" style={{
          width: ratio ? `min(100%, ${ratio * 525 + 16}px)` : undefined,
          transform: `scale(${scale})`,
        }}>
          <Img className="pim-source-figure-image" src={staticFile(scene.figure_file)} onImageFrame={readImageSize}
            alt={scene.figure_caption || (zh ? '论文原图' : 'Original paper figure')} />
          {focusRegions.length > 0 && <div className="pim-source-figure-panel-focus" style={{opacity: spotlight}} aria-hidden="true">
            <svg viewBox="0 0 1000 1000" preserveAspectRatio="none">
              <defs>
                <mask id={maskId}>
                  <rect width="1000" height="1000" fill="white" />
                  {focusRegions.map((region, index) => <rect key={region.key + index}
                    x={region.x * 1000} y={region.y * 1000}
                    width={region.width * 1000} height={region.height * 1000}
                    fill="black" />)}
                </mask>
              </defs>
              <rect width="1000" height="1000" className="pim-source-figure-dim" mask={`url(#${maskId})`} />
              {focusRegions.map((region, index) => <rect key={region.key + index}
                x={region.x * 1000 + 3} y={region.y * 1000 + 3}
                width={Math.max(0, region.width * 1000 - 6)}
                height={Math.max(0, region.height * 1000 - 6)}
                rx="14" className="pim-source-figure-highlight" />)}
            </svg>
          </div>}
        </div>
        {chapters.length > 1 && <div className="pim-source-figure-rail" aria-hidden="true">
          {chapters.map(chapter => {
            const viewed = plannedFocus.some(plan => plan.label === chapter && frame >= plan.end);
            return <span key={chapter}
              className={activePlan?.label === chapter ? 'is-current' : viewed ? 'is-viewed' : ''} />;
          })}
        </div>}
        {source && <figcaption className="pim-source-figure-credit">{source}</figcaption>}
      </figure>
      {showNotes && <aside className="pim-source-figure-note">
        {focusText && <div className="pim-source-figure-note-text" style={{
          opacity: .58 + .42 * enter,
          transform: `translateY(${(1 - enter) * 10}px)`,
        }}>
          <CaptionText caption={focusText} />
        </div>}
      </aside>}
    </div>
  );
}
