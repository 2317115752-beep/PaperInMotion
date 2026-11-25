const ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'];
const CHINESE_NUMERALS = '一二三四五六七八九十';
const ENGLISH_PREFIX = /^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)[,;:]\s+/iu;
const CHINESE_PREFIX = /^第([一二三四五六七八九十]+)(?:步|点)?[、，,:：；;]\s*/u;
const CLAUSE_BREAK = /[，；;]+|,\s+/gu;

function outlineItem(cue) {
  if (!cue || typeof cue.text !== 'string' || !Number.isInteger(cue.start_frame)
      || !Number.isInteger(cue.end_frame) || cue.start_frame < 0 || cue.end_frame <= cue.start_frame) return null;
  const sentence = cue.text.trim();
  const english = ENGLISH_PREFIX.exec(sentence);
  const chinese = CHINESE_PREFIX.exec(sentence);
  const prefix = english ?? chinese;
  if (!prefix) return null;

  const numeral = english ? ORDINALS.indexOf(english[1].toLowerCase()) + 1
    : chinese[1].length === 1 ? CHINESE_NUMERALS.indexOf(chinese[1]) + 1 : 11;
  const body = sentence.slice(prefix[0].length).trim();
  const split = [...body.matchAll(CLAUSE_BREAK)].find(({index}) => {
    // Skip commas and semicolons inside math expressions or quoted phrases.
    const before = body.slice(0, index);
    return (before.match(/[([{（［【「“]/gu)?.length ?? 0)
        === (before.match(/[)\]}）］】」”]/gu)?.length ?? 0)
        && (before.match(/(?<!\\)\$/gu)?.length ?? 0) % 2 === 0;
  });
  const text = (split ? body.slice(0, split.index) : body).trim();
  if ((text.match(/[\p{L}\p{N}]/gu)?.length ?? 0) < 4 || !/\p{L}/u.test(text)) {
    return {numeral, anchor: null};
  }
  const anchor = {start: cue.start_frame, end: cue.end_frame, text};
  const detail = split && body.slice(split.index + split[0].length).trim();
  if (detail) {
    const offset = Array.from(sentence.slice(0, sentence.length - detail.length)).length;
    const cueLength = Array.from(sentence).length;
    anchor.detail = detail;
    anchor.detailStart = Math.min(cue.end_frame - 1, cue.start_frame
      + Math.round((cue.end_frame - cue.start_frame) * offset / cueLength));
  }
  return {numeral, anchor};
}

export function narratedOutline(cues) {
  if (!Array.isArray(cues)) return [];
  let outline = [];
  for (const cue of cues) {
    const item = outlineItem(cue);
    if (item?.numeral === outline.length + 1 && item.anchor
        && (!outline.length || item.anchor.start >= outline.at(-1).end)) {
      outline.push(item.anchor);
    } else if (!item && outline.length >= 2 && outline.length <= 4) {
      return outline;
    } else {
      outline = item?.numeral === 1 && item.anchor ? [item.anchor] : [];
    }
  }
  return outline.length >= 2 && outline.length <= 4 ? outline : [];
}
