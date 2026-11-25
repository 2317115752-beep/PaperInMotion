import React, {useMemo} from 'react';
import {formatMath} from './math-format.mjs';
import './cliff-sequence.css';

const label = (zh, chinese, english) => zh ? chinese : english;
const clamp = value => Math.min(1, Math.max(0, value));
const mix = (from, to, progress) => from + (to - from) * progress;

function across(frame, start, end) {
  return 1 - (1 - clamp((frame - start) / Math.max(1, end - start))) ** 3;
}

function atCue(scene, index, fraction, fallback) {
  const cue = scene.cues?.[scene.beat_cues?.[index] ?? index];
  if (!Number.isFinite(cue?.start_frame) || !Number.isFinite(cue?.end_frame)) {
    return scene.duration_frames * fallback;
  }
  return mix(cue.start_frame, cue.end_frame, fraction);
}

function MathLabel({value}) {
  const markup = useMemo(() => formatMath(value), [value]);
  return markup
    ? <span dangerouslySetInnerHTML={{__html: markup}} />
    : <span>{value}</span>;
}

// Articulated pose for the explanatory diagrams. Coordinates carry no experimental values.
const POSE = [
  [-4, -99, -9], [0, -67, -6], [-30, -60, 2], [30, -67, -3],
  [-62, -34, 20], [60, -89, -12], [-76, -60, 35], [77, -117, 6],
  [0, -4, 4], [-21, 2, 0], [19, 3, 9],
  [-43, 52, 20], [24, 52, 5], [-34, 108, 22], [46, 107, -12],
];

const BONES = [
  [0, 1], [1, 2], [1, 3], [2, 4], [4, 6], [3, 5], [5, 7],
  [1, 8], [8, 9], [8, 10], [9, 10], [9, 11], [11, 13], [10, 12], [12, 14],
];

function Skeleton({points, color = 'var(--accent)', opacity = 1, width = 5, dots = true}) {
  return (
    <g opacity={opacity} strokeLinecap="round">
      {BONES.map(([from, to]) => (
        <line key={from + ':' + to} x1={points[from][0]} y1={points[from][1]} x2={points[to][0]}
          y2={points[to][1]} stroke={color} strokeWidth={width} />
      ))}
      {dots && points.map(([x, y], index) => (
        <circle key={index} cx={x} cy={y} r={index === 0 ? 6 : 4} fill="var(--surface)" stroke={color} strokeWidth="2.5" />
      ))}
    </g>
  );
}

function Silhouette({x, y, scale = 1, color = 'var(--accent)'}) {
  return (
    <g transform={'translate(' + x + ' ' + y + ') scale(' + scale + ')'} fill={color} stroke={color}>
      <ellipse cx="-4" cy="-97" rx="16" ry="20" stroke="none" />
      <path d="M-21-66Q-4-75 20-66L31-57 22-4 18 9-21 8-25-4-34-55Z" stroke="none" />
      <g strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path d="M-25-57-61-32-76-61M26-61 60-88 77-116" strokeWidth="17" />
        <path d="M-15 0-40 50-34 101M14 2 24 52 46 104" strokeWidth="21" />
        <path d="M-34 103-50 108M46 105 63 105" strokeWidth="13" />
      </g>
    </g>
  );
}

function Schematic({zh}) {
  return <span className="pim-cliff-schematic">{label(zh, '示意图', 'Schematic')}</span>;
}

const ACTIVATIONS = Array.from({length: 72}, (_, index) =>
  .14 + ((index * 31 + Math.floor(index / 8) * 13) % 73) / 100);

function CropEncode({scene, frame, zh}) {
  const encode = across(frame, atCue(scene, 1, .19, .13), atCue(scene, 1, .83, .29));
  const vector = across(frame, atCue(scene, 1, .51, .24), atCue(scene, 2, .17, .38));
  const locate = across(frame, atCue(scene, 2, .48, .44), atCue(scene, 2, .88, .59));
  const shift = across(frame, atCue(scene, 3, .1, .64), atCue(scene, 4, .62, .87));
  const poseX = 186 + 171 * shift;

  return (
    <section className="pim-cliff-sequence pim-cliff-crop">
      <svg className="pim-cliff-diagram" viewBox="0 0 1680 520" role="img"
        aria-label={label(zh, '从裁剪图编码出图像特征的示意图', 'Encoding image features from the crop')}>
        <defs>
          <pattern id="cliff-crop-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0H0V40" fill="none" stroke="var(--line)" strokeWidth="1.3" />
          </pattern>
          <clipPath id="cliff-crop-window"><rect x="0" y="73" width="497" height="357" rx="18" /></clipPath>
        </defs>
        <g clipPath="url(#cliff-crop-window)">
          <rect x="0" y="73" width="497" height="357" fill="var(--surface)" />
          <rect x="0" y="73" width="497" height="357" fill="url(#cliff-crop-grid)" />
          <circle cx="408" cy="145" r="70" fill="var(--accentPale)" />
          <path d="M-65 420 112 235 198 331 331 185 550 410V440H-65Z" fill="var(--accentPale)" />
          <path d="M-65 420 150 334 259 370 368 260 548 412V440H-65Z" fill="var(--accent)" opacity=".17" />
          <path d="M0 252H497M248.5 73V430" stroke="var(--muted)" strokeWidth="2" strokeDasharray="8 11" opacity={.68 * locate} />
          <Silhouette x={poseX} y={252} scale={1.05} />
          <rect x={poseX - 123} y="128" width="246" height="246" fill="none" stroke="var(--accent)" strokeWidth="4" rx="8" />
          <path d="M0 0h34M0 0v34M246 0h-34M246 0v34M0 246h34M0 246v-34M246 246h-34M246 246v-34"
            transform={'translate(' + (poseX - 123) + ' 128)'} fill="none" stroke="var(--warm)" strokeWidth="6" />
          <g opacity={locate}>
            <circle cx="248.5" cy="252" r="6" fill="var(--muted)" />
            <path d={'M248.5 252H' + poseX} stroke="var(--warm)" strokeWidth="4" strokeDasharray="5 10" />
            <circle cx={poseX} cy="252" r="8" fill="var(--warm)" />
          </g>
        </g>
        <rect x="0" y="73" width="497" height="357" fill="none" stroke="var(--line)" strokeWidth="2" rx="18" />
        <text className="pim-cliff-svg-label" x="248" y="479" textAnchor="middle">
          {label(zh, '原图与 224 × 224 裁剪', 'Full frame and 224 × 224 crop')}
        </text>

        <path d="M497 252H601M1011 252H1110" fill="none" stroke="var(--accent)" strokeOpacity={.18 + .55 * encode}
          strokeWidth="3" strokeDasharray="9 9" />
        <circle cx={mix(497, 601, encode)} cy="252" r="7" fill="var(--warm)" opacity={encode * (1 - locate * .65)} />

        <g opacity={.15 + .85 * encode}>
          {[0, 1, 2, 3].map(layer => (
            <g key={layer}
              transform={'translate(' + (600 + 63 * layer * encode) + ' ' + (163 + 10 * layer) + ') skewY(-12)'}>
              <rect width="213" height="155" rx="9" fill="var(--surface)" stroke="var(--accent)" strokeWidth="3" />
              {ACTIVATIONS.slice(0, 48).map((strength, index) => (
                <rect key={index} x={12 + index % 8 * 24} y={10 + Math.floor(index / 8) * 23}
                  width="20" height="19" rx="2" fill={(index + layer) % 8 === 0 ? 'var(--warm)' : 'var(--accent)'}
                  opacity={strength * (.76 + .23 * Math.sin(frame / 18 + layer + index) * (1 - locate))} />
              ))}
            </g>
          ))}
        </g>
        <text className="pim-cliff-svg-label" x="797" y="479" textAnchor="middle" opacity={.4 + .6 * encode}>ResNet</text>

        <g transform="translate(1110 155)">
          <text className="pim-cliff-svg-label" x="0" y="0" opacity={.4 + .6 * vector}>
            {label(zh, '图像特征向量', 'Image feature vector')}
          </text>
          <rect y="26" width="561" height="160" rx="12" fill="var(--surface)" stroke="var(--line)" strokeWidth="2" />
          {ACTIVATIONS.map((strength, index) => (
            <rect key={index} x={14 + index % 24 * 22.4} y={39 + Math.floor(index / 24) * 47} width="19" height="42" rx="2"
              fill={index % 11 === 0 ? 'var(--warm)' : 'var(--accent)'}
              opacity={.11 + strength * clamp(vector * 1.45 - index % 24 / 48)} />
          ))}
          <g transform={'translate(0 ' + (235 + 12 * (1 - locate)) + ')'} opacity={locate}>
            <text className="pim-cliff-svg-note" y="0">{label(zh, '保留外观、姿态和形状线索', 'Appearance, pose and shape cues')}</text>
            <text className="pim-cliff-svg-note pim-cliff-warm" y="49">
              {label(zh, '画面中的位置没有进入向量', 'Position in the full frame is missing')}
            </text>
          </g>
        </g>
      </svg>
      <Schematic zh={zh} />
    </section>
  );
}

function RegressionBranches({scene, frame, zh}) {
  const input = across(frame, atCue(scene, 1, 0, .05), atCue(scene, 1, .26, .16));
  const body = across(frame, atCue(scene, 1, .30, .19), atCue(scene, 1, .59, .27));
  const camera = across(frame, atCue(scene, 1, .61, .29), atCue(scene, 1, .94, .38));
  const joints = across(frame, atCue(scene, 2, 0, .39), atCue(scene, 2, .62, .51));
  const reframe = across(frame, atCue(scene, 3, 0, .58), atCue(scene, 3, .7, .67));
  const backToInput = across(frame, atCue(scene, 4, 0, .73), atCue(scene, 4, .65, .91));
  const points = POSE.map(([x, y, z]) => [x * (1 - .24 * reframe) + z * .58 * reframe, y + z * .06 * reframe]);

  return (
    <section className="pim-cliff-sequence pim-cliff-regression">
      <div className="pim-cliff-reg-input" style={{transform: 'scale(' + (1 + .08 * backToInput) + ')'}}>
        <div className="pim-cliff-feature-strip">
          {ACTIVATIONS.slice(0, 13).map((strength, index) => (
            <i key={index} style={{background: 'var(--accent)', opacity: strength}} />
          ))}
          <b>{label(zh, '图像特征', 'Image features')}</b>
        </div>
        <span className="pim-cliff-join" aria-hidden="true">+</span>
        <div className="pim-cliff-feature-strip is-geometry">
          <b>{label(zh, '边界框信息', 'Box information')}</b>
          <MathLabel value={'I_{\\mathrm{bbox}}'} />
        </div>
      </div>
      <svg className="pim-cliff-fork" viewBox="0 0 1680 504" aria-hidden="true">
        <path d="M840 0V177" stroke="var(--line)" strokeWidth="4" fill="none" />
        <path d="M840 0V177" stroke="var(--accent)" strokeWidth="4" fill="none" pathLength="1"
          strokeDasharray={input + ' 1'} />
        <path d="M840 120V177C840 252 590 213 447 290" stroke="var(--accent)" strokeWidth="4"
          fill="none" opacity={.33 + .67 * body} pathLength="1" strokeDasharray={body + ' 1'} />
        <path d="M840 120V177C840 252 1090 213 1233 290" stroke="var(--warm)" strokeWidth="4"
          fill="none" opacity={.33 + .67 * camera} pathLength="1" strokeDasharray={camera + ' 1'} />
        <circle cx="447" cy="290" r="8" fill="var(--accent)" opacity={body} />
        <circle cx="1233" cy="290" r="8" fill="var(--warm)" opacity={camera} />
      </svg>
      <div className="pim-cliff-regressor" style={{opacity: .36 + .64 * input}}>{label(zh, '回归器', 'Regressor')}</div>

      <div className="pim-cliff-pose-branch" style={{opacity: (.17 + .83 * body) * (1 - .23 * backToInput), transform: 'translateY(' + 29 * (1 - body) + 'px)'}}>
        <svg viewBox="0 0 330 290" aria-hidden="true">
          <path d="M7 238 96 186H322L231 238H7ZM7 238H231V248H7ZM231 238 322 186V196L231 248"
            fill="var(--accentPale)" stroke="var(--line)" strokeWidth="2" />
          <g transform="translate(163 135)">
            <ellipse cx="0" cy="101" rx="71" ry="13" fill="var(--shade)" />
            <g opacity={1 - .83 * joints}><Silhouette x={0} y={0} /></g>
            <Skeleton points={points} opacity={joints} />
          </g>
          <rect x="48" y="8" width="233" height="247" rx="12" fill="none" stroke="var(--warm)"
            strokeWidth="2.5" strokeDasharray="7 8" opacity={joints * (.83 - .44 * reframe)} />
        </svg>
        <div className="pim-cliff-branch-label">
          <strong>{label(zh, '人体参数', 'Body parameters')}</strong>
          <span><MathLabel value={'\\theta,\\ \\beta'} /><span className="pim-cliff-branch-muted">
            {label(zh, '姿态与形状', 'Pose and shape')}
          </span></span>
          <span style={{opacity: joints}}><MathLabel value={'J_{\\mathrm{3D}}'} /><span className="pim-cliff-branch-muted">
            {label(zh, '仍在裁剪坐标系', 'Crop coordinates')}
          </span></span>
        </div>
      </div>

      <div className="pim-cliff-camera-branch" style={{opacity: (.17 + .83 * camera) * (1 - .23 * backToInput), transform: 'translateY(' + 29 * (1 - camera) + 'px)'}}>
        <div className="pim-cliff-branch-label">
          <strong>{label(zh, '投影参数', 'Projection parameters')}</strong>
          <span><MathLabel value={'s,\\ t_x,\\ t_y'} /></span>
          <span className="pim-cliff-branch-muted">{label(zh, '缩放与平移', 'Scale and translation')}</span>
        </div>
        <svg viewBox="0 0 330 290" aria-hidden="true">
          <path d="M67 230V77L244 39V191ZM67 77 91 97 274 55 244 39M244 191l30 20V55"
            fill="var(--accentPale)" stroke="var(--accent)" strokeWidth="3" />
          <path d="M67 160 244 121M167 57v150" stroke="var(--line)" strokeWidth="2" strokeDasharray="6 6" />
          <path d={'M167 151H' + (167 + 56 * reframe) + 'V' + (151 - 45 * reframe)} fill="none" stroke="var(--warm)" strokeWidth="3" />
          <circle cx={167 + 56 * reframe} cy={151 - 45 * reframe} r="10" fill="var(--warm)" />
          <rect x="100" y="105" width={93 + 32 * reframe} height={82 + 29 * reframe} rx="4"
            fill="none" stroke="var(--warm)" strokeWidth="3" />
        </svg>
      </div>
      <Schematic zh={zh} />
    </section>
  );
}

const RAY_POINTS = [0, 6, 7, 8, 13, 14];
const JOINT_OFFSETS = [
  [6, 6], [-1, 6], [-4, 3], [8, 1], [-14, -12], [15, 0], [-14, -19], [25, -12],
  [0, 0], [-5, 6], [5, 5], [12, 9], [-14, -12], [-10, 16], [17, 15],
];

function Camera({x, y, opacity = 1}) {
  return (
    <g transform={'translate(' + x + ' ' + y + ')'} opacity={opacity}>
      <path d="M-23-13H5L21-7V11L5 17H-23ZM-15-13V-22H4V-13M21-7 39-19V24L21 11"
        fill="var(--surface)" stroke="var(--accent)" strokeWidth="3.5" strokeLinejoin="round" />
      <circle cx="39" cy="2" r="5" fill="var(--warm)" />
    </g>
  );
}

const WEIGHTED_TERMS = [
  '\\lambda_{\\mathrm{SMPL}}\\mathcal L_{\\mathrm{SMPL}}',
  '\\lambda_{\\mathrm{3D}}\\mathcal L_{\\mathrm{3D}}',
  '\\lambda_{\\mathrm{2D}}\\mathcal L_{\\mathrm{2D}}^{\\mathrm{full}}',
];

function Reprojection({scene, frame, zh}) {
  const projectionStart = atCue(scene, 1, 0, .09);
  const project = across(frame, projectionStart, atCue(scene, 1, .78, .28));
  const compare = across(frame, atCue(scene, 2, 0, .34), atCue(scene, 2, .34, .43));
  const rotationCue = scene.cues?.find(cue => /全局旋转|global rotation|perspective distortion/i.test(cue.text));
  const lossCue = scene.cues?.find(cue => /总损失|组合损失|total loss|combined loss|weighted sum/i.test(cue.text));
  const rotationStart = rotationCue?.start_frame ?? atCue(scene, 3, .1, .58);
  const lossStart = lossCue?.start_frame ?? Math.max(rotationStart + 1, atCue(scene, 4, 0, .87));
  const lossEnd = lossCue?.end_frame ?? scene.duration_frames;
  const rotation = across(frame, rotationStart, Math.min(lossStart, rotationCue?.end_frame ?? lossStart));
  const residualStart = atCue(scene, 2, .22, .40);
  const residualEnd = Math.max(residualStart + 1, rotationStart + .34 *
    Math.max(0, Math.min(lossStart, (rotationCue?.end_frame ?? lossStart)) - rotationStart));
  const residual = across(frame, residualStart, residualEnd);
  const inspect = compare * (1 - across(frame, rotationStart, lossStart));
  const combine = clamp((frame - lossStart) / Math.max(1, lossEnd - lossStart));
  const origin = [113, 239];
  const rotateJoint = ([x, y, z], angle) => [
    Math.cos(angle) * x + Math.sin(angle) * z,
    y,
    Math.cos(angle) * z - Math.sin(angle) * x,
  ];
  const world = POSE.map(point => {
    const [x, y, z] = rotateJoint(point, .70 * rotation);
    return [x, y - 18 * (1 - rotation), 523 + z];
  });
  const cameraView = ([x, y, z]) => [origin[0] + .58 * x + z, origin[1] + y - .18 * x];
  const body = world.map(cameraView);
  const projected = world.map(([x, y, z]) => cameraView([x * 287 / z, y * 287 / z, 287]));
  const fullFrame = ([x, y, z]) => [1330 + x * 634 / z, 227 + y * 634 / z];
  const predicted = world.map(fullFrame);
  const target = POSE.map((point, index) => {
    const [x, y, z] = rotateJoint(point, .70);
    const [imageX, imageY] = fullFrame([x, y, 523 + z]);
    return [imageX + JOINT_OFFSETS[index][0] * .28, imageY + JOINT_OFFSETS[index][1] * .28];
  });
  const focus = Math.min(2, Math.floor(combine * WEIGHTED_TERMS.length));

  return (
    <section className="pim-cliff-sequence pim-cliff-reprojection">
      <svg className="pim-cliff-diagram" viewBox="0 0 1680 450" role="img"
        aria-label={label(zh, '3D 关节投影到全帧并和真实关键点对比', 'Projecting 3D joints into the full frame and comparing with target keypoints')}>
        <defs>
          <pattern id="cliff-project-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0H0V40" fill="none" stroke="var(--line)" strokeWidth="1.1" />
          </pattern>
        </defs>
        <g opacity={1 - .33 * compare + .2 * rotation}>
          <path d="M56 332 232 359 404 333 580 367 787 337 640 291 343 300Z"
            fill="var(--accentPale)" stroke="var(--line)" strokeWidth="2" />
          <path d="M56 332 640 291M232 359 730 319M404 333l176 34M113 326l123 33M310 314l113 42"
            fill="none" stroke="var(--line)" strokeWidth="2" />
          <text x="634" y="35" textAnchor="middle" className="pim-cliff-svg-label">{label(zh, '3D 关节', '3D joints')}</text>
          <Skeleton points={body} width={5} />
          <path d="M355 123 445 95 445 341 355 369Z" fill="var(--accentPale)" opacity={.31 + .36 * project} />
          <path d="M355 123 445 95 445 341 355 369ZM355 185l90-28M355 247l90-28M355 308l90-28M400 109v246"
            fill="none" stroke="var(--line)" strokeWidth="2" />
          {RAY_POINTS.map(index => (
            <g key={index} opacity={.73 * project}>
              <line x1={origin[0]} y1={origin[1]} x2={body[index][0]} y2={body[index][1]} stroke="var(--warm)"
                strokeWidth="2.3" strokeDasharray="6 6" />
              <circle cx={mix(body[index][0], projected[index][0], project)} cy={mix(body[index][1], projected[index][1], project)}
                r="5.2" fill="var(--warm)" />
            </g>
          ))}
          <Skeleton points={projected} opacity={project * .86} width={3} />
          <Camera x={74} y={237} opacity={.47 + project * .53} />
          <text x="104" y="413" textAnchor="middle" className="pim-cliff-svg-note">{label(zh, '原始相机', 'Full-frame camera')}</text>
          <text x="409" y="413" textAnchor="middle" className="pim-cliff-svg-note">{label(zh, '成像平面', 'Image plane')}</text>
        </g>

        <path d="M784 213h151m-16-12 16 12-16 12" fill="none" stroke="var(--accent)" strokeWidth="3"
          opacity={.18 + .82 * project} strokeDasharray="8 7" />
        <g opacity={.28 + .72 * project}>
          <rect x="976" y="18" width="687" height="388" fill="var(--surface)" rx="16" />
          <rect x="976" y="18" width="687" height="388" fill="url(#cliff-project-grid)" stroke="var(--line)" strokeWidth="2" rx="16" />
          <path d="M1300 178h60m-30-30v60" stroke="var(--line)" strokeWidth="2.5" />
          <text x="1012" y="64" className="pim-cliff-svg-label">{label(zh, '完整图像', 'Full image')}</text>
          <g transform={`translate(1330 227) scale(${1 + .22 * inspect}) translate(-1330 -227)`}>
            <Skeleton points={predicted} opacity={project} width={5} />
            <Skeleton points={target} color="var(--warm)" opacity={.26 * compare} width={3} dots={false} />
            {target.map(([x, y], index) => (
              <circle key={index} cx={x} cy={y} r="6" fill="var(--surface)" stroke="var(--warm)"
                strokeWidth="3" opacity={compare} />
            ))}
            {RAY_POINTS.map((index, order) => {
              const amount = clamp(residual * 1.45 - order * .08);
              return <line key={index} x1={predicted[index][0]} y1={predicted[index][1]}
                x2={mix(predicted[index][0], target[index][0], amount)}
                y2={mix(predicted[index][1], target[index][1], amount)}
                stroke="var(--warm)" strokeWidth="4" strokeLinecap="round" opacity={amount} />;
            })}
          </g>
          <line x1="1009" y1="372" x2="1043" y2="372" stroke="var(--accent)" strokeWidth="4" opacity={project} />
          <text x="1053" y="381" className="pim-cliff-svg-note" opacity={project}>{label(zh, '投影关键点', 'Projected joints')}</text>
          <circle cx="1403" cy="372" r="7" fill="var(--surface)" stroke="var(--warm)" strokeWidth="3" opacity={compare} />
          <text x="1424" y="381" className="pim-cliff-svg-note" opacity={compare}>{label(zh, '真实关键点', 'Target keypoints')}</text>
        </g>
      </svg>
      <div className="pim-cliff-projection-math" style={{opacity: project}}>
        {frame < lossStart ? (
          <div className="pim-cliff-projection-calculation">
            <MathLabel value={'J_{\\mathrm{2D}}^{\\mathrm{full}} = \\Pi_{\\mathrm{full}}\\bigl(J_{\\mathrm{3D}} + t^{\\mathrm{full}}\\bigr)'} />
            <span className="pim-cliff-loss-detail" style={{opacity: residual}}>
              <MathLabel value={'\\mathcal L_{\\mathrm{2D}}^{\\mathrm{full}} = \\bigl\\|J_{\\mathrm{2D}}^{\\mathrm{full}} - J_{\\mathrm{2D}}^{\\mathrm{gt}}\\bigr\\|_2'} />
            </span>
          </div>
        ) : (
          <div className="pim-cliff-weighted">
            <MathLabel value={'\\mathcal L^{\\mathrm{CLIFF}} ='} />
            {WEIGHTED_TERMS.map((term, index) => (
              <React.Fragment key={term}>
                {index > 0 && <span aria-hidden="true">+</span>}
                <span className={'pim-cliff-loss-term' + (index === focus ? ' is-focused' : '')}
                  style={{opacity: index <= focus ? 1 : .38 + .62 * combine}}><MathLabel value={term} /></span>
              </React.Fragment>
            ))}
          </div>
        )}
      </div>
      <Schematic zh={zh} />
    </section>
  );
}

function BoxFusion({scene, frame, zh}) {
  const measure = across(frame, atCue(scene, 1, 0, .10), atCue(scene, 1, .43, .31));
  const fuse = across(frame, atCue(scene, 1, .52, .34), atCue(scene, 1, .98, .56));
  const angles = across(frame, atCue(scene, 2, 0, .57), atCue(scene, 2, .76, .88));
  const x = 647 + 106 * angles;
  const y = 211 - 33 * angles;

  return (
    <section className="pim-cliff-sequence pim-cliff-box-fusion">
      <svg viewBox="0 0 856 539" role="img" aria-label={label(zh, '边界框中心偏移和宽度', 'Box center offsets and width')}>
        <rect x="13" y="35" width="829" height="435" rx="11" fill="var(--surface)" stroke="var(--line)" strokeWidth="2" />
        <path d="M14 419 216 292 379 350 521 201 843 432V470H14Z" fill="var(--accentPale)" opacity=".75" />
        <path d="M13 251H841M415 35V470" fill="none" stroke="var(--line)" strokeWidth="2.5" strokeDasharray="9 11" />
        <circle cx="415" cy="251" r="7" fill="var(--muted)" />
        <Silhouette x={x} y={y} scale={.62} />
        <rect x={x - 75} y={y - 80} width="150" height="150" fill="none" stroke="var(--accent)" strokeWidth="4" rx="5" />
        <g opacity={measure}>
          <path d={'M415 251H' + x + 'V' + y} fill="none" stroke="var(--warm)" strokeWidth="3.5" strokeDasharray="8 7" />
          <path d={'M' + (x - 75) + ' ' + (y + 105) + 'h150m-150-9v18m150-18v18'} fill="none" stroke="var(--accent)" strokeWidth="3" />
          <circle cx={x} cy={y} r="8" fill="var(--warm)" />
          <text className="pim-cliff-coordinate" x={(415 + x) / 2} y="284" textAnchor="middle">c<tspan dy="8" fontSize="21">x</tspan></text>
          <text className="pim-cliff-coordinate" x={x + 17} y={(251 + y) / 2}>c<tspan dy="8" fontSize="21">y</tspan></text>
          <text className="pim-cliff-coordinate" x={x} y={y + 145} textAnchor="middle">b</text>
        </g>
        <text x="412" y="517" className="pim-cliff-svg-note" textAnchor="middle">
          {label(zh, '在原图上量出中心偏移与框宽', 'Measure center offsets and box width in the full image')}
        </text>
      </svg>

      <div className="pim-cliff-fusion-detail">
        <div className="pim-cliff-fusion-formula" style={{opacity: .19 + .81 * measure}}>
          <MathLabel value={'I_{\\mathrm{bbox}} = \\left[\\frac{c_x}{f_{\\mathrm{CLIFF}}},\\ \\frac{c_y}{f_{\\mathrm{CLIFF}}},\\ \\frac{b}{f_{\\mathrm{CLIFF}}}\\right]'} />
        </div>
        <div className="pim-cliff-fusion-vector">
          <span className="pim-cliff-fusion-appearance">
            {ACTIVATIONS.slice(0, 11).map((intensity, index) => <i key={index} style={{opacity: intensity}} />)}
          </span>
          <span className="pim-cliff-fusion-geometry" style={{opacity: fuse, translate: (1 - fuse) * 35 + 'px -' + (1 - fuse) * 22 + 'px'}}>
            <i /><i /><i />
          </span>
        </div>
        <div className="pim-cliff-fusion-legend">
          <span>{label(zh, '图像特征', 'Image features')}</span>
          <span style={{opacity: fuse}}>{label(zh, '拼接边界框信息', 'Append box information')}</span>
        </div>
        <div className="pim-cliff-fusion-angles" style={{opacity: angles, transform: 'translateY(' + (1 - angles) * 22 + 'px)'}}>
          <span>{label(zh, '中心偏移对应观察角度', 'Center offsets encode viewing angles')}</span>
          <MathLabel value={'c_x/f_{\\mathrm{CLIFF}} = \\tan\\gamma_X,\\quad c_y/f_{\\mathrm{CLIFF}} = \\tan\\gamma_Y'} />
        </div>
      </div>
      <Schematic zh={zh} />
    </section>
  );
}

const TRANSLATION_TERMS = [
  't_X^{\\mathrm{full}} = t_X^{\\mathrm{crop}} + \\frac{2c_x}{bs}',
  't_Y^{\\mathrm{full}} = t_Y^{\\mathrm{crop}} + \\frac{2c_y}{bs}',
  't_Z^{\\mathrm{full}} = t_Z^{\\mathrm{crop}}\\cdot\\frac{f_{\\mathrm{CLIFF}}}{f_{\\mathrm{HMR}}}\\cdot\\frac{r}{b}',
];

function TranslateFull({scene, frame, zh}) {
  const shift = across(frame, atCue(scene, 1, .22, .14), atCue(scene, 1, .83, .44));
  const depth = across(frame, atCue(scene, 2, 0, .49), atCue(scene, 2, .84, .64));
  const reveal = across(frame, atCue(scene, 3, 0, .68), atCue(scene, 4, .62, .85));
  const baselineReveal = across(frame, atCue(scene, 4, 0, .80), atCue(scene, 4, .82, .88));
  const finalFocus = across(frame, atCue(scene, 5, 0, .88), atCue(scene, 5, .84, .98));
  const example = scene.example;
  const demo = example?.checkpoints?.some(checkpoint => checkpoint.passed) &&
    Array.isArray(example.baseline) && Array.isArray(example.output) &&
    [...example.baseline, ...example.output].every(Number.isFinite) &&
    example.baseline.length === 2 && example.output.length === 2;
  const displayVector = values => '[' + values.map(value => Number(value.toPrecision(4))).join(', ') + ']';
  const cx = 621 + 315 * shift + 25 * depth;
  const cy = 263 - 82 * shift + 28 * depth;
  const initialSize = 158;
  const size = initialSize * (1 - .26 * depth);
  const points = POSE.map(([x, y]) => [cx + (x * size / 237), cy + (y * size / 237)]);

  return (
    <section className="pim-cliff-sequence pim-cliff-translation">
      <div className="pim-cliff-translation-equations">
        {TRANSLATION_TERMS.map((value, index) => {
          const amount = index < 2 ? shift : depth;
          const active = index === 2 ? depth : shift * (1 - depth);
          return (
            <div key={value} style={{opacity: .33 + .67 * amount, borderColor: active > .2 ? 'var(--warm)' : 'var(--line)'}}>
              <MathLabel value={value} />
            </div>
          );
        })}
      </div>
      <svg className="pim-cliff-diagram" viewBox="0 0 1680 416" role="img"
        aria-label={label(zh, '将人体根节点从裁剪坐标系转换到原始相机坐标系', 'Transforming the root translation into full-camera coordinates')}>
        <path d="M307 336 576 166H1518L1249 336Z" fill="var(--accentPale)" stroke="var(--line)" strokeWidth="2.5" />
        <path d="M372 295H1315M437 254H1380M502 213H1444M548 336 818 166M777 336 1047 166M1011 336 1281 166"
          stroke="var(--line)" strokeWidth="2" fill="none" />
        <g opacity={.89 - .63 * reveal}>
          <rect x="527" y="148" width="189" height="194" rx="10" fill="var(--surface)" fillOpacity=".76"
            stroke="var(--warm)" strokeWidth="3" strokeDasharray="7 8" />
          <Silhouette x={621} y={263} scale={.61} color="var(--warm)" />
          <text className="pim-cliff-svg-note" x="621" y="394" textAnchor="middle">{label(zh, '裁剪虚拟相机', 'Virtual crop camera')}</text>
        </g>
        <g opacity={.30 + .70 * shift}>
          <path d={'M621 263H' + cx + 'V' + cy} fill="none" stroke="var(--warm)" strokeWidth="3" strokeDasharray="8 8" />
          <path d="M307 336H155M307 336V222M307 336 414 267" fill="none" stroke="var(--accent)" strokeWidth="3" />
          <text className="pim-cliff-coordinate" x="124" y="346">X</text>
          <text className="pim-cliff-coordinate" x="294" y="209">Y</text>
          <text className="pim-cliff-coordinate" x="428" y="264">Z</text>
          <rect x="757" y="49" width="521" height="289" rx="15" fill="var(--surface)" fillOpacity={.09 + .41 * reveal}
            stroke="var(--accent)" strokeWidth={2 + 2 * reveal + finalFocus} />
          <Skeleton points={points} width={5} />
          <circle cx={cx} cy={points[8][1]} r={7 + 2 * finalFocus} fill="var(--warm)" />
          <text className="pim-cliff-svg-note" x="1017" y="394" textAnchor="middle">{label(zh, '原始相机坐标系', 'Full-camera coordinates')}</text>
        </g>
        <g opacity={.36 + .64 * reveal}>
          <Camera x={131} y={130} />
          <path d="M170 132 757 49m-587 83 587 206" fill="none" stroke="var(--accent)"
            strokeWidth="2" strokeDasharray="7 10" />
        </g>
        {demo && <g transform="translate(1311 50)" opacity={baselineReveal}>
          <rect width="348" height="224" rx="11" fill="var(--surface)" stroke="var(--line)" strokeWidth="2" />
          <text className="pim-cliff-svg-note" x="17" y="40">{label(zh, '演算示例输出', 'Toy example outputs')}</text>
          <path d="M17 59h312" stroke="var(--line)" strokeWidth="2" />
          <text className="pim-cliff-svg-note" x="17" y="100">{label(zh, '基线', 'Baseline')}</text>
          <text className="pim-cliff-svg-label" x="329" y="100" textAnchor="end">{displayVector(example.baseline)}</text>
          <g opacity={finalFocus}>
            <text className="pim-cliff-svg-note" x="17" y="173">{label(zh, '改进方法', 'Proposed method')}</text>
            <text className="pim-cliff-svg-label pim-cliff-warm" x="329" y="173" textAnchor="end">{displayVector(example.output)}</text>
          </g>
        </g>}
      </svg>
      <Schematic zh={zh} />
    </section>
  );
}

export const CLIFF_SCENES = {
  'crop-encode': CropEncode,
  'box-fusion': BoxFusion,
  'translate-full': TranslateFull,
  'parameter-branches': RegressionBranches,
  reprojection: Reprojection,
};

export function CliffSequence({variant, scene, frame, zh}) {
  const Component = CLIFF_SCENES[variant];
  return Component ? <Component scene={scene} frame={frame} zh={zh} /> : null;
}
