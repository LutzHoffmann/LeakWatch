"""Watchers — source-specific pollers that emit RawItems."""

from .base import BaseWatcher
from .github_gist import GitHubGistWatcher
from .pastebin import PastebinWatcher

__all__ = ["BaseWatcher", "GitHubGistWatcher", "PastebinWatcher"]
