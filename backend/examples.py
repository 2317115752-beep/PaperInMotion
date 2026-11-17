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
            return {'kind': kind, 'base': W.tolist(), 'A': A.tolist(), 'B': B.tolist(), 'input': x.tolist(), 'scale': scale, 'baseline': baseline.tolist(), 'hidden': hidden.tolist(), 'delta': delta.tolist(), 'output': output.tolist(), 'params': {'frozen': int(W.size), 'adapter': int(A.size + B.size), 'rank': A.shape[0]}, 'steps': [{'formula': 'y₀ = W₀x', 'result': baseline.tolist()}, {'formula': 'h = Ax', 'result': hidden.tolist()}, {'formula': 'Δy = scale × Bh', 'result': delta.tolist()}, {'formula': 'y = y₀ + Δy', 'result': output.tolist()}], 'scope': 'Illustrative toy inputs, not paper experimental data.'}
        if kind == 'scaled_dot_attention':
            Q, K, V = (array(plan.get(key), 2, key) for key in ('Q', 'K', 'V'))
            if Q.shape[1] != K.shape[1] or K.shape[0] != V.shape[0]:
                raise ValueError('Q、K、V 的矩阵维度不匹配。')
            scores = Q @ K.T / np.sqrt(Q.shape[1])
            weights = np.exp(scores - scores.max(axis=-1, keepdims=True))
            weights /= weights.sum(axis=-1, keepdims=True)
            output = weights @ V
            return {'kind': kind, 'Q': Q.tolist(), 'K': K.tolist(), 'V': V.tolist(), 'scores': scores.tolist(), 'weights': weights.tolist(), 'output': output.tolist(), 'steps': [{'formula': 'scores = QKᵀ / √d', 'result': scores.tolist()}, {'formula': 'weights = softmax(scores)', 'result': weights.tolist()}, {'formula': 'output = weights × V', 'result': output.tolist()}], 'scope': 'Illustrative toy inputs, not paper experimental data.'}
    raise ValueError('首版只支持 low_rank 和 scaled_dot_attention 安全计算模板。')
