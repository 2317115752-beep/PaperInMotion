import assert from 'node:assert/strict';
import {test} from 'node:test';
import {formatCaptionMath, formatMath} from '../renderer/math-format.mjs';

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


test('typesets CLIFF narration with the paper’s subscript and superscript meanings', () => {
  const title = 'CLIFF: Carrying Location Information in Full Frames into Human Pose and Shape Estimation';
  const text = '等于tan gamma_X、tan gamma_Y，得到J2D_full，计算L2D_full。';
  const parts = formatCaptionMath(text, title);
  assert.equal(parts.map(part => part.text).join(''), text);
  const maths = parts.filter(part => part.html).map(part => part.html);
  assert.equal(maths.length, 4);
  assert.match(maths[0], /<msub><mi>γ<\/mi><mi>X<\/mi><\/msub>/);
  assert.match(maths[1], /<msub><mi>γ<\/mi><mi>Y<\/mi><\/msub>/);
  assert.match(maths[2], /<msubsup><mi>J<\/mi>.*<\/msubsup>/);
  assert.match(maths[3], /<msubsup><mi mathvariant="script">L<\/mi>.*<\/msubsup>/);
});

test('preserves surrounding prose, corrects Unicode scripts, and typesets delimited math', () => {
  const parts = formatCaptionMath(String.raw`Start with cᵧ, \(\frac{a_i}{2}\), and $x_{out}^2$，然后结束。`);
  const maths = parts.filter(part => part.html).map(part => part.html);
  assert.equal(maths.length, 3);
  assert.match(maths[0], /<msub><mi>c<\/mi><mi>y<\/mi><\/msub>/);
  assert.match(maths[1], /<mfrac>.*<msub>/);
  assert.match(maths[2], /<msubsup><mi>x<\/mi>/);
  assert.deepEqual(formatCaptionMath('Costs $5 and $10. Use report_v2.txt.'),
    [{text: 'Costs $5 and $10. Use report_v2.txt.'}]);
  const broken = String.raw`Keep invalid math \(\frac{1}{\) readable.`;
  assert.deepEqual(formatCaptionMath(broken), [{text: broken}]);
});

test('supports upper-case and named scripts without changing file names or code spans', () => {
  const text = '从 E_{out}、y_hat、W_q 和 Δₜ 到 w_1.npy 或 `x_1`。';
  const parts = formatCaptionMath(text);
  assert.equal(parts.map(part => part.text).join(''), text);
  assert.deepEqual(parts.filter(part => part.html).map(part => part.text), ['E_{out}', 'y_hat', 'W_q', 'Δₜ']);
});

test('typesets combining accents together with subscripts in ordinary captions', () => {
  const text = 'CNN 里 v̂_t 变小，比较 m̂ₜ、x̄_i 和 θ̂_t。代码 `v̂_t` 保持原样。';
  const parts = formatCaptionMath(text);
  assert.equal(parts.map(part => part.text).join(''), text);
  const maths = parts.filter(part => part.html);
  assert.deepEqual(maths.map(part => part.text), ['v̂_t', 'm̂ₜ', 'x̄_i', 'θ̂_t']);
  for (const {html} of maths) assert.match(html, /<msub><mover accent="true">/);
});
