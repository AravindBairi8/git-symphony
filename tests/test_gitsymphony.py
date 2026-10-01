import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave

from gitsymphony.cli import main
from gitsymphony.composer import CRASH, HAT, compose, parse_key
from gitsymphony.history import Commit, parse_log
from gitsymphony.midi import to_midi
from gitsymphony.player import to_html
from gitsymphony.synth import write_wav

LOG = (
    "\x1eaaaa1111\x1fAda\x1fada@example.com\x1f1700000000\x1f\x1fInitial commit\n"
    "10\t0\tREADME.md\n"
    "-\t-\tlogo.png\n"
    "\x1ebbbb2222\x1fGrace\x1fgrace@example.com\x1f1700003600\x1faaaa1111\x1fFix crash on empty input\n"
    "3\t40\tsrc/app.py\n"
    "\x1ecccc3333\x1fAda\x1fada@example.com\x1f1700100000\x1fbbbb2222 dddd4444\x1fMerge branch 'feature'\n"
    "\x1eeeee5555\x1fAda\x1fada@example.com\x1f1700200000\x1fcccc3333\x1fRelease v1.0.0\n"
    "1\t1\tpyproject.toml\n"
)


def sample_commits():
    return parse_log(LOG)


class HistoryTests(unittest.TestCase):
    def test_parse_log(self):
        commits = sample_commits()
        self.assertEqual([c.sha for c in commits], ["aaaa1111", "bbbb2222", "cccc3333", "eeee5555"])
        first = commits[0]
        self.assertEqual((first.additions, first.deletions), (10, 0))
        self.assertEqual(first.files, ["README.md", "logo.png"])
        self.assertTrue(commits[2].is_merge)
        self.assertFalse(commits[1].is_merge)
        self.assertEqual(commits[1].churn, 43)

    def test_ignores_garbage(self):
        self.assertEqual(parse_log(""), [])
        self.assertEqual(parse_log("\x1enot enough fields"), [])


class ComposerTests(unittest.TestCase):
    def test_deterministic(self):
        a = compose(sample_commits()).to_dict()
        b = compose(sample_commits()).to_dict()
        self.assertEqual(a, b)

    def test_voices_follow_authors(self):
        score = compose(sample_commits())
        self.assertEqual(score.voices, ["Ada", "Grace"])
        self.assertEqual(len(score.cues), 4)

    def test_merge_is_a_chord(self):
        score = compose(sample_commits())
        chord = [n for n in score.notes if n.part == "chord"]
        self.assertEqual(len(chord), 3)
        self.assertTrue(all(n.commit == 2 for n in chord))

    def test_fix_adds_grace_note(self):
        score = compose(sample_commits())
        leads = [n for n in score.notes if n.part == "lead" and n.commit == 1]
        self.assertEqual(len(leads), 2)
        self.assertEqual(leads[0].duration, 0.125)

    def test_release_crashes(self):
        score = compose(sample_commits())
        drums = [n for n in score.notes if n.part == "drums"]
        self.assertTrue(any(n.pitch == CRASH and n.commit == 3 for n in drums))
        self.assertEqual(sum(n.pitch == HAT for n in drums), 4)

    def test_time_moves_forward(self):
        beats = [c.beat for c in compose(sample_commits()).cues]
        self.assertEqual(beats, sorted(beats))
        self.assertEqual(len(set(beats)), len(beats))

    def test_deletions_sing_lower(self):
        base = Commit("12345678", "A", "a@x", 0, subject="add", additions=50)
        removal = Commit("12345678", "A", "a@x", 0, subject="remove", deletions=50)
        hi = compose([base], key="C").notes[-2].pitch
        lo = compose([removal], key="C").notes[-2].pitch
        self.assertEqual(hi - lo, 12)

    def test_key_and_scale(self):
        self.assertEqual(parse_key("C"), 0)
        self.assertEqual(parse_key("f#"), 6)
        self.assertEqual(parse_key("Bb"), 10)
        with self.assertRaises(ValueError):
            parse_key("H")
        score = compose(sample_commits(), key="D", scale="dorian")
        self.assertEqual((score.key, score.scale), ("D", "dorian"))
        with self.assertRaises(ValueError):
            compose(sample_commits(), scale="nope")
        with self.assertRaises(ValueError):
            compose([])


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.score = compose(sample_commits(), title="demo")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_midi(self):
        data = to_midi(self.score)
        self.assertEqual(data[:4], b"MThd")
        tracks = int.from_bytes(data[10:12], "big")
        # conductor + drums + bass + two authors
        self.assertEqual(tracks, 5)
        self.assertEqual(data.count(b"MTrk"), tracks)

    def test_wav(self):
        path = os.path.join(self.tmp, "song.wav")
        write_wav(self.score, path, sample_rate=8000)
        with wave.open(path) as w:
            self.assertEqual(w.getnchannels(), 2)
            self.assertEqual(w.getframerate(), 8000)
            self.assertGreater(w.getnframes(), 8000 * self.score.length_seconds)

    def test_html_escapes_script(self):
        self.score.cues[0].subject = "</script><b>hi"
        page = to_html(self.score)
        self.assertNotIn("</script><b>", page)
        start = page.index("const SCORE = ") + len("const SCORE = ")
        end = page.index(";\nconst COLORS")
        self.assertEqual(json.loads(page[start:end])["title"], "demo")


@unittest.skipIf(shutil.which("git") is None, "git not installed")
class CliTests(unittest.TestCase):
    def test_end_to_end(self):
        tmp = tempfile.mkdtemp()
        try:
            env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@x",
                       GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@x")
            run = lambda *a: subprocess.run(["git", "-C", tmp, *a], check=True, env=env, capture_output=True)
            run("init", "-q")
            for i in range(3):
                with open(os.path.join(tmp, "f.txt"), "a") as f:
                    f.write(f"line {i}\n")
                run("add", ".")
                run("commit", "-q", "-m", f"commit {i}")
            outs = [os.path.join(tmp, n) for n in ("s.wav", "s.mid", "s.html", "s.json")]
            argv = [tmp, "--sample-rate", "8000"]
            for o in outs:
                argv += ["-o", o]
            self.assertEqual(main(argv), 0)
            for o in outs:
                self.assertGreater(os.path.getsize(o), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_not_a_repo(self):
        tmp = tempfile.mkdtemp()
        try:
            self.assertEqual(main([tmp, "-o", os.path.join(tmp, "x.wav")]), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
