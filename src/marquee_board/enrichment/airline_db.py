"""Callsign -> airline name lookup.

Parses ICAO 3-letter codes from ATC callsigns and maps to airline info.
Uses the OpenFlights airlines database.
"""
from __future__ import annotations
import csv
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import httpx

from ..models import AirlineInfo

logger = logging.getLogger(__name__)

DB_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"


class AirlineDB:
    def __init__(self, cache_dir: Path, cache_ttl_hours: int = 720):
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_hours * 3600
        self._by_icao: dict[str, AirlineInfo] = {}
        self._loaded = False

    def lookup_icao(self, icao_code: str) -> Optional[AirlineInfo]:
        if not self._loaded:
            self._load()
        return self._by_icao.get(icao_code.upper())

    def parse_callsign(self, callsign: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse an ATC callsign into (ICAO airline code, flight number).

        Examples:
            "UAL1234" -> ("UAL", "1234")
            "DLH45A"  -> ("DLH", "45A")
            "N12345"  -> (None, None)  -- general aviation
        """
        if not callsign or len(callsign) < 4:
            return None, None

        # Extract the alphabetic prefix (ICAO codes are 3 letters)
        alpha_prefix = ""
        for ch in callsign:
            if ch.isalpha():
                alpha_prefix += ch
            else:
                break

        if len(alpha_prefix) != 3:
            return None, None

        remainder = callsign[3:].strip()
        if not remainder:
            return None, None

        # Check if this is a known airline
        if not self._loaded:
            self._load()

        if alpha_prefix.upper() in self._by_icao:
            return alpha_prefix.upper(), remainder

        return None, None

    def get_display_flight_number(self, callsign: str) -> Optional[str]:
        """Convert an ICAO callsign to an IATA-style flight number.

        "UAL1234" -> "UA1234"
        """
        icao_code, flight_num = self.parse_callsign(callsign)
        if not icao_code or not flight_num:
            return None

        airline = self.lookup_icao(icao_code)
        if airline and airline.iata_code:
            return f"{airline.iata_code}{flight_num}"

        return f"{icao_code}{flight_num}"

    def _load(self):
        dat_path = self._cache_dir / "airlines.dat"
        meta_path = self._cache_dir / "airlines_meta.json"

        need_download = True
        if dat_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                age = time.time() - meta.get("downloaded_at", 0)
                if age < self._cache_ttl:
                    need_download = False
            except (json.JSONDecodeError, KeyError):
                pass

        if need_download:
            self._download(dat_path, meta_path)

        if dat_path.exists():
            self._parse(dat_path)

        self._loaded = True
        logger.info("Airline DB loaded: %d airlines", len(self._by_icao))

    def _download(self, dat_path: Path, meta_path: Path):
        logger.info("Downloading airline database...")
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(DB_URL)
                resp.raise_for_status()
                dat_path.write_bytes(resp.content)
                meta_path.write_text(json.dumps({
                    "downloaded_at": time.time(),
                    "url": DB_URL,
                }))
                logger.info("Airline database downloaded")
        except Exception as e:
            logger.warning("Failed to download airline DB: %s", e)

    def _parse(self, dat_path: Path):
        """Parse the OpenFlights airlines.dat CSV format.

        Columns: ID, Name, Alias, IATA, ICAO, Callsign, Country, Active
        """
        try:
            text = dat_path.read_text(encoding="utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            for row in reader:
                if len(row) < 8:
                    continue

                name = row[1].strip()
                iata = row[3].strip() if row[3].strip() != "\\N" else None
                icao = row[4].strip() if row[4].strip() != "\\N" else None
                radio_callsign = row[5].strip() if row[5].strip() != "\\N" else None
                active = row[7].strip()

                if not icao or active != "Y":
                    continue

                self._by_icao[icao] = AirlineInfo(
                    name=name,
                    icao_code=icao,
                    iata_code=iata if iata and len(iata) == 2 else None,
                    callsign_name=radio_callsign,
                )
        except Exception as e:
            logger.warning("Failed to parse airline DB: %s", e)
