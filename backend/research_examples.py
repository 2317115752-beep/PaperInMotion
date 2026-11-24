"""Verified worked-example kernels for the held-out papers."""
import math

import numpy as np


def execute_research_example(plan):
    from .examples import array, checked

    kind = plan['kind']
    if kind == 'residual_add':
        x = array(plan.get('x'), 1, 'x')
        residual = array(plan.get('residual'), 1, 'residual')
        if x.shape != residual.shape:
            raise ValueError('The residual and identity shortcut must have matching dimensions.')
        output = x + residual
        independent = [float(left) + float(right) for left, right in zip(x, residual)]
        return checked(kind, residual, output, independent,
                       [('x', x), ('F(x)', residual), ('F(x) + x', output)])

    if kind == 'volume_composite':
        alphas = array(plan.get('alphas'), 1, 'alphas')
        colors = array(plan.get('colors'), 1, 'colors')
        if alphas.shape != colors.shape or np.any((alphas < 0) | (alphas > 1)) or np.any((colors < 0) | (colors > 1)):
            raise ValueError('Volume samples require matching alpha/color vectors within [0, 1].')
        transmittance = np.concatenate(([1.], np.cumprod(1-alphas[:-1])))
        weights = transmittance * alphas
        output = [weights @ colors]
        independent = [math.fsum(float(alpha)*float(color)*math.prod(1-float(a) for a in alphas[:i])
                                 for i, (alpha, color) in enumerate(zip(alphas, colors)))]
        return checked(kind, [colors[0]], output, independent,
                       [('α', alphas), ('T', transmittance), ('Tα', weights), ('composite', output)])

    if kind == 'adam_step':
        weights = array(plan.get('weights'), 1, 'weights')
        grads = array(plan.get('gradient'), 1, 'gradient')
        alpha, beta1, beta2, epsilon = (float(plan.get(name, default)) for name, default in
                                       (('rate', .1), ('beta1', .9), ('beta2', .999), ('epsilon', 1e-8)))
        if (weights.shape != grads.shape or not 0 < alpha <= 10 or not 0 <= beta1 < 1
                or not 0 <= beta2 < 1 or not 0 < epsilon < 1):
            raise ValueError('Adam example requires aligned vectors and valid hyperparameters.')
        first = (1-beta1)*grads
        second = (1-beta2)*grads**2
        corrected_first, corrected_second = first/(1-beta1), second/(1-beta2)
        baseline = weights-alpha*grads
        output = weights-alpha*corrected_first/(np.sqrt(corrected_second)+epsilon)
        reference = [float(w)-alpha*float(g)/(abs(float(g))+epsilon) for w, g in zip(weights, grads)]
        return checked(kind, baseline, output, reference,
                       [('m₁', first), ('v₁', second), ('SGD', baseline), ('Adam', output)])

    if kind == 'tiled_softmax':
        scores = array(plan.get('scores'), 1, 'scores')
        values = array(plan.get('values'), 1, 'values')
        tile_size = plan.get('tile_size', 2)
        if (scores.shape != values.shape or len(scores) < 2
                or type(tile_size) is not int or not 1 <= tile_size < len(scores)):
            raise ValueError('Tiled attention requires at least two tiles of aligned scalar scores and values.')
        maxima, denominators, numerators = [], [], []
        maximum, denominator, numerator = -math.inf, 0., 0.
        for start in range(0, len(scores), tile_size):
            score_tile, value_tile = scores[start:start+tile_size], values[start:start+tile_size]
            next_max = max(float(score_tile.max()), maximum)
            decayed = math.exp(maximum-next_max)
            scores_exp = np.exp(score_tile-next_max)
            denominator = denominator*decayed + float(scores_exp.sum())
            numerator = numerator*decayed + float(scores_exp @ value_tile)
            maximum = next_max
            maxima.append(maximum)
            denominators.append(denominator)
            numerators.append(numerator)
        reference_weights = [math.exp(float(score)-float(scores.max())) for score in scores]
        full = [math.fsum(weight*float(value) for weight, value in zip(reference_weights, values))
                / math.fsum(reference_weights)]
        return checked(kind, full, [numerator/denominator], full,
                       [('running max', maxima), ('normalization', denominators),
                        ('weighted sum', numerators), ('attention output', [numerator/denominator])])

    raise ValueError('Unsupported computation template.')
