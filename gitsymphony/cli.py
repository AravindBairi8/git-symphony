"""Command-line interface: ``gitsymphony [REPO] -o song.wav``."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .composer import SCALES, compose
from .history import GitError, read_history
from .midi import write_midi
from .player import write_html
from .synth import write_wav

FORMATS = (".wav", ".mid", ".midi", ".html", ".json")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitsymphony",
        description="Turn a git repository's commit history into music.",
    )
    p.add_argument("repo", nargs="?", default=".", help="path to a git repository (default: .)")
    p.add_argument(
        "-o", "--output", action="append", metavar="FILE",
        help="output file; format from extension: .wav .mid .html .json "
             "(repeatable, default: symphony.wav)",
    )
    p.add_argument("--rev", default="HEAD", help="branch, tag or revision range (default: HEAD)")
    p.add_argument("-n", "--max-commits", type=int, default=300,
                   help="use at most this many recent commits; 0 for all (default: 300)")
    p.add_argument("--scale", choices=sorted(SCALES), default="pentatonic")
    p.add_argument("--key", help="musical key such as C, F# or Bb (default: chosen by the first commit)")
    p.add_argument("--tempo", type=int, default=112, help="beats per minute (default: 112)")
    p.add_argument("--sample-rate", type=int, default=22050, help="WAV sample rate (default: 22050)")
    p.add_argument("--title", help="song title (default: repository folder name)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    outputs = args.output or ["symphony.wav"]
    for out in outputs:
        if not out.lower().endswith(FORMATS):
            print(f"gitsymphony: unsupported output {out!r} (use {', '.join(FORMATS)})", file=sys.stderr)
            return 2
    if args.tempo <= 0:
        print("gitsymphony: --tempo must be positive", file=sys.stderr)
        return 2

    try:
        commits = read_history(args.repo, args.rev, args.max_commits)
    except GitError as e:
        print(f"gitsymphony: {e}", file=sys.stderr)
        return 1
    if not commits:
        print("gitsymphony: no commits found", file=sys.stderr)
        return 1

    title = args.title or os.path.basename(os.path.abspath(args.repo))
    try:
        score = compose(commits, scale=args.scale, key=args.key, tempo=args.tempo, title=title)
    except ValueError as e:
        print(f"gitsymphony: {e}", file=sys.stderr)
        return 2

    secs = score.length_seconds
    print(
        f"Composed {len(commits)} commits by {len(score.voices)} author(s) "
        f"in {score.key} {score.scale}, {int(secs // 60)}:{int(secs % 60):02d} long"
    )
    for out in outputs:
        ext = os.path.splitext(out)[1].lower()
        if ext == ".wav":
            write_wav(score, out, args.sample_rate)
        elif ext in (".mid", ".midi"):
            write_midi(score, out)
        elif ext == ".html":
            write_html(score, out)
        else:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(score.to_dict(), f, indent=2)
        print(f"  -> {out}")
    return 0
