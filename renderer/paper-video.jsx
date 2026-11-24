import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Freeze, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {formatMath, LOWER_SCRIPTS, UPPER_SCRIPTS} from './math-format.mjs';
import 'katex/dist/katex.min.css';
import './video.css';

const WIDTH = 1920;
const HEIGHT = 1080;
const EASE = value => 1 - (1 - value) ** 3;

const label = (zh, chinese, english) => zh ? chinese : english;
const list = value => Array.isArray(value) ? value : value ? [value] : [];
const limit = (value, max) => typeof value === 'string' ? value.length > max ? value.slice(0, max - 1) + '…' : value : '';
const number = value => Number.isFinite(value) ? Number(value.toPrecision(5)).toString() : '—';

function MathExpression({text}) {
  const source = typeof text === 'string' ? text : '';
  const html = useMemo(() => formatMath(source), [source]);
  if (html) return <span className="pim-math" dangerouslySetInnerHTML={{__html: html}} />;

  const chars = Array.from(source);
  const tokens = [];
  for (const character of chars) {
    const lower = LOWER_SCRIPTS[character];
    const upper = UPPER_SCRIPTS[character];
    const type = lower ? 'sub' : upper ? 'sup' : 'normal';
    const glyph = lower || upper || character;
    const previous = tokens.at(-1);
    if (previous?.type === type) previous.text += glyph;
    else tokens.push({type, text: glyph});
  }
  return tokens.map((token, index) => {
    if (token.type === 'sub') return <sub key={index}>{token.text}</sub>;
    if (token.type === 'sup') return <sup key={index}>{token.text}</sup>;
    return <React.Fragment key={index}>{token.text}</React.Fragment>;
  });
}

function entrance(frame, delay, frames = 18) {
  return interpolate(frame, [delay, delay + frames], [0, 1], {
    easing: EASE,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
}

function Reveal({children, delay = 0, className = '', style}) {
  const frame = useCurrentFrame();
  const progress = entrance(frame, delay);
  return (
    <div
      className={className}
      style={{opacity: progress, transform: 'translateY(' + (1 - progress) * 21 + 'px)', ...style}}
    >
      {children}
    </div>
  );
}

function stepTimes(scene, count) {
  const beats = list(scene.beats).filter(beat => Number.isFinite(beat?.start_frame));
  if (beats.length === count) return beats.map(beat => beat.start_frame);
  const cues = list(scene.cues);
  return Array.from({length: count}, (_, index) => {
    if (!cues.length) return scene.duration_frames * index / count;
    const position = index * cues.length / count;
    const cue = cues[Math.floor(position)];
    return cue.start_frame + (cue.end_frame - cue.start_frame) * (position % 1);
  });
}

function activeStep(scene, frame, count) {
  const latest = stepTimes(scene, count).findLastIndex(start => start <= frame);
  return Math.max(0, latest);
}

function focusProgress(scene, frame, fps) {
  if (!['title', 'figure', 'matrix', 'equation'].includes(scene.visual_type)) return 0;
  const cues = list(scene.cues);
  const cue = Number.isInteger(scene.focus_cue) ? cues[scene.focus_cue] : undefined;
  const fallback = scene.visual_type === 'title' ? cues[0] : cues[1];
  const start = (cue ?? fallback)?.start_frame;
  if (!Number.isFinite(start)) return 0;
  const remaining = scene.duration_frames - start;
  if (remaining < fps) return 0;
  const push = Math.min(remaining * .35, fps * .85);
  const settle = Math.min(remaining * .25, fps * .65);
  return entrance(frame, start, push) * (1 - entrance(frame, start + push, settle));
}

function Arrow({active = false, pulseStart}) {
  const frame = useCurrentFrame();
  const animated = active && Number.isFinite(pulseStart) && frame >= pulseStart && frame < pulseStart + 15;
  const progress = animated ? entrance(frame, pulseStart, 14) : 0;
  return (
    <svg className={'pim-arrow' + (active ? ' is-active' : '')} viewBox="0 0 72 32" aria-hidden="true">
      <path d="M2 16h62M54 5l12 11-12 11" fill="none" stroke="currentColor" strokeWidth="2.5" />
      {animated && <circle cx={3 + progress * 57} cy="16" r="4.5" fill="currentColor" />}
    </svg>
  );
}

function TitleArtwork() {
  const frame = useCurrentFrame();
  const p = entrance(frame, 6, 38);
  return (
    <svg className="pim-title-art" viewBox="0 0 630 640" aria-hidden="true">
      <defs>
        <pattern id="pim-grid" width="30" height="30" patternUnits="userSpaceOnUse">
          <path d="M30 0H0V30" fill="none" stroke="var(--grid)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect x="0" y="0" width="630" height="640" rx="12" fill="url(#pim-grid)" />
      <circle cx="315" cy="320" r="228" fill="none" stroke="var(--line)" strokeWidth="1" />
      <circle cx="315" cy="320" r="173" fill="none" stroke="var(--line)" strokeWidth="1" strokeDasharray="4 8" />
      <path d="M88 320h454M315 92v456" stroke="var(--line)" strokeWidth="1" />
      <g transform={'translate(0 ' + (1 - p) * 52 + ')'} opacity={p}>
        <path d="M146 274l182-104 152 88-183 104z" fill="var(--accent)" fillOpacity=".16" stroke="var(--accent)" strokeWidth="2" />
        <path d="M146 318l182-104 152 88-183 104z" fill="var(--accent)" fillOpacity=".4" stroke="var(--accent)" strokeWidth="2" />
        <path d="M146 364l182-104 152 88-183 104z" fill="var(--accent)" stroke="var(--accent)" strokeWidth="2" />
        <path d="M146 364v35l151 87 183-104v-34l-183 104z" fill="var(--accentDeep)" opacity=".88" />
        <path d="M185 342l150 87m-108-111 149 87m-105-111 149 87m-108-110 150 87M185 385l182-104m-145 126 182-104m-144 125 182-104" stroke="var(--onAccent)" strokeOpacity=".4" strokeWidth="1.5" />
        <circle cx="297" cy="452" r="7" fill="var(--warm)" />
        <circle cx="328" cy="170" r="7" fill="var(--accent)" />
      </g>
      <circle cx={315 + 228 * Math.cos(frame / 90)} cy={320 + 228 * Math.sin(frame / 90)} r="5" fill="var(--warm)" />
    </svg>
  );
}

function Title({scene, zh}) {
  return (
    <div className="pim-title-grid">
      <div>
        <Reveal className="pim-kicker">{label(zh, '论文导读', 'RESEARCH EXPLAINER')}</Reveal>
        <Reveal delay={5} className={'pim-title ' + (scene.title?.length > (zh ? 23 : 58) ? 'is-long' : '')}>
          {limit(scene.title, zh ? 64 : 130)}
        </Reveal>
        {scene.bullets?.[0] && <Reveal delay={13} className="pim-lead">{limit(scene.bullets[0], 145)}</Reveal>}
      </div>
      <TitleArtwork />
    </div>
  );
}

function TalkingPoint({items, scene, frame}) {
  const points = list(items).filter(item => typeof item === 'string' && item.trim()).slice(0, 4);
  if (!points.length) return null;
  const step = activeStep(scene, frame, points.length);
  const progress = entrance(frame, stepTimes(scene, points.length)[step] || 0, 13);
  return (
    <div className="pim-talking-point" style={{opacity: .35 + .65 * progress, transform: `translateY(${14 * (1 - progress)}px)`}}>
      {limit(points[step], 145)}
    </div>
  );
}

function Flow({scene, zh, frame}) {
  const nodes = list(scene.nodes).length ? scene.nodes : list(scene.bullets);
  if (nodes.length < 2) return <Takeaways scene={scene} zh={zh} frame={frame} />;
  const labels = nodes.slice(0, 5);
  const starts = stepTimes(scene, labels.length);
  const active = Math.max(0, starts.findLastIndex(start => start <= frame));
  const nextGap = (starts[active + 1] ?? scene.duration_frames) - starts[active];
  const travel = entrance(frame, starts[active], Math.max(1, Math.min(15, nextGap)));
  const progress = active ? (active - 1 + travel) / (labels.length - 1) : 0;
  return (
    <div className="pim-flow-layout">
      <div className="pim-flow" style={{'--flow-nodes': labels.length}}>
        <div className="pim-flow-track" aria-hidden="true">
          <div className="pim-flow-trace" style={{width: progress * 100 + '%'}} />
        </div>
        {labels.map((node, index) => (
          <div key={index} className={'pim-flow-card' + (index === active ? ' is-active' : index < active ? ' is-visited' : '')}>
            <span className="pim-flow-step" aria-hidden="true" />
            <Reveal delay={starts[index]}>{limit(node, 74)}</Reveal>
          </div>
        ))}
        <div className="pim-flow-marker-track" aria-hidden="true">
          <span className="pim-flow-marker" style={{left: progress * 100 + '%'}} />
        </div>
      </div>
      {scene.formula && <Reveal delay={10} className="pim-flow-formula"><MathExpression text={scene.formula} /></Reveal>}
      <TalkingPoint items={list(scene.bullets).filter(item => !labels.includes(item))} scene={scene} frame={frame} />
    </div>
  );
}

function Chart({scene, zh, frame, appears = 0}) {
  const chart = scene.chart;
  const points = list(chart?.points).filter(point => typeof point?.label === 'string' && Number.isFinite(point?.value)).slice(0, 6);
  if (points.length < 2) return <Takeaways scene={scene} zh={zh} frame={frame} />;

  const stagger = Math.min(4, Math.max(1, Math.floor((scene.duration_frames - appears - 9) / points.length)));
  const starts = appears ? points.map((_, index) => appears + index * stagger) : stepTimes(scene, points.length);
  const active = starts.findLastIndex(start => start <= frame);
  const minimum = Math.min(0, ...points.map(point => point.value));
  const maximum = Math.max(0, ...points.map(point => point.value));
  const scale = Math.max(Math.abs(minimum), maximum) || 1;
  const range = maximum / scale - minimum / scale || 1;
  const origin = -minimum / scale / range * 100;
  const axis = [...new Set([minimum, 0, maximum])];

  return (
    <div className="pim-chart-layout">
      {(chart.title !== scene.title || chart.unit) && <div className="pim-chart-heading">
        {chart.title !== scene.title && <strong>{limit(chart.title, 100)}</strong>}
        {chart.unit && <span>{limit(chart.unit, 32)}</span>}
      </div>}
      <div className="pim-chart-body" role="img" aria-label={points.map(point => `${point.label} ${point.display_value ?? point.value}`).join(', ')}>
        {points.map((point, index) => {
          const fillFrames = Math.max(1, Math.min(appears ? 10 : 22, scene.duration_frames - starts[index] - 1));
          const progress = entrance(frame, starts[index], fillFrames);
          const length = Math.abs(point.value) / scale / range * 100 * progress;
          const tip = point.value < 0 ? origin - length : origin + length;
          const focused = index === active;
          const focus = focused ? entrance(frame, starts[index], 11) : 0;
          return (
            <div key={index} className={'pim-chart-row' + (focused ? ' is-active' : '')}>
              <span className="pim-chart-focus" style={{opacity: focus}} aria-hidden="true" />
              <div className="pim-chart-label" style={{opacity: .7 + .3 * progress}}>{limit(point.label, 75)}</div>
              <div className="pim-chart-track">
                <span className="pim-chart-zero" style={{left: `${origin}%`}} />
                <span className="pim-chart-bar" style={{left: `${origin - (point.value < 0 ? length : 0)}%`, width: `${length}%`}} />
                {focused && <span className="pim-chart-tip" style={{left: tip + '%', opacity: focus}} aria-hidden="true" />}
              </div>
              <div className="pim-chart-value" style={{opacity: progress}}>{point.display_value ?? String(point.value)}</div>
            </div>
          );
        })}
        <div className="pim-chart-scale" aria-hidden="true">
          {axis.map(value => {
            const position = (value / scale - minimum / scale) / range * 100;
            const separate = value !== 0 && Math.abs(position - origin) < 11;
            return separate ? null : <span key={value} style={{left: `${position}%`}}>{number(value)}</span>;
          })}
        </div>
      </div>
      {chart.source_label && <div className="pim-chart-source">{limit(chart.source_label, 120)}</div>}
    </div>
  );
}

function Equation({scene, zh, frame}) {
  const equations = list(scene.equations).filter(item => typeof item?.expression === 'string' && item.expression.trim()).slice(0, 3);
  if (!equations.length && scene.formula) equations.push({expression: scene.formula});
  if (!equations.length) return <Takeaways scene={scene} zh={zh} frame={frame} />;
  const active = activeStep(scene, frame, equations.length);
  const starts = stepTimes(scene, equations.length);
  return (
    <div className={'pim-equation-grid' + (!scene.bullets?.length ? ' is-solo' : '')}>
      <div className="pim-equation-panel">
        {equations.map(({label: name, expression}, index) => {
          const progress = entrance(frame, starts[index], 24);
          return (
            <div key={index} className={'pim-equation' + (index === active ? ' is-active' : '')}
              style={{opacity: progress * (index === active ? 1 : .66), transform: 'translateX(' + (1 - progress) * 30 + 'px)'}}>
              {name && <span className="pim-equation-label">{limit(name, 56)}</span>}
              <span className={expression.length > 70 ? 'is-long' : ''}><MathExpression text={expression} /></span>
              {index === active && <span className="pim-equation-underline" aria-hidden="true"
                style={{transform: 'scaleX(' + progress + ')'}} />}
            </div>
          );
        })}
      </div>
      <TalkingPoint items={scene.bullets} scene={scene} frame={frame} />
    </div>
  );
}

function Compare({scene, zh, frame}) {
  const items = list(scene.bullets);
  const comparison = scene.comparison;
  if (!comparison?.baseline || !comparison?.proposed) {
    return <Takeaways scene={{...scene, bullets: items}} zh={zh} frame={frame} />;
  }
  const sides = [
    {title: label(zh, '基线', 'Baseline'), items: comparison.baseline},
    {title: label(zh, '论文方法', 'Proposed method'), items: comparison.proposed},
  ];
  const starts = stepTimes(scene, sides.length);
  const active = activeStep(scene, frame, sides.length);
  return (
    <div className="pim-comparison">
      {sides.map((side, index) => (
        <Reveal key={side.title} delay={starts[index]} className={'pim-comparison-card' + (index === active ? ' is-active' : '')}>
          <h3>{side.title}</h3>
          <p>{limit(Array.isArray(side.items) ? side.items.join(' · ') : side.items, 145)}</p>
        </Reveal>
      ))}
    </div>
  );
}

function exampleStates(example) {
  if (list(example.states).length) {
    return example.states.filter(state => state?.label && Array.isArray(state.values)).slice(0, 8);
  }
  if (example.kind === 'low_rank') {
    return [
      {label: 'x', values: example.input},
      {label: 'W₀x', values: example.baseline},
      {label: 'Ax', values: example.hidden},
      {label: 'Δy', values: example.delta},
      {label: 'y', values: example.output},
    ];
  }
  if (example.kind === 'scaled_dot_attention') {
    return [
      {label: 'QKᵀ / √d', values: example.scores},
      {label: 'softmax(scores)', values: example.weights},
      {label: 'softmax(scores) × V', values: example.output},
    ];
  }
  return list(example.steps).filter(step => Array.isArray(step?.result)).slice(0, 8)
    .map(step => ({label: step.formula, values: step.result}));
}

function DataGrid({values}) {
  const rows = list(values);
  const isVector = !Array.isArray(rows[0]);
  const display = isVector ? [rows.slice(0, 6)] : rows.slice(0, 4).map(row => list(row).slice(0, 6));
  const truncated = isVector ? rows.length > 6 : rows.length > 4 || rows.some(row => list(row).length > 6);
  return (
    <div className="pim-matrix-values">
      {display.map((row, index) => (
        <div key={index} className="pim-matrix-row">
          {row.map((value, column) => <span key={column}>{number(value)}</span>)}
        </div>
      ))}
      {truncated && <span>…</span>}
    </div>
  );
}

function WorkedHeader({zh}) {
  return (
    <Reveal className="pim-executed-header">
      <span className="pim-kicker">{label(zh, '可执行示例', 'WORKED EXAMPLE')}</span>
      <span>{label(zh, '示例数值', 'Illustrative values')}</span>
    </Reveal>
  );
}

function StateCard({name, values, active, delay = 0}) {
  return (
    <Reveal delay={delay} className={'pim-state-card' + (active ? ' is-active' : '')}>
      <div className="pim-state-label">{name}</div>
      <DataGrid values={values} />
    </Reveal>
  );
}

function LoRA({scene, zh, frame}) {
  const example = scene.example;
  const active = activeStep(scene, frame, 4);
  const starts = stepTimes(scene, 4);
  return (
    <div className="pim-executed-layout">
      <WorkedHeader zh={zh} />
      <div className="pim-branches">
        <div className="pim-branch-input">
          <StateCard name="x" values={example.input} active={active === 0} />
          <Arrow active={active > 0} pulseStart={starts[1]} />
        </div>
        <div className="pim-branch-paths">
          <div className="pim-branch-path">
            <span className="pim-path-label">{label(zh, '冻结路径', 'Frozen path')}</span>
            <StateCard name="W₀x" values={example.baseline} active={active === 0} delay={starts[0]} />
          </div>
          <div className="pim-branch-path">
            <span className="pim-path-label">{label(zh, '低秩更新', 'Low-rank update')}</span>
            <StateCard name="Ax" values={example.hidden} active={active === 1} delay={starts[1]} />
            <Arrow active={active > 1} pulseStart={starts[2]} />
            <StateCard name={example.scale === 1 ? 'B(Ax)' : 's·B(Ax)'} values={example.delta} active={active === 2} delay={starts[2]} />
          </div>
        </div>
        <div className="pim-branch-output">
          <div className="pim-merge-path"><span>+</span><Arrow active={active > 2} pulseStart={starts[3]} /></div>
          <StateCard name="y" values={example.output} active={active === 3} delay={starts[3]} />
        </div>
      </div>
      <Reveal delay={16} className="pim-flow-formula">
        <MathExpression text={example.scale === 1 ? 'y = W₀x + B(Ax)' : 'y = W₀x + s·B(Ax)'} />
      </Reveal>
    </div>
  );
}

function CropSketch({geometry, highlight, zh}) {
  const center = [229, 124];
  const scale = Math.max(0.25, Math.abs(geometry[0]), Math.abs(geometry[1]), Math.abs(geometry[2]));
  const x = center[0] + 86 * geometry[0] / scale;
  const y = center[1] + 78 * geometry[1] / scale;
  const box = 22 + 36 * Math.abs(geometry[2]) / scale;
  return (
    <Reveal className="pim-crop">
      <svg viewBox="0 0 458 248" aria-label={label(zh, '人体框的全图位置示意', 'Schematic of the person box in the full frame')}>
        <rect x="1" y="1" width="456" height="246" rx="10" fill="var(--surface)" stroke="var(--line)" strokeWidth="2" />
        <path d="M19 124h420M229 18v212" fill="none" stroke="var(--line)" strokeWidth="1.5" strokeDasharray="4 5" />
        <path d={'M229 124H' + x + 'V' + y} fill="none" stroke="var(--warm)" strokeWidth={highlight ? 4 : 2} strokeDasharray="6 6" />
        <circle cx="229" cy="124" r="5.5" fill="var(--warm)" />
        <rect x={x - box / 2} y={y - box / 2} width={box} height={box} rx="5" fill="var(--accentPale)" stroke="var(--accent)" strokeWidth="3" />
        <circle cx={x} cy={y} r="4" fill="var(--accent)" />
      </svg>
      <span>{label(zh, '原图中心与人体框 · 示意', 'Frame center and box · schematic')}</span>
    </Reveal>
  );
}

function Cliff({scene, zh, frame}) {
  const example = scene.example;
  const states = exampleStates(example);
  const geometry = states.find(state => state.label === 'g')?.values;
  if (!Array.isArray(geometry) || geometry.length !== 3) return <ExecutedExample scene={scene} zh={zh} frame={frame} />;
  const appearance = states.find(state => state.label === 'v')?.values;
  const joined = states.find(state => state.label === '[v; g]')?.values;
  const active = activeStep(scene, frame, 3);
  const starts = stepTimes(scene, 3);
  return (
    <div className="pim-executed-layout">
      <WorkedHeader zh={zh} />
      <div className="pim-cliff-layout">
        <CropSketch geometry={geometry} highlight={active === 0} zh={zh} />
        <div className="pim-branch-paths">
          <div className="pim-branch-path">
            <span className="pim-path-label">{label(zh, '仅裁剪', 'Crop only')}</span>
            <StateCard name="v" values={appearance} active={active === 0} delay={3} />
            <Arrow active={active > 0} pulseStart={starts[1]} />
            <StateCard name={label(zh, '基线输出', 'Baseline output')} values={example.baseline} active={active === 2} delay={starts[2]} />
          </div>
          <div className="pim-branch-path">
            <span className="pim-path-label">{label(zh, '外观＋几何', 'Appearance + geometry')}</span>
            <StateCard name="g" values={geometry} active={active === 0} delay={3} />
            <Arrow active={active > 0} pulseStart={starts[1]} />
            <StateCard name="[v; g]" values={joined} active={active === 1} delay={starts[1]} />
            <Arrow active={active > 1} pulseStart={starts[2]} />
            <StateCard name={label(zh, '预测输出', 'Prediction')} values={example.output} active={active === 2} delay={starts[2]} />
          </div>
        </div>
      </div>
      <Reveal delay={15} className="pim-flow-formula"><MathExpression text="g = [cₓ/f, cᵧ/f, b/f]" /></Reveal>
    </div>
  );
}

function ExecutedExample({scene, zh, frame}) {
  const example = scene.example;
  const states = exampleStates(example).filter(state => Array.isArray(state.values));
  if (!states.length) return <Equation scene={scene} zh={zh} frame={frame} />;
  const active = activeStep(scene, frame, states.length + 1);
  const starts = stepTimes(scene, states.length + 1);
  const compare = active === states.length && Array.isArray(example.baseline) && Array.isArray(example.output);
  const first = Math.max(0, Math.min(states.length - 3, active - 1));
  const visibleStates = states.slice(first, first + 3);
  return (
    <div className="pim-executed-layout">
      <WorkedHeader zh={zh} />
      {compare ? (
        <div className="pim-state-comparison">
          <StateCard name={label(zh, '基线结果', 'Baseline result')} values={example.baseline} active={false} />
          <StateCard name={label(zh, '论文方法结果', 'Proposed method result')} values={example.output} active />
        </div>
      ) : (
        <div className="pim-state-row">
          {visibleStates.map((state, index) => (
            <StateCard
              key={first + index}
              name={limit(state.label, 72)}
              values={state.values}
              active={active === first + index}
              delay={starts[first + index]}
            />
          ))}
        </div>
      )}
      {!!scene.formula && <Reveal className="pim-flow-formula" delay={15}><MathExpression text={scene.formula} /></Reveal>}
    </div>
  );
}

function Figure({scene, zh, frame}) {
  const progress = entrance(frame, 0, Math.min(scene.duration_frames, 160));
  return (
    <div className={'pim-figure-layout' + (!scene.bullets?.length ? ' is-solo' : '')}>
      <Reveal className="pim-figure">
        <Img src={staticFile(scene.figure_file)} alt={scene.figure_caption || label(zh, '论文原图', 'Original paper figure')}
          style={{transform: `scale(${.9 + progress * .1})`}} />
        {scene.figure_source && <div className="pim-figure-source">{limit(scene.figure_source, 100)}</div>}
      </Reveal>
      <TalkingPoint items={scene.bullets} scene={scene} frame={frame} />
    </div>
  );
}

function Table({scene, zh, frame}) {
  const headers = list(scene.table?.headers).slice(0, 5);
  const rows = list(scene.table?.rows).slice(0, 7);
  if (!headers.length || !rows.length) return <Takeaways scene={scene} zh={zh} frame={frame} />;
  const starts = stepTimes(scene, rows.length);
  const active = activeStep(scene, frame, rows.length);
  const dense = rows.length > 5 || headers.length > 4;
  return (
    <Reveal className={'pim-table-card' + (dense ? ' is-dense' : '')}>
      <table className="pim-table">
        <thead>
          <tr>{headers.map((cell, index) => <th key={index}><span>{limit(String(cell ?? ''), 44)}</span></th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className={active === index ? 'is-active' : ''} style={{opacity: .45 + .55 * entrance(frame, starts[index], 12)}}>
              {headers.map((_, column) => <td key={column}><span>{limit(String(list(row)[column] ?? ''), 70)}</span></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </Reveal>
  );
}

function Takeaways({scene, zh, frame}) {
  const points = list(scene.bullets).filter(item => item?.trim?.());
  return (
    <div className="pim-takeaways">
      <TalkingPoint items={points} scene={scene} frame={frame} />
      {scene.formula && <Reveal className="pim-flow-formula" delay={10}><MathExpression text={scene.formula} /></Reveal>}
      {!points.length && !scene.formula && <TitleArtwork />}
    </div>
  );
}

function Content({scene, zh, frame}) {
  const props = {scene, zh, frame};
  if (scene.visual_type === 'title') return <Title {...props} />;
  if (scene.visual_type === 'chart' && scene.chart) return <Chart {...props} />;
  if (scene.visual_type === 'table' && scene.table?.rows?.length) return <Table {...props} />;
  if (scene.figure_file && ['figure', 'table', 'equation'].includes(scene.visual_type) &&
    !(scene.visual_type === 'equation' && scene.equations?.length)) return <Figure {...props} />;
  if (scene.example && ['matrix', 'equation', 'comparison'].includes(scene.visual_type)) {
    const isLoRA = scene.example.kind === 'low_rank' && scene.example.input && scene.example.hidden;
    const isCliff = scene.example.kind === 'cliff_geometry';
    const Component = isLoRA ? LoRA : isCliff ? Cliff : ExecutedExample;
    if (!scene.chart) return <Component {...props} />;
    const steps = isLoRA ? 4 : isCliff ? 3 : exampleStates(scene.example).length + 1;
    const lastStep = stepTimes(scene, steps).at(-1);
    const appears = Math.round(Math.max(lastStep + 18, scene.duration_frames * .70));
    if (appears < scene.duration_frames - 24 && frame >= appears) return <Chart {...props} appears={appears} />;
    return <Component {...props} />;
  }
  switch (scene.visual_type) {
    case 'flow': return <Flow {...props} />;
    case 'equation': return <Equation {...props} />;
    case 'comparison': return <Compare {...props} />;
    case 'table': return <Table {...props} />;
    default: return <Takeaways {...props} />;
  }
}

function captionAt(scene, frame, fps, zh) {
  if (Array.isArray(scene.cues)) {
    const cue = scene.cues.find(({start_frame, end_frame}) => frame >= start_frame && frame < end_frame);
    return cue?.text ?? '';
  }
  // Legacy projects did not store cues. Reproduce a readable estimate from their duration.
  const text = scene.narration ?? '';
  const parts = text.split(/(?<=[。！？]|[.!?](?!\d))\s*/).flatMap(part => {
    const words = part.trim();
    return zh ? words.match(/.{1,34}/gu) ?? [] : words.match(/.{1,92}(?:\s|$)|\S+/gu) ?? [];
  }).filter(Boolean);
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const audioFrames = scene.audio_duration > 0 ? Math.min(scene.duration_frames, scene.audio_duration * fps) : scene.duration_frames;
  if (frame >= audioFrames) return '';
  const position = frame / Math.max(audioFrames, 1) * total;
  let cursor = 0;
  return parts.find(part => {
    cursor += part.length;
    return cursor > position;
  })?.trim() ?? '';
}

function Scene({scene, manifest, index, start, total, previous, visualOnly = false}) {
  const {width, height, fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const zh = manifest.language === 'zh';
  const theme = ['editorial', 'midnight', 'classroom'].includes(manifest.style) ? manifest.style : 'editorial';
  const title = scene.visual_type === 'title';
  const caption = captionAt(scene, frame, fps, zh);
  const scale = `scale(${width / WIDTH}, ${height / HEIGHT})`;
  const transitionFrames = Math.round(fps * .32);
  const clipPath = previous && frame < transitionFrames
    ? `inset(0 ${(1 - entrance(frame, 0, transitionFrames)) * 100}% 0 0)`
    : undefined;
  const entry = entrance(frame, 0, 16);
  const camera = 1 + .045 * focusProgress(scene, frame, fps);
  const evidence = list(scene.evidence);
  const sourceLabels = [...new Set(evidence.map(item => {
    const page = item.physical_page ?? item.page;
    const document = item.document?.toLowerCase() === 'paper'
      ? label(zh, '论文', 'Paper')
      : item.document ?? 'PDF';
    return zh ? document + ' 第 ' + page + ' 页' : document + ' p. ' + page;
  }))];
  const sourcePages = list(scene.source_pages);
  const source = sourceLabels.length
    ? sourceLabels.slice(0, 3).join(' · ')
    : sourcePages.length
      ? label(zh, 'PDF 第 ' + sourcePages.join('、') + ' 页', 'PDF ' + (sourcePages.length === 1 ? 'p. ' : 'pp. ') + sourcePages.join(', '))
      : manifest.is_demo ? label(zh, '内置演示', 'Built-in demo') : '';

  return (
    <AbsoluteFill className={'pim-video is-' + theme} lang={zh ? 'zh-Hans' : 'en'}>
      {clipPath && (
        <Freeze frame={previous.duration_frames - 1}>
          <Scene scene={previous} manifest={manifest} index={index - 1}
            start={start - previous.duration_frames} total={total} visualOnly />
        </Freeze>
      )}
      <AbsoluteFill style={{background: 'inherit', clipPath}}>
        <div className="pim-stage" style={{transform: scale}}>
          <header className="pim-video-header">
            <span className="pim-brand"><span className="pim-brand-icon" />{limit(manifest.paper_title || manifest.title, 112)}</span>
            <div className="pim-chapter" aria-hidden="true">
              {manifest.scenes.map((_, chapter) => <span key={chapter} className={chapter <= index ? 'is-viewed' : ''} />)}
            </div>
          </header>
          {!title && (
            <Reveal className={'pim-scene-title' + (scene.title?.length > (zh ? 27 : 58) ? ' is-long' : '')}>
              {limit(scene.title, 100)}
            </Reveal>
          )}
          <main className={'pim-scene-content' + (title ? ' is-title' : '')}
            style={{opacity: entry, transform: `translateY(${(1 - entry) * 14}px) scale(${camera})`}}>
            <Content scene={scene} zh={zh} frame={frame} />
          </main>
          {source && <footer className="pim-footer"><span className="pim-source">{source}</span></footer>}
          {!visualOnly && <div className="pim-video-progress" style={{width: (start + frame + 1) / total * 100 + '%'}} />}
        </div>
      </AbsoluteFill>
      {!visualOnly && caption && (
        <div className="pim-stage" style={{transform: scale}}>
          <div className="pim-caption-wrap"><span className={'pim-caption' + (caption.length > (zh ? 48 : 125) ? ' is-long' : '')}>{caption}</span></div>
        </div>
      )}
      {!visualOnly && scene.audio_file && <Audio src={staticFile(scene.audio_file)} playbackRate={scene.audio_playback_rate ?? 1} preservePitch />}
    </AbsoluteFill>
  );
}

export function PaperVideo({manifest}) {
  const total = manifest.scenes.reduce((sum, scene) => sum + scene.duration_frames, 0);
  let start = 0;
  return (
    <AbsoluteFill>
      {manifest.scenes.map((scene, index) => {
        const from = start;
        start += scene.duration_frames;
        return (
          <Sequence key={scene.id ?? index} from={from} durationInFrames={scene.duration_frames}>
            <Scene scene={scene} manifest={manifest} index={index} start={from} total={total} previous={manifest.scenes[index - 1]} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}
