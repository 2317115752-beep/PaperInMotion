import React from 'react';
import {Img, interpolate, staticFile, useVideoConfig} from 'remotion';
import './source-figure.css';

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

export function SourceFigure({scene, zh, frame, CaptionText, focus, paced}) {
  const {fps} = useVideoConfig();
  const duration = scene.duration_frames ?? Infinity;
  const planned = timedNotes((scene.visual_beats ?? []).filter(beat => Number.isInteger(beat?.cue)).map(beat => ({
    text: beat.label,
    start: scene.cues?.[beat.cue]?.start_frame,
  })), duration);
  const notes = planned.length >= 2 ? planned : timedNotes((scene.beats ?? []).map(beat => ({
    text: beat?.label,
    start: beat?.start_frame,
  })), duration);
  const hasNotes = paced ? Boolean(focus) : notes.length >= 2;
  const active = paced ? focus && {start: focus.start_frame, text: focus.label}
    : hasNotes ? notes.findLast(note => note.start <= frame) : undefined;
  const aside = focus ? interpolate(frame - focus.first_frame, [0, Math.max(1, Math.round(fps * .52))], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }) : 0;
  const enter = active ? interpolate(frame - active.start, [0, Math.max(1, Math.round(fps * .3))], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }) : 0;
  const source = sourceLabel(scene);

  return (
    <div className="pim-source-figure" style={paced ? {gap: 48 * aside} : undefined}>
      <figure className="pim-source-figure-plate">
        <Img className="pim-source-figure-image" src={staticFile(scene.figure_file)}
          alt={scene.figure_caption || (zh ? '论文原图' : 'Original paper figure')} />
        {source && <figcaption className="pim-source-figure-credit">{source}</figcaption>}
      </figure>
      {hasNotes && <aside className="pim-source-figure-note" style={paced ? {
        flexBasis: 300 * aside,
        opacity: aside,
        overflow: 'hidden',
      } : undefined}>
        {active && <div className="pim-source-figure-note-text" style={{
          minWidth: paced ? 300 : undefined,
          opacity: .58 + .42 * enter,
          transform: `translateY(${(1 - enter) * 10}px)`,
        }}>
          <CaptionText caption={active.text} />
        </div>}
      </aside>}
    </div>
  );
}
