"""ICAO24 hex code -> aircraft type/model lookup.

Downloads and caches the OpenSky aircraft database CSV.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

from ..models import AircraftInfo

logger = logging.getLogger(__name__)

DB_URL = "https://opensky-network.org/datasets/metadata/aircraft-database-complete-2024-06.csv"


class AircraftDB:
    def __init__(self, cache_dir: Path, cache_ttl_hours: int = 168):
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_hours * 3600
        self._db: dict[str, AircraftInfo] = {}
        self._loaded = False

    def lookup(self, icao24: str) -> Optional[AircraftInfo]:
        if not self._loaded:
            self._load()
        return self._db.get(icao24.lower())

    def _load(self):
        csv_path = self._cache_dir / "aircraft_db.csv"
        meta_path = self._cache_dir / "aircraft_db_meta.json"

        # Check if we need to download
        need_download = True
        if csv_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                age = time.time() - meta.get("downloaded_at", 0)
                if age < self._cache_ttl:
                    need_download = False
            except (json.JSONDecodeError, KeyError):
                pass

        if need_download:
            self._download(csv_path, meta_path)

        if csv_path.exists():
            self._parse_csv(csv_path)

        self._loaded = True
        logger.info("Aircraft DB loaded: %d entries", len(self._db))

    def _download(self, csv_path: Path, meta_path: Path):
        logger.info("Downloading aircraft database...")
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                resp = client.get(DB_URL)
                resp.raise_for_status()
                csv_path.write_bytes(resp.content)
                meta_path.write_text(json.dumps({
                    "downloaded_at": time.time(),
                    "url": DB_URL,
                }))
                logger.info("Aircraft database downloaded (%.1f MB)",
                            len(resp.content) / 1_000_000)
        except Exception as e:
            logger.warning("Failed to download aircraft DB: %s", e)

    def _parse_csv(self, csv_path: Path):
        try:
            text = csv_path.read_text(encoding="utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text), quotechar="'")
            for row in reader:
                # Get value helper — keys/values may have residual quotes
                def g(key):
                    val = row.get(key, "")
                    if val is None:
                        return None
                    return val.strip().strip("'") or None

                icao24 = g("icao24")
                if not icao24:
                    continue
                icao24 = icao24.lower()
                self._db[icao24] = AircraftInfo(
                    icao24=icao24,
                    registration=g("registration"),
                    typecode=g("typecode"),
                    model=g("model"),
                    manufacturer=g("manufacturerName"),
                    operator=g("operator"),
                    operator_icao=g("operatorIcao"),
                    operator_iata=g("operatorIata"),
                )
        except Exception as e:
            logger.warning("Failed to parse aircraft DB CSV: %s", e)
