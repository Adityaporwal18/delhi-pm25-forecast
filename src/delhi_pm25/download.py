"""File download helpers shared by the fetch scripts (01_fetch_cpcb.py, 01b_fetch_cpcb_vonter.py)."""

import hashlib
import time
from pathlib import Path

import requests


class DownloadError(Exception):
    """The server refused the file (e.g. HTTP 404): retrying will not help."""


def download(session: requests.Session, url: str, dest: Path) -> tuple[int, str]:
    """Stream `url` into `dest`, returning (bytes, sha256).

    Writes to `<dest>.part` first and renames only when complete, so an interrupted
    run never leaves a half-written file that looks valid. Retries network errors.
    """
    tmp = dest.with_name(dest.name + ".part")
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            sha, size = hashlib.sha256(), 0
            # identity = no gzip, so Content-Length is the true file size we can check
            with session.get(url, stream=True, timeout=(15, 120),
                             headers={"Accept-Encoding": "identity"}) as resp:
                if 400 <= resp.status_code < 500:  # 404 etc.: not retried (see except below)
                    raise DownloadError(f"HTTP {resp.status_code} for {url}")
                resp.raise_for_status()
                expected = resp.headers.get("Content-Length")
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
                        sha.update(chunk)
                        size += len(chunk)
            if expected is not None and int(expected) != size:
                raise OSError(f"truncated: got {size} of {expected} bytes")
            tmp.replace(dest)
            return size, sha.hexdigest()
        except (requests.RequestException, OSError) as exc:
            tmp.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            print(f"    attempt {attempt} failed ({exc}); retrying in {2 ** attempt}s")
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def sha256_of(path: Path) -> str:
    """SHA-256 fingerprint of a file on disk (read in 1 MB chunks, so any size works)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
