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
