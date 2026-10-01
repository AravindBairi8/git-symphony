"""Read commit history out of a git repository."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

RECORD = "\x1e"
FIELD = "\x1f"
PRETTY = "--pretty=format:%x1e%H%x1f%an%x1f%ae%x1f%at%x1f%P%x1f%s"


class GitError(RuntimeError):
    """Raised when git is missing or the repository can't be read."""


@dataclass
class Commit:
    sha: str
    author: str
    email: str
    timestamp: int
    parents: list[str] = field(default_factory=list)
    subject: str = ""
    additions: int = 0
    deletions: int = 0
    files: list[str] = field(default_factory=list)

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def churn(self) -> int:
        return self.additions + self.deletions


def parse_log(text: str) -> list[Commit]:
    """Parse the output of ``git log --numstat`` with the PRETTY format."""
    commits = []
    for record in text.split(RECORD):
        if not record.strip():
            continue
        header, _, body = record.partition("\n")
        parts = header.split(FIELD)
        if len(parts) < 6:
            continue
        sha, author, email, ts, parents, subject = parts[:6]
        commit = Commit(
            sha=sha,
            author=author,
            email=email,
            timestamp=int(ts or 0),
            parents=parents.split(),
            subject=subject,
        )
        for line in body.splitlines():
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            added, deleted, path = cols
            # Binary files report "-" for both counts.
            commit.additions += int(added) if added.isdigit() else 0
            commit.deletions += int(deleted) if deleted.isdigit() else 0
            commit.files.append(path)
        commits.append(commit)
    return commits


def read_history(repo: str = ".", rev: str = "HEAD", max_commits: int = 300) -> list[Commit]:
    """Return up to ``max_commits`` of the most recent commits, oldest first."""
    if shutil.which("git") is None:
        raise GitError("git is not installed or not on PATH")
    cmd = ["git", "-C", repo, "log", "--reverse", "--numstat", "--no-color", PRETTY]
    if max_commits > 0:
        cmd.append(f"--max-count={max_commits}")
    cmd.append(rev)
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(msg or f"git log failed in {repo!r}")
    return parse_log(proc.stdout.decode("utf-8", "replace"))
