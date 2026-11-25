import assert from 'node:assert/strict';
import {test} from 'node:test';
import {equationCueStarts} from '../renderer/equation-timing.mjs';

const equations = (...labels) => labels.map(label => ({label}));
const cue = (text, start_frame, end_frame) => ({text, start_frame, end_frame});

test('estimates three sequential CLIFF terms inside one measured Mandarin cue', () => {
  const cues = [
    cue('转换公式分三步。', 0, 35),
    cue('Ｘ方向加上二倍cx除以b乘s，Y方向加上二倍cy除以b乘s，Z方向乘以焦距比再乘以分辨率比。', 37, 243),
    cue('我们用示例数值代入。', 246, 436),
  ];
  const frames = equationCueStarts(equations('X方向', 'Y方向', 'Z方向'), cues);
  assert.equal(frames[0], 37);
  assert.ok(frames[1] >= 95 && frames[1] <= 108, 'Y starts around the next clause');
  assert.ok(frames[2] >= 155 && frames[2] <= 172, 'Z starts around the third clause');
  assert.ok(frames[2] < 243);
});

test('anchors labels in successive cues and respects word boundaries', () => {
  const cues = [
    cue('We define baseline and update rules.', 0, 100),
    cue('Base is the initial value.', 110, 210),
    cue('The adjusted step is next.', 220, 340),
  ];
  const frames = equationCueStarts(equations('BASE', 'adjusted step'), cues);
  assert.equal(frames[0], 110);
  assert.ok(frames[1] > 220 && frames[1] < 260);
});

test('falls back when a complete sequence in supplied order cannot be timed', () => {
  const cues = [cue('Start with Y direction, then X direction.', 20, 110)];
  assert.equal(equationCueStarts(equations('X direction', 'Y direction'), cues), null);
  assert.equal(equationCueStarts(equations('Y direction', 'Z direction'), cues), null);
  assert.equal(equationCueStarts(equations('Y direction', ''), cues), null);
  assert.equal(equationCueStarts(equations('Y direction', 'y direction'), cues), null);
  assert.equal(equationCueStarts(equations('Y direction', 'X direction'), [cue(cues[0].text, 0, 1)]), null);
  assert.equal(equationCueStarts(equations('X方向'), undefined), null);
});
