import React, {useMemo} from 'react';
import {formatCaptionMath} from './math-format.mjs';
import './worked-sequence.css';

const number = value => Number(value.toPrecision(5)).toString();
const reveal = (frame, start) => 1 - (1 - Math.min(1, Math.max(0, (frame - start + 1) / 18))) ** 3;

export function canAnimateWorkedSequence(states) {
  return states.length >= 2 && states.length <= 8 && states.every(({label, values}) =>
    typeof label === 'string' && label.trim() && values.length >= 1 &&
    values.length <= 3 && values.every(Number.isFinite));
}

function StateLabel({name}) {
  const parts = useMemo(() => formatCaptionMath(name), [name]);
  return parts.map(({text, html}, index) => html
    ? <span key={index} dangerouslySetInnerHTML={{__html: html}} />
    : <React.Fragment key={index}>{text}</React.Fragment>);
}

function Values({values}) {
  return values.length === 1 ? number(values[0]) : `[${values.map(number).join(', ')}]`;
}

export function WorkedSequence({states, intro, frame, zh}) {
  const active = states.findLastIndex(state => state.start <= frame);
  const current = states[active] ?? intro.findLast(beat => beat.start <= frame);
  const progress = current ? reveal(frame, current.start) : 0;
  return (
    <section className="pim-worked-sequence" aria-label={zh ? '计算示例' : 'Worked example'}>
      <div className="pim-worked-focus">
        <div className="pim-worked-kicker">{zh ? '计算示例' : 'Worked example'}</div>
        {current && <div className="pim-worked-result"
          style={{opacity: progress, transform: `translateY(${(1 - progress) * 26}px)`}}>
          <div className="pim-worked-focus-label"><StateLabel name={current.label.slice(0, 96)} /></div>
          {current.values && <div className={'pim-worked-focus-value' + (current.values.length > 1 ? ' is-vector' : '')}>
            <Values values={current.values} />
          </div>}
        </div>}
      </div>
      <ol className={'pim-worked-steps' + (states.length > 5 ? ' is-dense' : '')}>
        {states.map(({values, label, start}, index) => {
          const shown = reveal(frame, start);
          return (
            <li className={'pim-worked-row' + (index === active ? ' is-active' : '')} key={index}>
              <span className="pim-worked-node" style={{'--shown': shown}} aria-hidden="true" />
              <span className="pim-worked-state" style={{opacity: .64 + .36 * shown}}>
                <StateLabel name={label.slice(0, 64)} />
              </span>
              <span className="pim-worked-value"
                style={{opacity: shown, transform: `translateX(${(1 - shown) * 28}px)`}}>
                <Values values={values} />
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
