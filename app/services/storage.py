"""Local filesystem storage for uploaded resumes.

Keys are namespaced by user (``<user-id>/<uuid>.<ext>``) and every path is
resolved and checked against the storage root, protecting against path
traversal.  Writes are atomic (temp file + ``os.replace``).
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_-]")
_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,10}$")


class StorageError(Exception):
    """Raised for invalid keys or storage failures."""


@dataclass(frozen=True)
class StoredFile:
    key: str
    size_bytes: int
    sha256: str


class Storage:
    """Simple, safe file storage rooted at *base_dir*."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        if not key or "\x00" in key:
            raise StorageError("Invalid storage key")
        if key.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", key):
            raise StorageError("Absolute storage keys are not allowed")
        path = (self.base_dir / key).resolve()
        if not path.is_relative_to(self.base_dir):
            raise StorageError("Storage key escapes the storage root")
        return path

    def save(self, data: bytes, *, user_id: str, extension: str) -> StoredFile:
        if not data:
            raise StorageError("Cannot store an empty file")
        extension = extension.lower()
        if not _EXTENSION_RE.match(extension):
            raise StorageError("Invalid file extension")

        safe_user = _SAFE_SEGMENT_RE.sub("", user_id)[:64] or "anonymous"
        key = f"{safe_user}/{uuid.uuid4().hex}{extension}"
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(data).hexdigest()
        file_descriptor, temp_path = tempfile.mkstemp(
            dir=target.parent, prefix=".upload-", suffix=".tmp"
        )
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
        except BaseException:
            Path(temp_path).unlink(missing_ok=True)
            raise
        return StoredFile(key=key, size_bytes=len(data), sha256=digest)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> bool:
        path = self._resolve(key)
        if not path.is_file():
            return False
        path.unlink(missing_ok=True)
        return True
