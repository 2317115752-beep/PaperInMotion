import katex from 'katex';

export const LOWER_SCRIPTS = Object.fromEntries(Array.from('₀₁₂₃₄₅₆₇₈₉ₓᵧₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥ₊₋₌').map((char, i) => [char, '0123456789xyaehijklmnoprstuv+−='[i]]));
export const UPPER_SCRIPTS = Object.fromEntries(Array.from('⁰¹²³⁴⁵⁶⁷⁸⁹ᵀⁿⁱᵏ⁺⁻⁼').map((char, i) => [char, '0123456789Tnik+−='[i]]));
const lowerScripts = new RegExp('[' + Object.keys(LOWER_SCRIPTS).join('') + ']+', 'gu');
const upperScripts = new RegExp('[' + Object.keys(UPPER_SCRIPTS).join('') + ']+', 'gu');
const delimiters = [['$$', '$$'], ['\\[', '\\]'], ['\\(', '\\)'], ['$', '$']];

export function formatMath(value) {
  const source = value.trim();
  if (!source) return null;
  const pair = delimiters.find(([open, close]) =>
    source.length > open.length + close.length && source.startsWith(open) && source.endsWith(close));
  const expression = (pair ? source.slice(pair[0].length, -pair[1].length).trim() : source)
    .replaceAll('∆', 'Δ')
    .replace(lowerScripts, run => '_{' + Array.from(run, char => LOWER_SCRIPTS[char]).join('') + '}')
    .replace(upperScripts, run => '^{' + Array.from(run, char => UPPER_SCRIPTS[char]).join('') + '}');
  try {
    return katex.renderToString(expression, {
      trust: false,
      strict: 'ignore',
      throwOnError: true,
      maxExpand: 100,
      maxSize: 10,
    });
  } catch (error) {
    if (!(error instanceof katex.ParseError)) throw error;
    return null;
  }
}

const greekNames = 'alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|lambda|mu|nu|xi|pi|varpi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega';
const greekName = new RegExp(String.raw`^(tan |sin |cos )?\\?(${greekNames})(?=[_^])`, 'u');
const unicodeScripts = Object.keys(LOWER_SCRIPTS).join('') + Object.keys(UPPER_SCRIPTS).join('');
const script = String.raw`(?:[_^](?:\{[^{}\n]{1,48}\}|[a-zA-Z0-9]+)|[${unicodeScripts}]+)`;
const inlineMath = String.raw`(?<inline>\\\([^\n]*?\\\)|\\\[[^\n]*?\\\]|(?<![\\$])\$\$[^\n$]+\$\$|(?<![\\$])\$(?!\s)[^\n$]+\$(?![\d$]))`;
const cliffNotation = {
  cx: 'c_x', cy: 'c_y', '2cx': '2c_x', '2cy': '2c_y',
  tx: 't_x', ty: 't_y', tz: 't_z', fCLIFF: String.raw`f_{\mathrm{CLIFF}}`,
  Ibbox: String.raw`I_{\mathrm{bbox}}`, theta: String.raw`\theta`, beta: String.raw`\beta`,
  J3D: String.raw`J_{3\mathrm{D}}`, J2D_full: String.raw`J_{2\mathrm{D}}^{\mathrm{full}}`,
  L2: 'L_2', L2D_full: String.raw`\mathcal{L}_{2\mathrm{D}}^{\mathrm{full}}`,
};

function captionPattern(aliases = []) {
  const scripted = String.raw`(?:tan |sin |cos )?(?:\\?(?:${greekNames})|[a-zA-Z\p{Script=Greek}])${script}+`;
  const shorthand = [scripted, ...aliases].join('|');
  const codeSpan = String.raw`(?<literal>\x60[^\x60\n]+\x60)`;
  return new RegExp(String.raw`${codeSpan}|${inlineMath}|(?<![\\\w])(?<shorthand>${shorthand})(?!\w|\.[a-zA-Z0-9])`, 'gu');
}

const plainCaptionPattern = captionPattern();
const cliffCaptionPattern = captionPattern(Object.keys(cliffNotation));

export function formatCaptionMath(text, paperTitle = '') {
  // Saved CLIFF storyboards contain spoken shorthand for the paper’s symbols.
  const isCliff = /^CLIFF(?=[:：]|$)/i.test(paperTitle);
  const notation = isCliff ? cliffNotation : {};
  const pattern = isCliff ? cliffCaptionPattern : plainCaptionPattern;
  const parts = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const [source] = match;
    const {inline, shorthand, literal} = match.groups;
    if (literal) continue;
    const expression = inline ?? (notation[shorthand] ?? shorthand.replace(greekName,
      (_, operator, symbol) => (operator ? '\\' + operator.trim() + ' ' : '') + '\\' + symbol));
    const html = formatMath(inline ? expression : expression.replace(/([_^])([a-zA-Z0-9]+)/g, '$1{$2}'));
    if (!html) continue;
    if (match.index > cursor) parts.push({text: text.slice(cursor, match.index)});
    parts.push({text: source, html});
    cursor = match.index + source.length;
  }
  if (cursor < text.length) parts.push({text: text.slice(cursor)});
  return parts;
}
