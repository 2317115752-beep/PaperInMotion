const normalize = text => text.normalize('NFKC').toLowerCase().replace(/\s+/gu, ' ').trim();

function spokenWeight(text) {
  let weight = 0;
  for (const character of text) {
    if (/[a-z0-9]/u.test(character)) weight += .6;
    else if (/[\p{L}\p{N}]/u.test(character)) weight += 1;
    else if (/[,;:.!?，；：。！？]/u.test(character)) weight += .3;
  }
  return weight;
}

function matchLabel(text, name, cursor) {
  let index = text.indexOf(name, cursor);
  const startsWithLatin = /^[a-z0-9]/u.test(name);
  const endsWithLatin = /[a-z0-9]$/u.test(name);
  while (index >= 0) {
    const left = startsWithLatin && /[a-z0-9]/u.test(text[index - 1] ?? '');
    const right = endsWithLatin && /[a-z0-9]/u.test(text[index + name.length] ?? '');
    if (!left && !right) return index;
    index = text.indexOf(name, index + 1);
  }
  return -1;
}

// Cue timings are measured. Positions within a cue are estimated from the spoken text.
export function equationCueStarts(equations, cues) {
  if (!Array.isArray(equations) || !equations.length || !Array.isArray(cues) || !cues.length) return null;
  const labels = equations.map(equation => typeof equation?.label === 'string' ? normalize(equation.label) : '');
  if (labels.some(name => !name) || new Set(labels).size !== labels.length) return null;

  const starts = [];
  for (const cue of cues) {
    const {text, start_frame: start, end_frame: end} = cue ?? {};
    if (typeof text !== 'string' || !Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) {
      continue;
    }
    const narration = normalize(text);
    const totalWeight = spokenWeight(narration);
    if (!totalWeight) continue;
    let cursor = 0;
    while (starts.length < labels.length) {
      const name = labels[starts.length];
      const offset = matchLabel(narration, name, cursor);
      if (offset < 0) break;
      const fraction = spokenWeight(narration.slice(0, offset)) / totalWeight;
      const frame = Math.min(end - 1, start + Math.round((end - start) * fraction));
      if (frame <= starts.at(-1)) return null;
      starts.push(frame);
      cursor = offset + name.length;
    }
    if (starts.length === labels.length) return starts;
  }
  return null;
}
