"""File logging for the backend.

Logs are appended to `/tmp/logs/`, one file per rollover, each named for the
timestamp of its first record. A file is closed and replaced once it reaches
`MAX_BYTES`, and only the `KEEP_FILES` most recent survive.

Records carry operational metadata only. `docs/specification.md` §8.1 requires
logs to exclude raw personal memories, full user or assistant messages,
credentials, and API keys, so nothing here may log chat content.
"""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("tmp/logs")
FILE_PREFIX = "backend-"
MAX_BYTES = 1_000_000
KEEP_FILES = 5

# The logger every backend module should descend from, so one call configures
# all of them: `logging.getLogger("linger.<something>")`.
ROOT_NAME = "linger"


class TimestampedRotatingHandler(RotatingFileHandler):
    """Rotates into a new timestamp-named file rather than `.1`/`.2` suffixes.

    Each file is named for the moment of its first record: `delay=True` means
    nothing is created until something is actually logged. A restart appends to
    the newest file that still has room, so a new name appears only when the
    previous file filled up.
    """

    def __init__(self, directory: Path, max_bytes: int, keep: int) -> None:
        self.directory = directory
        self.keep = keep
        self.max_bytes = max_bytes
        super().__init__(self._resume_path(), maxBytes=max_bytes, delay=True)

    def _resume_path(self) -> str:
        """The file to append to at startup.

        A restart continues the newest file that still has room, so routine
        server reloads do not scatter a handful of near-empty logs. Only a
        genuinely full (or absent) file starts a new one.
        """
        existing = sorted(
            self.directory.glob(f"{FILE_PREFIX}*.log"),
            key=lambda p: p.stat().st_mtime,
        )
        if existing and existing[-1].stat().st_size < self.max_bytes:
            return str(existing[-1])
        return self._new_path()

    def _new_path(self) -> str:
        """A path that does not exist yet, unique within the same second."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.directory / f"{FILE_PREFIX}{stamp}.log"
        counter = 1
        while path.exists():
            path = self.directory / f"{FILE_PREFIX}{stamp}-{counter}.log"
            counter += 1
        return str(path)

    def doRollover(self) -> None:
        """Close the full file and start a fresh one under a new name."""
        if self.stream:
            self.stream.close()
            self.stream = None
        self.baseFilename = self._new_path()
        if not self.delay:
            self.stream = self._open()
        self._prune()

    def _prune(self) -> None:
        """Delete all but the `keep` most recent log files.

        `keep` counts every file left on disk, including the one now being
        written. Ordered by mtime because the `-1`/`-2` uniquifier does not
        sort lexicographically against a bare timestamp.
        """
        active = Path(self.baseFilename)
        existing = sorted(
            (p for p in self.directory.glob(f"{FILE_PREFIX}*.log") if p != active),
            key=lambda p: p.stat().st_mtime,
        )
        # `keep` counts every file on disk, and the active one is always kept,
        # so only `keep - 1` completed files survive alongside it.
        for stale in existing[: -(self.keep - 1) or None]:
            stale.unlink(missing_ok=True)


def configure_logging() -> logging.Logger:
    """Attach file and console handlers to the `linger` logger.

    Idempotent: uvicorn's `--reload` re-imports the app, and repeated calls
    must not stack duplicate handlers that would log every record twice.
    """
    root = logging.getLogger(ROOT_NAME)
    if root.handlers:
        return root

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = TimestampedRotatingHandler(LOG_DIR, MAX_BYTES, KEEP_FILES)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    # Uvicorn configures the root logger too; without this every record would
    # also print through its handlers.
    root.propagate = False
    return root
