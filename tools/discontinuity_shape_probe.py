"""Rejected bounded developer experiment; never used by production detectors."""

import numpy as np
from numpy.typing import NDArray

from mediaqc_engine.detectors.audio.common import number


def candidates(
    samples: NDArray[np.float64],
    previous: NDArray[np.float64],
    policy: dict[str, object],
    *,
    isolated: bool,
) -> NDArray[np.bool_]:
    """48 kHz / 20 ms diagnostic. At most two jumps per channel is a hypothesis."""
    if (
        samples.ndim != 2
        or not 1 <= len(samples) <= 960
        or not 1 <= samples.shape[1] <= 64
        or previous.shape != (samples.shape[1],)
        or not np.all(np.isfinite(samples))
        or not np.all(np.isfinite(previous))
    ):
        raise ValueError("Probe requires bounded finite 20 ms PCM with previous sample")
    derivative = np.abs(np.diff(np.concatenate((previous[None, :], samples)), axis=0))
    scale = 2 - number(policy, "sensitivity")
    mask: NDArray[np.bool_] = (
        derivative >= number(policy, "min_jump_amplitude") * scale
    ) & (
        derivative / np.maximum(np.median(derivative, axis=0), 1e-12)
        >= number(policy, "min_derivative_ratio") * scale
    )
    if isolated:
        mask &= np.sum(mask, axis=0) <= 2
    return mask


def interpolation_candidates(
    samples: NDArray[np.float64],
    previous: NDArray[np.float64],
    following: NDArray[np.float64],
    policy: dict[str, object],
) -> NDArray[np.bool_]:
    """Rejected two-sided sample-prediction experiment, one-sample lookahead."""
    mask = candidates(samples, previous, policy, isolated=False)
    if following.shape != previous.shape or not np.all(np.isfinite(following)):
        raise ValueError("Invalid lookahead")
    padded = np.concatenate((previous[None, :], samples, following[None, :]))
    residual = np.abs(samples - (padded[:-2] + padded[2:]) / 2)
    limit = number(policy, "min_jump_amplitude") * (2 - number(policy, "sensitivity"))
    result: NDArray[np.bool_] = mask & (residual >= limit)
    return result
