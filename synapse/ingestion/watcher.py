"""
File system watcher using watchdog.
Fires incremental re-index events when files change in watched folders.
Cross-platform: works on Windows, macOS, and Linux.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    raise ImportError("watchdog is required: pip install watchdog")

logger = logging.getLogger(__name__)

# Callback type: called with (file_path: Path, event_type: str)
# event_type is one of: "created", "modified", "deleted"
ChangeCallback = Callable[[Path, str], None]


class SynapseEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler that fires the callback on supported file changes.
    Filters out unsupported file types and ignored patterns before firing.
    """

    def __init__(
        self,
        callback: ChangeCallback,
        ignore_patterns: list[str],
    ):
        super().__init__()
        self._callback = callback
        self._ignore_patterns = ignore_patterns

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path), "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path), "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            # Old path is effectively deleted; new path is created
            self._handle(Path(event.src_path), "deleted")
            self._handle(Path(event.dest_path), "created")

    def _handle(self, path: Path, event_type: str) -> None:
        from synapse.ingestion.reader import is_supported, should_ignore

        if should_ignore(path, self._ignore_patterns):
            return

        if event_type != "deleted" and not is_supported(path):
            return

        logger.debug(f"[watcher] {event_type}: {path}")
        try:
            self._callback(path, event_type)
        except Exception as exc:
            logger.error(f"[watcher] callback error for {path}: {exc}")


class FileWatcher:
    """
    Manages watchdog Observer instances for multiple watch paths.
    Call start() to begin watching; stop() to clean up.
    """

    def __init__(
        self,
        watch_paths: list[Path],
        callback: ChangeCallback,
        ignore_patterns: list[str],
    ):
        self._watch_paths = watch_paths
        self._callback = callback
        self._ignore_patterns = ignore_patterns
        self._observer: Observer | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start watching all configured paths."""
        with self._lock:
            if self._observer and self._observer.is_alive():
                return

            handler = SynapseEventHandler(self._callback, self._ignore_patterns)
            self._observer = Observer()

            for path in self._watch_paths:
                if path.exists() and path.is_dir():
                    self._observer.schedule(handler, str(path), recursive=True)
                    logger.info(f"[watcher] Watching: {path}")
                else:
                    logger.warning(f"[watcher] Path not found, skipping: {path}")

            self._observer.start()
            logger.info("[watcher] Observer started.")

    def stop(self) -> None:
        """Stop the observer and clean up threads."""
        with self._lock:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
                logger.info("[watcher] Observer stopped.")

    def is_running(self) -> bool:
        with self._lock:
            return self._observer is not None and self._observer.is_alive()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
