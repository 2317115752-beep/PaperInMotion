import assert from 'node:assert/strict';
import test from 'node:test';
import {sourceFocusPlan, sourcePanelLayout} from '../renderer/source-figure-motion.mjs';

const figure1 = 'Fig. 1. In the upper part, the cropped images are presented. The lower part shows their global rotations.';
const figure4 = 'Fig. 4. Our pipeline to generate 3D annotations. (a) Pretrain the model. (b) Test on the target dataset. (c) Finetune with weak supervision. (d) Infer parameters as pseudo-GT.';
const pipelineCue = '流程分四步：先在三维标注数据集上预训练，然后在目标数据集上预测SMPL参数作为显式先验，接着用二维关键点做弱监督微调，最后输出高质量三维标注。';

function plan(caption, text, options = {}) {
  return sourceFocusPlan({
    caption, cues: [{start_frame: 0, end_frame: 120, text}], durationFrames: 120, ...options,
  });
}

test('scopes highlights to explicitly matched upper or lower panels', () => {
  assert.deepEqual(plan(figure1, '上排三张裁剪图')[0].regions, [
    {key: 'upper', x: 0, y: 0, width: 1, height: 0.5},
  ]);
  assert.equal(plan(figure1, 'rotations in the bottom row')[0].regions[0].key, 'lower');
  assert.equal(plan(figure1, '鸟瞰图能看到全局旋转')[0].mode, 'full');
  assert.equal(plan(figure1, 'The upper row and lower row')[0].mode, 'full');
});

test('recognizes left and right panel markers but not the side of a depicted object', () => {
  const caption = 'Fig. 3. (left) First three epochs. (right) All 45 epochs.';
  assert.equal(plan(caption, '看右图的训练损失')[0].regions[0].key, 'right');
  assert.equal(plan(caption, 'Over all 45 epochs')[0].mode, 'full');
  const body = 'Fig. 2. The left side and the right side of a person.';
  assert.equal(plan(body, 'The pose of the left side is ambiguous.')[0].mode, 'full');
});

test('keeps full framing when the cue explicitly refers to another figure', () => {
  const caption = 'Figure 4. (left) Baseline. (right) Our model.';
  assert.equal(plan(caption, 'Figure 3 shows the left plot.')[0].mode, 'full');
  assert.equal(plan(caption, '图3里的左图。')[0].mode, 'full');
  assert.equal(plan(caption, 'Figure 4 shows the left plot.')[0].mode, 'panel');
});

test('lettered panels require explicit layout and follow the caption order', () => {
  const caption = 'Fig. 4. (a) Baseline. (b) Ablation. (c) Updated model. (d) Noise test.';
  assert.deepEqual(sourcePanelLayout(caption), []);
  assert.equal(plan(caption, 'See panel c.')[0].mode, 'full');
  const explicit = 'Fig. 4. From left to right: (c) Updated model. (a) Baseline. (b) Ablation.';
  assert.deepEqual(plan(explicit, 'See panel c.')[0].regions, [
    {key: 'c', x: 0, y: 0, width: 1 / 3, height: 1},
  ]);
  const vertical = 'Fig. 4. From top to bottom: (a) Baseline. (b) Ablation.';
  assert.deepEqual(plan(vertical, 'See panel b.')[0].regions, [
    {key: 'b', x: 0, y: 0.5, width: 1, height: 0.5},
  ]);
});

test('view captions do not imply column count, order or duplicated groups', () => {
  const caption = 'Fig. 6. Qualitative results. From left to right: side view, front view, input images.';
  assert.deepEqual(sourcePanelLayout(caption), []);
  assert.equal(plan(caption, 'Show the front view.')[0].mode, 'full');
});

test('numbered phrases do not imply a panel or connect unrelated panels', () => {
  const caption = 'Fig. 5. From left to right: (a) Image. (b) Fine-tuned version. (c) Attention map. (d) Depth estimate.';
  assert.equal(plan(caption, 'In the second step, we use an independent protocol.')[0].mode, 'full');
  assert.deepEqual(plan(caption, 'Panel b is the fine-tuned result.')[0].regions.map(region => region.key), ['b']);
});

test('animates verified compound steps while keeping geometry-neutral full framing', () => {
  const steps = plan(figure4, pipelineCue, {zh: true}).filter(interval => interval.label);
  assert.deepEqual(steps.map(interval => interval.label), [
    '(a) 预训练', '(b) 测试与预测', '(c) 微调', '(d) 输出',
  ]);
  assert.ok(steps.every(interval => interval.mode === 'full' && !interval.regions.length));
  assert.ok(steps[0].start > 0);
  assert.equal(steps.at(-1).end, 120);
  assert.ok(steps.every(interval => interval.end > interval.start));
});

test('localizes a matched process label and rejects other computations', () => {
  const confirmed = plan(figure4, 'In the second step, the model predicts a prior.')[0];
  assert.equal(confirmed.label, '(b) Testing and prediction');
  assert.equal(confirmed.mode, 'full');
  assert.equal(plan(figure4, 'In the second step, take the average.')[0].label, undefined);
  assert.equal(plan(figure4, 'In Figure 7, the second step predicts a prior.')[0].label, undefined);
});

test('sorts timeline events and clips them to scene boundaries', () => {
  const result = sourceFocusPlan({
    caption: figure1, durationFrames: 70,
    cues: [
      {start_frame: 25, end_frame: 49, text: 'The upper row.'},
      {start_frame: 0, end_frame: 30, text: 'Introduction.'},
      {start_frame: 55, end_frame: 80, text: 'The lower row.'},
    ],
  });
  assert.deepEqual(result.map(({start, end, mode}) => [start, end, mode]), [
    [0, 25, 'full'], [25, 49, 'panel'], [55, 70, 'panel'],
  ]);
});
