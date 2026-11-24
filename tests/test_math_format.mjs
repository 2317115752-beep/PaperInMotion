import assert from 'node:assert/strict';
import {test} from 'node:test';
import {formatMath} from '../renderer/math-format.mjs';

test('renders the sample video’s Greek symbol and subscript', () => {
  assert.match(formatMath(String.raw`\Delta y = B(Ax)`), /<mi[^>]*>Δ<\/mi>/);
  assert.match(formatMath('y = W_0 x + BAx = [9,-2]'), /<msub><mi>W<\/mi><mn>0<\/mn><\/msub>/);
});

test('preserves Latin y in subscripts from saved storyboards', () => {
  assert.match(formatMath('g = [cₓ/f, cᵧ/f, b/f]'), /<msub><mi>c<\/mi><mi>y<\/mi><\/msub>/);
});

test('renders structured TeX inside common delimiters', () => {
  assert.match(formatMath(String.raw`$$\frac{a_i}{\sqrt{b^2}}$$`), /<mfrac>.*<msqrt>.*<msup>/);
  assert.match(formatMath(String.raw`\(\sum_{i=1}^n x_i\)`), /<msubsup><mo>∑<\/mo>/);
  assert.match(formatMath(String.raw`$\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}$`), /<mtable /);
});

test('falls back on invalid TeX and blocks embedded links', () => {
  assert.equal(formatMath(String.raw`\frac{1}{`), null);
  assert.doesNotMatch(formatMath(String.raw`\href{https://example.com}{x}`), /<a /);
});
