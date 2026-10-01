"""git-symphony: turn a git repository's history into music."""

from .composer import SCALES, Score, compose
from .history import Commit, read_history

__all__ = ["SCALES", "Commit", "Score", "compose", "read_history"]
__version__ = "0.1.0"
