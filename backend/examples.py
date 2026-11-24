"""Finite, shape-checked numerical examples. No generated code is executed."""
import numpy as np


def array(value, ndim, name):
    try:
        result = np.asarray(value, dtype=np.float64)
    except (ValueError, TypeError):
        raise ValueError(f'{name} 必须是数值数组。') from None
    if result.ndim != ndim or any(d < 1 or d > 12 for d in result.shape) or not np.isfinite(result).all() or np.abs(result).max() > 1e6:
        raise ValueError(f'{name} 的维度或数值无效（每维 1–12，有限数值且绝对值不超过 1e6）。')
    return result


def execute_example(plan):
    if not isinstance(plan, dict):
        raise ValueError('示例计划必须是对象。')
    kind = plan.get('kind')
    with np.errstate(over='raise', invalid='raise'):
        if kind == 'low_rank':
            W = array(plan.get('W0', plan.get('base')), 2, 'W0')
            A, B = array(plan.get('A'), 2, 'A'), array(plan.get('B'), 2, 'B')
            x = array(plan.get('x', plan.get('input')), 1, 'x')
            if W.shape[1] != len(x) or A.shape[1] != len(x) or B.shape != (W.shape[0], A.shape[0]):
                raise ValueError('W0、A、B、x 的矩阵维度不匹配。')
            scale = float(plan.get('scale', 1))
            if not np.isfinite(scale) or abs(scale) > 100:
                raise ValueError('示例 scale 无效。')
            baseline, hidden = W @ x, A @ x
            delta = scale * (B @ hidden)
            output = baseline + delta
            result = checked(kind, baseline, output, [sum(float(w)*float(xj) for w,xj in zip(row, x)) + scale*sum(float(b)*sum(float(a)*float(xj) for a,xj in zip(arow, x)) for b,arow in zip(brow, A)) for row,brow in zip(W,B)], [('W₀x', baseline), ('Ax', hidden), ('Δy', delta), ('y', output)])
            return {**result, 'base': W.tolist(), 'A': A.tolist(), 'B': B.tolist(), 'input': x.tolist(), 'scale': scale, 'baseline': baseline.tolist(), 'hidden': hidden.tolist(), 'delta': delta.tolist(), 'output': output.tolist(), 'params': {'frozen': int(W.size), 'adapter': int(A.size + B.size), 'rank': A.shape[0]}, 'steps': [{'formula': 'y₀ = W₀x', 'result': baseline.tolist()}, {'formula': 'h = Ax', 'result': hidden.tolist()}, {'formula': 'Δy = scale × Bh', 'result': delta.tolist()}, {'formula': 'y = y₀ + Δy', 'result': output.tolist()}], 'scope': 'Illustrative toy inputs, not paper experimental data.'}
        if kind == 'scaled_dot_attention':
            Q, K, V = (array(plan.get(key), 2, key) for key in ('Q', 'K', 'V'))
            if Q.shape[1] != K.shape[1] or K.shape[0] != V.shape[0]:
                raise ValueError('Q、K、V 的矩阵维度不匹配。')
            scores = Q @ K.T / np.sqrt(Q.shape[1])
            weights = np.exp(scores - scores.max(axis=-1, keepdims=True))
            weights /= weights.sum(axis=-1, keepdims=True)
            output = weights @ V
            reference = [[sum(float(weight)*float(value) for weight,value in zip(row, column)) for column in V.T] for row in weights]
            baseline = np.repeat(V.mean(axis=0, keepdims=True), Q.shape[0], axis=0)
            result = checked(kind, baseline, output, reference, [('QKᵀ / √d', scores), ('softmax', weights), ('uniform', baseline), ('output', output)])
            return {**result, 'Q': Q.tolist(), 'K': K.tolist(), 'V': V.tolist(), 'scores': scores.tolist(), 'weights': weights.tolist(), 'output': output.tolist(), 'steps': [{'formula': 'scores = QKᵀ / √d', 'result': scores.tolist()}, {'formula': 'weights = softmax(scores)', 'result': weights.tolist()}, {'formula': 'output = weights × V', 'result': output.tolist()}], 'scope': 'Illustrative toy inputs, not paper experimental data.'}
        if kind == 'cliff_geometry':
            center = array(plan.get('center_offset'), 1, 'center_offset')
            feature = array(plan.get('appearance'), 1, 'appearance')
            head = array(plan.get('head'), 2, 'head')
            box, focal = (float(plan[key]) for key in ('box_size', 'focal_length'))
            if len(center) != 2 or not 0 < box <= 1e6 or not 0 < focal <= 1e6 or head.shape[1] != len(feature) + 3:
                raise ValueError('Invalid CLIFF inputs or prediction head shape.')
            geometry = np.r_[center, box] / focal
            cropped = np.r_[feature, [0., 0., 0.]]
            global_input = np.r_[feature, geometry]
            baseline, output = head @ cropped, head @ global_input
            independent = [sum(float(x)*float(y) for x, y in zip(row, global_input)) for row in head]
            return checked(kind, baseline, output, independent, [('v', feature), ('g', geometry),
                           ('[v; g]', global_input), ('prediction', output)])
        if kind == 'linear_regression':
            coefficients = array(plan.get('baseline_weights'), 1, 'baseline_weights')
            proposed = array(plan.get('proposed_weights'), 1, 'proposed_weights')
            x = array(plan.get('x'), 1, 'x')
            if coefficients.shape != x.shape or proposed.shape != x.shape:
                raise ValueError('Regression weights and features must have the same shape.')
            adjusted = proposed*x
            baseline, output = [coefficients @ x], [proposed @ x]
            independent = [sum(map(float, adjusted))]
            return checked(kind, baseline, output, independent, [('x', x), ('w₁ ⊙ x', adjusted),
                           ('baseline', baseline), ('prediction', output)])
        if kind == 'gradient_momentum':
            gradient = array(plan.get('gradient'), 1, 'gradient')
            weights = array(plan.get('weights'), 1, 'weights')
            velocity = array(plan.get('velocity'), 1, 'velocity')
            rate, momentum = (float(plan[key]) for key in ('rate', 'momentum'))
            if gradient.shape != weights.shape or velocity.shape != weights.shape or not 0 < rate <= 10 or not 0 <= momentum < 1:
                raise ValueError('Invalid optimizer inputs.')
            next_velocity = momentum * velocity + gradient
            baseline, output = weights-rate*gradient, weights-rate*next_velocity
            independent = [float(w)-rate*(momentum*float(v)+float(g)) for w,v,g in zip(weights,velocity,gradient)]
            return checked(kind, baseline, output, independent, [('∇L', gradient), ('v₁', next_velocity),
                           ('SGD', baseline), ('momentum', output)])
        if kind == 'linear_complexity':
            length = plan.get('tokens')
            width = plan.get('head_dim')
            if any(type(number) is not int or not 1 <= number <= 4096 for number in (length, width)):
                raise ValueError('Token and feature counts must be integers from 1 to 4096.')
            # Compare dominant multiply counts for QKᵀ vs rearranged Q(KᵀV).
            baseline, output = [2*length**2*width], [2*length*width**2]
            independent = [2*sum(length for _ in range(width**2))]
            return checked(kind, baseline, output, independent, [('n, d', [length, width]),
                           ('(QKᵀ)V', baseline), ('Q(KᵀV)', output)])
    from .research_examples import execute_research_example

    return execute_research_example(plan)


def checked(kind, baseline, output, independent, states):
    passed = bool(np.allclose(output, independent, rtol=1e-9, atol=1e-9))
    if not passed:
        raise ValueError('Independent numerical checkpoint failed.')
    return {'kind': kind, 'baseline': np.asarray(baseline).tolist(), 'output': np.asarray(output).tolist(),
            'states': [{'label': label, 'values': np.asarray(value).tolist()} for label, value in states],
            'checkpoints': [{'name': 'output', 'passed': passed}],
            'scope': 'Illustrative toy inputs, not paper experimental data.'}
