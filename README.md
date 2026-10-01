#  git-symphony

Every repository has a song. This tool lets you hear it.

`git-symphony` reads a repository's commit history and composes it into music.
Each contributor becomes an instrument, every commit becomes a note, merges
play as chords, bug fixes get a grace note and releases hit the cymbals. The
same history always produces the same song, so every repository has exactly
one theme tune.

It outputs:

- `.wav`: rendered by a built-in wavetable synthesizer, ready to play anywhere
-  `.mid`: one track per contributor, ready to open in GarageBand, FL Studio, MuseScore or any DAW
- `.html`: a self-contained interactive player with a scrolling piano roll and the commit messages shown as it plays
- `.json`: the raw score, if you want to build your own visualizer

It has zero dependencies: only Python 3.9+ and `git`.

 [Live demo](docs/demo.html): a simulated 300-commit history with 4 contributors.
Turn on GitHub Pages for the `docs/` folder to make it playable online.

Quick start

```bash
pip install git+https://github.com/AravindBairi8/git-symphony
cd path/to/any/repo
gitsymphony -o song.wav -o song.html
```

Or run it without installing:

```bash
python -m gitsymphony path/to/repo -o song.html
```

Try it on a famous project:

```bash
git clone https://github.com/torvalds/linux --depth 500
gitsymphony linux -o linux.mid --scale dorian --tempo 140
```

How the history becomes music

| In the repository            | In the song                                                       |
| ---------------------------- | ----------------------------------------------------------------- |
| A contributor                | Their own instrument (timbre), octave and place in the stereo field |
| A commit                     | A note whose pitch comes from the commit hash                     |
| Lines changed                | Note length and loudness: big commits ring out longer            |
| A commit that mostly deletes | Played an octave lower                                            |
| A merge commit               | A three-note chord                                                |
| `fix`, `bug`, `hotfix`       | A quick grace note before the main note                           |
| `release`, `v1.2.3`, `bump`  | A cymbal crash                                                    |
| Time between commits         | Silence: busy days are dense, quiet months breathe               |
| A new calendar day           | A bass note (chosen by weekday) and a kick drum                   |
| Files touched                | Hi-hat loudness                                                   |
| The very first commit        | The song's key                                                    |

All notes are mapped onto a scale, so the result is always in tune.

Options

```
gitsymphony [REPO] [-o FILE ...] [--rev REV] [-n MAX_COMMITS]
            [--scale {blues,dorian,lydian,major,minor,pentatonic}]
            [--key KEY] [--tempo BPM] [--sample-rate HZ] [--title TITLE]
```

| Option            | Default            | Meaning                                         |
| ----------------- | ------------------ | ----------------------------------------------- |
| `REPO`            | `.`                | Path to the repository                          |
| `-o FILE`         | `symphony.wav`     | Output; repeat for several formats              |
| `--rev`           | `HEAD`             | Branch, tag or range such as `v1.0..v2.0`       |
| `-n`              | `300`              | Most recent N commits (`0` = whole history)     |
| `--scale`         | `pentatonic`       | Musical scale                                   |
| `--key`           | from first commit  | `C`, `F#`, `Bb` ...                             |
| `--tempo`         | `112`              | Beats per minute                                |
| `--sample-rate`   | `22050`            | WAV quality (44100 for CD quality, but slower)  |

Ideas for using it

- Add the song of your project to your README
- Compare the themes of `v1.0..v2.0` and `v2.0..v3.0`
- Play your team's sprint as a song at the retro
- Give the commit-history song to a contributor as a goodbye gift
- The CI workflow in this repository composes its own history on every push; download it from the run's artifacts

Project layout

```
gitsymphony/
  history.py   reads `git log --numstat` into Commit objects
  composer.py  turns commits into a Score of notes (the musical rules)
  synth.py     pure-Python wavetable synth + echo, writes WAV
  midi.py      Standard MIDI File writer
  player.py    self-contained HTML/WebAudio player
  cli.py       command-line interface
tests/         unittest suite (no extra packages needed)
```

Development

```bash
python -m unittest discover -s tests -v
```

Contributions are welcome. New scales, instruments and musical rules make
great first pull requests.

License

MIT
