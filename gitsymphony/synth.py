"""A tiny wavetable synthesizer that renders a Score to a stereo WAV file.

Pure standard library: no numpy, no soundfonts.
"""

from __future__ import annotations

import math
import random
import sys
import wave
from array import array

from .composer import CRASH, HAT, KICK, Score

TABLE_SIZE = 4096

# Timbres as (harmonic, amplitude) pairs, built once into wavetables.
TIMBRES = {
    "warm": [(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12)],
    "sine": [(1, 1.0)],
    "hollow": [(1, 1.0), (3, 0.33), (5, 0.2), (7, 0.14)],
    "bell": [(1, 1.0), (3, 0.4), (6, 0.2), (9, 0.1)],
    "glass": [(1, 1.0), (2, 0.2), (5, 0.15), (8, 0.08)],
    "sub": [(1, 1.0), (2, 0.3)],
}
VOICE_TIMBRES = ["warm", "sine", "hollow", "bell", "glass"]

# (attack, decay, sustain level, release) in seconds / level.
ENVELOPES = {
    "lead": (0.01, 0.12, 0.6, 0.25),
    "chord": (0.08, 0.2, 0.7, 0.6),
    "bass": (0.01, 0.3, 0.5, 0.3),
}
PART_GAIN = {"lead": 0.5, "chord": 0.22, "bass": 0.45}


def _table(harmonics: list[tuple[int, float]]) -> list[float]:
    total = sum(a for _, a in harmonics)
    return [
        sum(a * math.sin(2 * math.pi * h * i / TABLE_SIZE) for h, a in harmonics) / total
        for i in range(TABLE_SIZE)
    ]


_TABLES: dict[str, list[float]] = {}


def table(name: str) -> list[float]:
    if name not in _TABLES:
        _TABLES[name] = _table(TIMBRES[name])
    return _TABLES[name]


def voice_pan(voice: int) -> float:
    """Spread authors across the stereo field (-1 left .. 1 right)."""
    return ((voice * 0.618) % 1.0) * 1.4 - 0.7


def _gains(pan: float) -> tuple[float, float]:
    angle = (pan + 1) * math.pi / 4  # equal-power panning
    return math.cos(angle), math.sin(angle)


def _envelope(k: int, na: int, nd: int, sustain: float) -> float:
    if k < na:
        return k / na
    if k < na + nd:
        return 1.0 - (1.0 - sustain) * (k - na) / nd
    return sustain


def _tone(left, right, sr, start, dur, freq, amp, wave_table, env, pan):
    attack, decay, sustain, release = env
    na, nd = max(1, int(attack * sr)), max(1, int(decay * sr))
    n_on, nr = max(1, int(dur * sr)), max(1, int(release * sr))
    off_level = _envelope(n_on, na, nd, sustain)
    gl, gr = _gains(pan)
    gl, gr = gl * amp, gr * amp
    inc = freq * TABLE_SIZE / sr
    i0 = int(start * sr)
    phase = 0.0
    for k in range(min(n_on + nr, len(left) - i0)):
        if k < n_on:
            e = _envelope(k, na, nd, sustain)
        else:
            e = off_level * (1.0 - (k - n_on) / nr)
        s = wave_table[int(phase) % TABLE_SIZE] * e
        left[i0 + k] += s * gl
        right[i0 + k] += s * gr
        phase += inc


def _drum(left, right, sr, start, pitch, amp, pan, rng):
    gl, gr = _gains(pan)
    i0 = int(start * sr)
    if pitch == KICK:
        n, phase = int(0.35 * sr), 0.0
        for k in range(min(n, len(left) - i0)):
            t = k / sr
            phase += (50 + 100 * math.exp(-t * 30)) / sr
            s = math.sin(2 * math.pi * phase) * math.exp(-t * 8) * amp
            left[i0 + k] += s * gl
            right[i0 + k] += s * gr
        return
    decay, length = (60.0, 0.08) if pitch == HAT else (3.0, 1.5)
    prev = 0.0
    for k in range(min(int(length * sr), len(left) - i0)):
        x = rng.uniform(-1, 1)
        s = (x - prev) * 0.5 * math.exp(-k / sr * decay) * amp  # crude high-pass
        prev = x
        left[i0 + k] += s * gl
        right[i0 + k] += s * gr


def _echo(buf, sr, delay: float, feedback: float) -> None:
    d = int(delay * sr)
    for i in range(d, len(buf)):
        buf[i] += buf[i - d] * feedback


def render(score: Score, sample_rate: int = 22050) -> tuple[array, array]:
    """Render the score to left/right float buffers."""
    n = int((score.length_seconds + 3.0) * sample_rate)
    left = array("d", bytes(8 * n))
    right = array("d", bytes(8 * n))
    rng = random.Random(1234)
    for note in score.notes:
        start = score.seconds(note.start)
        amp = note.velocity / 127
        if note.part == "drums":
            drum_amp = amp * (0.25 if note.pitch == CRASH else 0.6)
            _drum(left, right, sample_rate, start, note.pitch, drum_amp, 0.0, rng)
            continue
        if note.part == "bass":
            timbre, pan = "sub", 0.0
        else:
            timbre = VOICE_TIMBRES[note.voice % len(VOICE_TIMBRES)]
            pan = voice_pan(note.voice)
        freq = 440.0 * 2 ** ((note.pitch - 69) / 12)
        _tone(
            left, right, sample_rate, start, score.seconds(note.duration), freq,
            amp * PART_GAIN[note.part], table(timbre), ENVELOPES[note.part], pan,
        )
    _echo(left, sample_rate, 0.33, 0.28)
    _echo(right, sample_rate, 0.27, 0.28)
    return left, right


def write_wav(score: Score, path: str, sample_rate: int = 22050) -> None:
    left, right = render(score, sample_rate)
    peak = max(max(map(abs, left)), max(map(abs, right)), 1e-9)
    gain = 0.89 * 32767 / peak
    data = array("h", (int(v * gain) for pair in zip(left, right) for v in pair))
    if sys.byteorder == "big":
        data.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(data.tobytes())
