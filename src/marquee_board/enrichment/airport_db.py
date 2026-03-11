"""ICAO airport code -> IATA code and city name lookup.

Uses the OurAirports dataset.
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

from ..models import AirportInfo

logger = logging.getLogger(__name__)

DB_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


class AirportDB:
    def __init__(self, cache_dir: Path, cache_ttl_hours: int = 168):
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_hours * 3600
        self._by_icao: dict[str, AirportInfo] = {}
        self._loaded = False

    def lookup(self, icao_code: str) -> Optional[AirportInfo]:
        if not self._loaded:
            self._load()
        return self._by_icao.get(icao_code.upper())

    def iata_for_icao(self, icao_code: str) -> Optional[str]:
        info = self.lookup(icao_code)
        return info.iata if info else None

    def _load(self):
        csv_path = self._cache_dir / "airports.csv"
        meta_path = self._cache_dir / "airports_meta.json"

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
            self._parse(csv_path)

        self._loaded = True
        logger.info("Airport DB loaded: %d airports", len(self._by_icao))

    def _download(self, csv_path: Path, meta_path: Path):
        logger.info("Downloading airport database...")
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                resp = client.get(DB_URL)
                resp.raise_for_status()
                csv_path.write_bytes(resp.content)
                meta_path.write_text(json.dumps({
                    "downloaded_at": time.time(),
                    "url": DB_URL,
                }))
                logger.info("Airport database downloaded (%.1f MB)",
                            len(resp.content) / 1_000_000)
        except Exception as e:
            logger.warning("Failed to download airport DB: %s", e)

    def _parse(self, csv_path: Path):
        try:
            text = csv_path.read_text(encoding="utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                icao = row.get("ident", "").strip()
                iata = row.get("iata_code", "").strip() or None
                name = row.get("name", "").strip() or None
                city = row.get("municipality", "").strip() or None
                apt_type = row.get("type", "")

                if not icao:
                    continue

                # Only keep airports with IATA codes or medium/large airports
                if not iata and apt_type not in ("medium_airport", "large_airport"):
                    continue

                self._by_icao[icao] = AirportInfo(
                    icao=icao,
                    iata=iata,
                    name=name,
                    city=city,
                )
        except Exception as e:
            logger.warning("Failed to parse airport DB: %s", e)
