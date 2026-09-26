"""Deterministic acquisition: download GHCNh files with hashes and retries."""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.request
from pathlib import Path

from src.noaa import config as C

logger = logging.getLogger("aws_noaa.acquire")

S3_BASE = "https://noaa-ghcnh-pds.s3.amazonaws.com"


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, retries: int = 4,
                  min_bytes: int = 1024) -> dict:
    """Download a URL to dest (skip when a valid copy exists). Return record.

    Existing files are re-verified by size and re-downloaded when the local
    copy is smaller than min_bytes. Records carry URL, size, and SHA-256.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        logger.info("Reusing %s (%d bytes)", dest.name, dest.stat().st_size)
        return {"url": url, "file": dest.name, "bytes": dest.stat().st_size,
                "sha256": sha256_file(dest), "reused": True}
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, dest)
            size = dest.stat().st_size
            if size < min_bytes:
                raise ValueError(f"{dest.name}: only {size} bytes")
            logger.info("Downloaded %s (%d bytes)", dest.name, size)
            return {"url": url, "file": dest.name, "bytes": size,
                    "sha256": sha256_file(dest), "reused": False}
        except Exception as exc:  # noqa: BLE001 - retry then raise
            last = exc
            logger.warning("Attempt %d/%d failed for %s: %s",
                           attempt, retries, url, exc)
            time.sleep(2 * attempt)
    raise RuntimeError(f"Download failed after {retries} attempts: {url}") from last


def station_year_url(station_id: str, year: int) -> str:
    """Canonical S3 HTTPS URL of one station-year parquet file."""
    return (f"{S3_BASE}/hourly/access/by-year/{year}/parquet/"
            f"GHCNh_{station_id}_{year}.parquet")


def acquire_station_years(raw_dir: Path) -> list[dict]:
    """Download every shortlisted station-year file. Return download records."""
    records = []
    for station in C.STATIONS:
        for year in C.YEARS:
            url = station_year_url(station["ghcnh_id"], year)
            dest = (Path(raw_dir) / "by-year" / str(year)
                    / f"GHCNh_{station['ghcnh_id']}_{year}.parquet")
            rec = download_file(url, dest)
            records.append({"station_id": station["ghcnh_id"], "year": year,
                            "path": str(dest).replace("\\", "/"), **rec})
    return records


def acquire_inventory(meta_dir: Path) -> list[dict]:
    """Download the station-list inventory and the documentation PDF."""
    meta_dir = Path(meta_dir)
    records = []
    for name, url in (("ghcnh-station-list.txt",
                       "https://www.ncei.noaa.gov/oa/global-historical-"
                       "climatology-network/hourly/doc/ghcnh-station-list.txt"),
                      ("ghcnh_DOCUMENTATION.pdf", C.DOC_PDF)):
        records.append({"kind": "inventory" if name.endswith(".txt") else "documentation",
                        "path": str(meta_dir / name).replace("\\", "/"),
                        **download_file(url, meta_dir / name, min_bytes=100)})
    return records
