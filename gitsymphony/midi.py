"""Write a Score as a Standard MIDI File (format 1), one track per part."""

from __future__ import annotations

import struct

from .composer import Score

TICKS_PER_BEAT = 480
DRUM_CHANNEL = 9
BASS_CHANNEL = 8
MELODIC_CHANNELS = [c for c in range(16) if c not in (DRUM_CHANNEL, BASS_CHANNEL)]
# Piano, vibraphone, flute, harp, warm pad, marimba, clarinet
PROGRAMS = [0, 11, 73, 46, 89, 12, 71]
BASS_PROGRAM = 33


def _varlen(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _meta(kind: int, data: bytes) -> bytes:
    return bytes([0xFF, kind]) + _varlen(len(data)) + data


def _chunk(kind: bytes, data: bytes) -> bytes:
    return kind + struct.pack(">I", len(data)) + data


def _track(name: str, events: list[tuple[int, int, bytes]]) -> bytes:
    body = b"\x00" + _meta(0x03, name.encode("utf-8", "replace")[:120])
    tick = 0
    for at, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        body += _varlen(at - tick) + msg
        tick = at
    body += b"\x00" + _meta(0x2F, b"")
    return _chunk(b"MTrk", body)


def to_midi(score: Score) -> bytes:
    tempo = int(60_000_000 / score.tempo)
    conductor = [
        (0, 0, _meta(0x51, tempo.to_bytes(3, "big"))),
        (0, 0, _meta(0x58, bytes([4, 2, 24, 8]))),
    ]
    tracks = [_track(score.title or "git-symphony", conductor)]

    parts: dict[tuple, tuple[str, int, int | None, list]] = {}
    for note in score.notes:
        if note.part == "drums":
            key = ("drums",)
            spec = ("Drums", DRUM_CHANNEL, None)
        elif note.part == "bass":
            key = ("bass",)
            spec = ("Bass", BASS_CHANNEL, BASS_PROGRAM)
        else:
            key = ("voice", note.voice)
            spec = (
                score.voices[note.voice],
                MELODIC_CHANNELS[note.voice % len(MELODIC_CHANNELS)],
                PROGRAMS[note.voice % len(PROGRAMS)],
            )
        parts.setdefault(key, (*spec, []))[3].append(note)

    for name, channel, program, notes in parts.values():
        events = []
        if program is not None:
            events.append((0, 0, bytes([0xC0 | channel, program])))
        for n in notes:
            pitch = max(0, min(127, n.pitch))
            vel = max(1, min(127, n.velocity))
            on = round(n.start * TICKS_PER_BEAT)
            off = on + max(1, round(n.duration * TICKS_PER_BEAT))
            # Order 1 = note-off, 2 = note-on, so repeated notes retrigger cleanly.
            events.append((on, 2, bytes([0x90 | channel, pitch, vel])))
            events.append((off, 1, bytes([0x80 | channel, pitch, 0])))
        tracks.append(_track(name, events))

    header = _chunk(b"MThd", struct.pack(">HHH", 1, len(tracks), TICKS_PER_BEAT))
    return header + b"".join(tracks)


def write_midi(score: Score, path: str) -> None:
    with open(path, "wb") as f:
        f.write(to_midi(score))
