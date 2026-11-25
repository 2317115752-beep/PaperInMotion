import assert from 'node:assert/strict';
import {test} from 'node:test';
import {narratedOutline} from '../renderer/narrated-outline.mjs';

const cue = (text, start_frame, end_frame) => ({text, start_frame, end_frame});

test('preserves the two explicit changes in the saved CLIFF overview', () => {
  const cues = [
    cue('CLIFF做了两个关键改动来修复这个问题。', 0, 65),
    cue('第一，把边界框信息也作为输入喂给回归器，让模型知道裁剪区域在原始画面中的位置和大小。', 68, 245),
    cue('第二，把二维重投影损失算在完整图像上，而不是裁剪图上。', 248, 355),
    cue('接下来我们逐步来看这两个改动在计算中是怎么实现的。', 358, 444),
    cue('两个改动分别对应两个核心问题：输入端缺少位置信息，监督端缺少全局视角。', 447, 597),
  ];
  const anchors = narratedOutline(cues);
  assert.deepEqual(anchors.map(({start, end, text, detail}) => ({start, end, text, detail})), [
    {start: 68, end: 245, text: '把边界框信息也作为输入喂给回归器', detail: '让模型知道裁剪区域在原始画面中的位置和大小。'},
    {start: 248, end: 355, text: '把二维重投影损失算在完整图像上', detail: '而不是裁剪图上。'},
  ]);
  for (let i = 0; i < anchors.length; i++) {
    assert.ok(anchors[i].detailStart > cues[i + 1].start_frame);
    assert.ok(anchors[i].detailStart < cues[i + 1].end_frame);
  }
});

test('preserves notation and only splits clauses outside math', () => {
  const anchors = narratedOutline([
    cue('First, Evaluate f(x, y) at 1,000 points, then compute the mean.', 0, 80),
    cue('Second: Compare $J_{2D}$ to the annotation.', 85, 150),
  ]);
  assert.equal(anchors[0].text, 'Evaluate f(x, y) at 1,000 points');
  assert.equal(anchors[0].detail, 'then compute the mean.');
  assert.deepEqual(anchors[1], {start: 85, end: 150, text: 'Compare $J_{2D}$ to the annotation.'});
});

test('requires a contiguous numbered sequence of two through four distinct cues', () => {
  const numbered = (order, index) => cue(order + ', show the inputs.', index * 100, index * 100 + 80);
  assert.equal(narratedOutline(['First', 'Second', 'Third', 'Fourth'].map(numbered)).length, 4);
  assert.deepEqual(narratedOutline(['First', 'Second', 'Third', 'Fourth', 'Fifth'].map(numbered)), []);
  assert.deepEqual(narratedOutline(['First', 'Second', 'Fourth'].map(numbered)), []);
  assert.deepEqual(narratedOutline(['Second', 'Third'].map(numbered)), []);
  assert.deepEqual(narratedOutline([cue('Show the input.', 0, 80), cue('Compare results.', 90, 160)]), []);
  assert.deepEqual(narratedOutline([cue('First, 1.', 0, 80), numbered('Second', 1)]), []);
  assert.deepEqual(narratedOutline([numbered('First', 0), cue('Explain terms.', 90, 120), numbered('Second', 2)]), []);
  assert.deepEqual(narratedOutline([numbered('First', 0), numbered('Second', 0)]), []);
});
