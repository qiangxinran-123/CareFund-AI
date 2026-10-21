"""Verify original fixtures while tolerating Git's LF-to-CRLF checkout only."""

import hashlib
from pathlib import Path


def original_fixture_bytes(root: Path, entry: dict) -> bytes:
    data = (root / entry["path"]).read_bytes()
    for candidate in (data, data.replace(b"\r\n", b"\n")):
        if len(candidate) == entry["bytes"] and hashlib.sha256(candidate).hexdigest() == entry["sha256"]:
            return candidate
    raise ValueError("A fixture fingerprint mismatch: " + entry["path"])
