"""Map commits onto a musical score.

Every rule here is deterministic: the same history always produces the same
song, so a repository has exactly one "theme tune".
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .history import Commit

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

SCALES = {
    "pentatonic": [0, 2, 4, 7, 9],
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "blues": [0, 3, 5, 6, 7, 10],
}

FIX_RE = re.compile(r"\b(fix(es|ed)?|bug|hotfix|patch)\b", re.I)
RELEASE_RE = re.compile(r"\b(release|bump|v?\d+\.\d+\.\d+)\b", re.I)

KICK, HAT, CRASH = 36, 42, 49  # General MIDI drum numbers
STEP = 0.5  # beats between back-to-back commits
MAX_REST = 2.0  # longest silence a quiet period can produce, in beats
VOICE_OCTAVES = [0, -12, 12, 0, -12, 12]


@dataclass
class Note:
    start: float  # beats
    duration: float  # beats
    pitch: int  # MIDI note number
    velocity: int  # 1-127
    voice: int  # author index
    part: str  # "lead", "chord", "bass" or "drums"
    commit: int = -1


@dataclass
class Cue:
    beat: float
    sha: str
    author: str
    subject: str


@dataclass
class Score:
    title: str
    tempo: int
    key: str
    scale: str
    voices: list[str] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    cues: list[Cue] = field(default_factory=list)

    @property
    def length_beats(self) -> float:
        return max((n.start + n.duration for n in self.notes), default=0.0)

    @property
    def length_seconds(self) -> float:
        return self.seconds(self.length_beats)

    def seconds(self, beats: float) -> float:
        return beats * 60.0 / self.tempo

    def to_dict(self) -> dict:
        return asdict(self)


def parse_key(name: str) -> int:
    """Return the pitch class (0-11) for a key name such as "C", "F#" or "Bb"."""
    norm = name.strip()
    norm = norm[:1].upper() + norm[1:]
    norm = FLATS.get(norm, norm)
    if norm not in NOTE_NAMES:
        raise ValueError(f"unknown key {name!r}")
    return NOTE_NAMES.index(norm)


def scale_pitch(steps: list[int], degree: int) -> int:
    octave, idx = divmod(degree, len(steps))
    return 12 * octave + steps[idx]


def churn_duration(churn: int) -> float:
    """Bigger commits ring out longer."""
    for limit, beats in ((10, 0.25), (50, 0.5), (200, 1.0), (1000, 2.0)):
        if churn < limit:
            return beats
    return 4.0


def churn_velocity(churn: int) -> int:
    return int(min(127, 60 + math.log2(churn + 1) * 5))


def quantize(value: float, grid: float = 0.25) -> float:
    return round(value / grid) * grid


def _clamp(pitch: int) -> int:
    return max(24, min(108, pitch))


def compose(
    commits: list[Commit],
    *,
    scale: str = "pentatonic",
    key: str | None = None,
    tempo: int = 112,
    title: str = "",
) -> Score:
    if not commits:
        raise ValueError("no commits to compose")
    if scale not in SCALES:
        raise ValueError(f"unknown scale {scale!r}")
    steps = SCALES[scale]
    # With no key given, the very first commit picks one.
    root = parse_key(key) if key else int(commits[0].sha[:2], 16) % 12
    tonic = 60 + root

    score = Score(title=title, tempo=tempo, key=NOTE_NAMES[root], scale=scale)
    voice_of: dict[str, int] = {}
    beat = 0.0
    prev_ts = None
    prev_day = None

    for i, c in enumerate(commits):
        who = c.author or c.email
        if who not in voice_of:
            voice_of[who] = len(score.voices)
            score.voices.append(who)
        voice = voice_of[who]

        # Time between commits becomes rest: busy days are dense, quiet months breathe.
        if prev_ts is not None:
            gap_hours = max(0, c.timestamp - prev_ts) / 3600
            beat += STEP + quantize(min(MAX_REST, math.log2(1 + gap_hours) / 4))
        prev_ts = c.timestamp

        # Each new calendar day lays down a bass note and a kick drum.
        day = datetime.fromtimestamp(c.timestamp, timezone.utc).date()
        if day != prev_day:
            bass = tonic - 24 + steps[day.weekday() % len(steps)]
            score.notes.append(Note(beat, 2.0, bass, 70, voice, "bass", i))
            score.notes.append(Note(beat, 0.25, KICK, 100, voice, "drums", i))
            prev_day = day

        seed = int(c.sha[:8], 16)
        degree = seed % (len(steps) * 2)
        octave = VOICE_OCTAVES[voice % len(VOICE_OCTAVES)]
        if c.deletions > 2 * max(1, c.additions):
            octave -= 12  # code removal sings low
        duration = churn_duration(c.churn)
        velocity = churn_velocity(c.churn)
        start = beat

        if FIX_RE.search(c.subject):
            grace = tonic + octave + scale_pitch(steps, degree + 1)
            score.notes.append(Note(start, 0.125, _clamp(grace), velocity - 10, voice, "lead", i))
            start += 0.125

        if c.is_merge:
            for offset in (0, 2, 4):
                pitch = tonic + octave + scale_pitch(steps, degree + offset)
                score.notes.append(
                    Note(start, max(duration, 1.0), _clamp(pitch), velocity - 15, voice, "chord", i)
                )
        else:
            pitch = tonic + octave + scale_pitch(steps, degree)
            score.notes.append(Note(start, duration, _clamp(pitch), velocity, voice, "lead", i))

        if RELEASE_RE.search(c.subject):
            score.notes.append(Note(beat, 2.0, CRASH, 110, voice, "drums", i))
        hat_velocity = 30 + min(40, len(c.files) * 3)
        score.notes.append(Note(beat, 0.125, HAT, hat_velocity, voice, "drums", i))

        score.cues.append(Cue(beat, c.sha[:7], who, c.subject))

    return score
