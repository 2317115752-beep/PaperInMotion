const normalize = value => typeof value === 'string' ? value.normalize('NFKC').toLowerCase() : '';

const FIGURE_REFERENCE = /(?:\bfig(?:ure)?s?\.?\s*|图\s*)(\d+[a-z]?)/gu;
const PANEL_MARKERS = [
  {
    key: 'upper', axis: 'vertical',
    pattern: /\b(?:upper|top) (?:part|row|half|panel)\b|\((?:upper|top)\)|上(?:排|半(?:部(?:分)?)?|图)/u,
  },
  {
    key: 'lower', axis: 'vertical',
    pattern: /\b(?:lower|bottom) (?:part|row|half|panel)\b|\((?:lower|bottom)\)|下(?:排|半(?:部(?:分)?)?|图)/u,
  },
  {
    key: 'left', axis: 'horizontal',
    pattern: /\bleft (?:panel|plot|half|column)\b|\(left\)|左(?:图|栏|半(?:部(?:分)?)?)/u,
  },
  {
    key: 'right', axis: 'horizontal',
    pattern: /\bright (?:panel|plot|half|column)\b|\(right\)|右(?:图|栏|半(?:部(?:分)?)?)/u,
  },
];

const PHASES = [
  {pattern: /\bpre[ -]?train\w*\b|预训练/u, zh: '预训练', en: 'Pretraining'},
  {pattern: /\b(?:test|predict|infer)\w*\b|测试|预测|推理/u, zh: '测试与预测', en: 'Testing and prediction'},
  {pattern: /\bfine[ -]?tun\w*\b|微调/u, zh: '微调', en: 'Fine-tuning'},
  {pattern: /\b(?:infer|output)\w*\b|pseudo[ -]?(?:ground[ -]?truth|gt)|推理|输出|伪标注|伪标签/u,
    zh: '输出', en: 'Output'},
];

function normalizedPanels(keys, axis) {
  const size = 1 / keys.length;
  const horizontal = axis === 'horizontal';
  return keys.map((key, index) => ({
    key, x: horizontal ? index * size : 0, y: horizontal ? 0 : index * size,
    width: horizontal ? size : 1, height: horizontal ? 1 : size,
  }));
}

function letteredDescriptions(text) {
  return [...text.matchAll(/\(([a-d])\)\s*([^]*?)(?=\([a-d]\)|$)/gu)]
    .map(([_, key, description]) => ({key, description}));
}

export function sourcePanelLayout(caption) {
  const text = normalize(caption);
  const directional = PANEL_MARKERS.filter(marker => marker.pattern.test(text));
  if (directional.length === 2 && directional[0].axis === directional[1].axis) {
    return normalizedPanels(directional.map(marker => marker.key), directional[0].axis);
  }

  const letters = letteredDescriptions(text).map(({key}) => key);
  if (letters.length < 2 || new Set(letters).size !== letters.length) return [];
  const horizontal = /(?:from left to right|left to right|由左至右|从左到右)\s*[:：,，]?\s*\([a-d]\)/u.test(text);
  const vertical = /(?:from top to bottom|top to bottom|由上至下|从上到下)\s*[:：,，]?\s*\([a-d]\)/u.test(text);
  if (horizontal === vertical) return [];
  return normalizedPanels(letters, horizontal ? 'horizontal' : 'vertical');
}

function referencesDifferentFigure(caption, cue) {
  const [ownNumber] = [...caption.matchAll(FIGURE_REFERENCE)].map(match => match[1]);
  return [...cue.matchAll(FIGURE_REFERENCE)].some(match => match[1] !== ownNumber);
}

function sourcePanelFocus(panels, cue) {
  const directions = PANEL_MARKERS.filter(marker => marker.pattern.test(cue));
  if (directions.length > 1) return [];
  if (directions.length === 1) return panels.filter(panel => panel.key === directions[0].key);
  const matches = [...cue.matchAll(/\(([a-d])\)|\b(?:panel|subfigure)\s+([a-d])\b|子图\s*([a-d])/gu)];
  const keys = [...new Set(matches.map(match => match[1] ?? match[2] ?? match[3]))];
  return keys.every(key => panels.some(panel => panel.key === key))
    ? panels.filter(panel => keys.includes(panel.key)) : [];
}

function stepLabel(description, phase, zh) {
  return `(${description.key}) ${zh ? phase.zh : phase.en}`;
}

function narratedSteps(descriptions, cue, span, zh) {
  const anchors = [...cue.matchAll(/\b(?:first|then|next|finally)\b|先(?=在|用|对|做|预)|然后|接着|最后/gu)];
  if (anchors.length === PHASES.length && span >= 72) {
    const clauses = anchors.map((anchor, index) => cue.slice(anchor.index, anchors[index + 1]?.index ?? cue.length));
    if (PHASES.every((phase, index) => phase.pattern.test(clauses[index]))) {
      return anchors.map((anchor, index) => ({
        offset: Math.floor(span * anchor.index / cue.length),
        key: descriptions[index].key,
        label: stepLabel(descriptions[index], PHASES[index], zh),
      }));
    }
  }

  const ordinalPatterns = [
    /\b(?:first (?:step|stage)|step 1|stage 1)\b|第(?:一|1)步/u,
    /\b(?:second (?:step|stage)|step 2|stage 2)\b|第(?:二|2)步/u,
    /\b(?:third (?:step|stage)|step 3|stage 3)\b|第(?:三|3)步/u,
    /\b(?:fourth (?:step|stage)|step 4|stage 4)\b|第(?:四|4)步/u,
  ];
  const mentions = ordinalPatterns.flatMap((pattern, index) => pattern.test(cue) ? [index] : []);
  if (mentions.length !== 1 || !PHASES[mentions[0]].pattern.test(cue)) return [];
  const index = mentions[0];
  return [{offset: 0, key: descriptions[index].key, label: stepLabel(descriptions[index], PHASES[index], zh)}];
}

export function sourceFocusPlan({caption, cues, beats, durationFrames, zh = false}) {
  const duration = Number.isFinite(durationFrames) && durationFrames > 0 ? durationFrames : 0;
  const captionText = normalize(caption);
  const panels = sourcePanelLayout(captionText);
  const describedSteps = letteredDescriptions(captionText);
  const verifiedProcess = describedSteps.map(({key}) => key).join('') === 'abcd' &&
    PHASES.every((phase, index) => phase.pattern.test(describedSteps[index].description));
  const events = Array.isArray(cues) && cues.length ? cues : Array.isArray(beats) ? beats : [];
  const valid = events.filter(event => Number.isInteger(event?.start_frame) &&
    event.start_frame >= 0 && event.start_frame < duration).sort((a, b) => a.start_frame - b.start_frame);
  const unique = valid.filter((event, index) => event.start_frame !== valid[index - 1]?.start_frame);

  return unique.flatMap((event, index) => {
    const start = event.start_frame;
    const nextStart = unique[index + 1]?.start_frame ?? duration;
    const hasEnd = Number.isInteger(event.end_frame) && event.end_frame > start;
    const end = Math.min(nextStart, hasEnd ? event.end_frame : duration);
    const cue = normalize(event.text);
    if (referencesDifferentFigure(captionText, cue)) return [{start, end, regions: [], mode: 'full'}];

    const regions = sourcePanelFocus(panels, cue);
    if (regions.length) return [{start, end, regions, mode: 'panel'}];
    const steps = verifiedProcess ? narratedSteps(describedSteps, cue, end - start, zh) : [];
    if (!steps.length) return [{start, end, regions: [], mode: 'full'}];

    const frames = steps.map(({offset, key, label}, index) => {
      const regions = panels.filter(panel => panel.key === key);
      return {
        start: start + offset,
        end: steps[index + 1] ? start + steps[index + 1].offset : end,
        label, regions, mode: regions.length ? 'panel' : 'full',
      };
    }).filter(step => step.end > step.start);
    return frames[0].start > start ? [{start, end: frames[0].start, regions: [], mode: 'full'}, ...frames] : frames;
  });
}
