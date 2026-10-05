"""Causal counterexamples, separate from the unchanged production acceptance gate."""

import hashlib

import numpy as np
import pytest
from generate_test_media.audio import RATE, transient_samples


@pytest.mark.parametrize(
    "kind", ["sharp", "sharp_stereo", "sharp_delayed", "sustained_shifted", "mxf_sharp"]
)
def test_ringdown_cannot_prove_that_a_transient_is_legitimate(kind: str) -> None:
    """A fault impulse exciting a causal FIR can have an authored attack's shape.

    This is an existence proof for local shape ambiguity, not a model fitted to
    the reference MXF, a new classifier, or evidence that every attack is faulty.
    The FIR coefficients are the analytic attack response already in the corpus.
    A sparse digital fault is independently convolved with that fixed response.
    """
    recipe = "sharp_stereo" if kind == "mxf_sharp" else kind
    legitimate = transient_samples(recipe)
    onset = 2.015 if kind == "sustained_shifted" else 2.0
    origin = round(onset * RATE)
    count = 1920  # 40 ms observation; no detector or threshold is changed.
    absolute = np.arange(origin, origin + count) / RATE
    base = 0.1 * np.sin(2 * np.pi * 1000 * absolute)
    fault_output = np.repeat(base[:, None], legitimate.shape[1], axis=1)
    for channel in range(legitimate.shape[1]):
        delay = 48 if kind == "sharp_delayed" and channel == 1 else 0
        attack_time = onset + delay / RATE
        # Derive the causal impulse response independently of fixture samples.
        elapsed = np.arange(origin + delay, origin + count) / RATE - attack_time
        decay = 0.08 if kind == "sustained_shifted" else 0.0008
        response = (
            0.8
            * (1 - np.exp(-elapsed / 0.0001))
            * np.exp(-elapsed / decay)
            * np.sin(2 * np.pi * 8000 * elapsed)
        )
        injected = np.zeros(count)
        injected[delay] = 1  # a genuine one-sample fault before a ringing filter
        fault_output[:, channel] += np.convolve(injected, response)[:count]
    authored_pcm = (legitimate[origin : origin + count] * 32768).astype("<i2")
    faulty_pcm = (fault_output * 32768).astype("<i2")
    assert np.array_equal(authored_pcm, faulty_pcm)
    assert (
        hashlib.sha256(authored_pcm.tobytes()).digest()
        == hashlib.sha256(faulty_pcm.tobytes()).digest()
    )
    # Hence polarity, derivatives, local recovery and channel correlations are
    # identical too. Even the complete 40 ms neighborhood cannot establish cause.
    assert np.array_equal(np.diff(authored_pcm, axis=0), np.diff(faulty_pcm, axis=0))


def test_channel_local_signal_does_not_change_when_unrelated_channel_is_added() -> None:
    """Channel-local baseline fixes cross-channel dependence, not causal intent."""
    assert np.array_equal(
        transient_samples("sharp")[:, 0], transient_samples("sharp_busy")[:, 0]
    )
    isolated = transient_samples("simultaneous")[:, 0]
    assert np.array_equal(isolated, transient_samples("masked")[:, 0])
    assert np.array_equal(isolated, transient_samples("masked_swapped")[:, 1])
