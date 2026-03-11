from .models import EnrichedFlight


def format_flight(flight: EnrichedFlight, use_unicode: bool = True) -> str:
    """Format an enriched flight into a marquee display string.

    Examples:
        UA1234  SFO -> LAX  Boeing 737-800  5,200ft
        UAL1234  5,200ft  (minimal, no enrichment)
    """
    parts = []

    # Flight identifier
    parts.append(flight.flight_number or flight.callsign or flight.icao24)

    # Route
    if flight.route:
        dep = flight.route.departure_iata or flight.route.departure_icao
        arr = flight.route.arrival_iata or flight.route.arrival_icao
        arrow = "\u2192" if use_unicode else "->"

        if dep and arr:
            # Full route known: "SFO → SLC"
            parts.append(f"{dep} {arrow} {arr}")
        elif dep and not arr:
            # Departure only (in-progress flight): "from SLC"
            parts.append(f"from {dep}")
        elif arr and not dep:
            # Arrival only: "→ SLC"
            parts.append(f"{arrow} {arr}")

    # Aircraft type
    if flight.aircraft_info:
        type_str = _format_aircraft_type(flight.aircraft_info)
        if type_str:
            parts.append(type_str)

    # Altitude
    if flight.altitude_feet and not flight.on_ground:
        parts.append(f"{flight.altitude_feet:,}ft")

    return "  ".join(parts)


def _format_aircraft_type(info):
    """Pick the best available aircraft type description."""
    # Prefer the typecode-based friendly name
    if info.typecode and info.typecode in COMMON_TYPES:
        return COMMON_TYPES[info.typecode]

    # Build a display name from manufacturer + model
    if info.model and info.manufacturer:
        model = info.model
        mfr = info.manufacturer
        # If the model already contains the manufacturer name, just use model
        if mfr.lower() in model.lower():
            return model
        # Combine them for readability (e.g. "Cessna" + "182T" -> "Cessna 182T")
        return f"{mfr} {model}"

    # Fall back to just the model
    if info.model:
        return info.model

    # Last resort: just the typecode
    if info.typecode:
        return info.typecode

    return None


# Common ICAO type designators mapped to friendly display names
COMMON_TYPES = {
    "A20N": "Airbus A320neo",
    "A21N": "Airbus A321neo",
    "A306": "Airbus A300-600",
    "A310": "Airbus A310",
    "A318": "Airbus A318",
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A321": "Airbus A321",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A338": "Airbus A330-800neo",
    "A339": "Airbus A330-900neo",
    "A342": "Airbus A340-200",
    "A343": "Airbus A340-300",
    "A345": "Airbus A340-500",
    "A346": "Airbus A340-600",
    "A359": "Airbus A350-900",
    "A35K": "Airbus A350-1000",
    "A388": "Airbus A380",
    "B37M": "Boeing 737 MAX 7",
    "B38M": "Boeing 737 MAX 8",
    "B39M": "Boeing 737 MAX 9",
    "B3XM": "Boeing 737 MAX 10",
    "B712": "Boeing 717",
    "B732": "Boeing 737-200",
    "B733": "Boeing 737-300",
    "B734": "Boeing 737-400",
    "B735": "Boeing 737-500",
    "B736": "Boeing 737-600",
    "B737": "Boeing 737-700",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B744": "Boeing 747-400",
    "B748": "Boeing 747-8",
    "B752": "Boeing 757-200",
    "B753": "Boeing 757-300",
    "B762": "Boeing 767-200",
    "B763": "Boeing 767-300",
    "B764": "Boeing 767-400",
    "B772": "Boeing 777-200",
    "B77L": "Boeing 777-200LR",
    "B773": "Boeing 777-300",
    "B77W": "Boeing 777-300ER",
    "B778": "Boeing 777X-8",
    "B779": "Boeing 777X-9",
    "B788": "Boeing 787-8",
    "B789": "Boeing 787-9",
    "B78X": "Boeing 787-10",
    "BCS1": "Airbus A220-100",
    "BCS3": "Airbus A220-300",
    "C56X": "Cessna Citation Excel",
    "C68A": "Cessna Citation Latitude",
    "CL30": "Bombardier Challenger 300",
    "CL35": "Bombardier Challenger 350",
    "CRJ2": "CRJ-200",
    "CRJ7": "CRJ-700",
    "CRJ9": "CRJ-900",
    "CRJX": "CRJ-1000",
    "DH8D": "Dash 8 Q400",
    "E135": "Embraer ERJ-135",
    "E145": "Embraer ERJ-145",
    "E170": "Embraer E170",
    "E175": "Embraer E175",
    "E190": "Embraer E190",
    "E195": "Embraer E195",
    "E75L": "Embraer E175 Long",
    "E75S": "Embraer E175 Short",
    "E290": "Embraer E190-E2",
    "E295": "Embraer E195-E2",
    "G280": "Gulfstream G280",
    "GALX": "Gulfstream G200",
    "GL5T": "Bombardier Challenger 600",
    "GLF4": "Gulfstream G450",
    "GLF5": "Gulfstream G550",
    "GLF6": "Gulfstream G650",
    "GLEX": "Bombardier Global Express",
    "H25B": "Hawker 800",
    "LJ45": "Learjet 45",
    "LJ60": "Learjet 60",
    "MD11": "MD-11",
    "MD82": "MD-82",
    "MD83": "MD-83",
    "C150": "Cessna 150",
    "C152": "Cessna 152",
    "C172": "Cessna 172",
    "C182": "Cessna 182",
    "C206": "Cessna 206",
    "C208": "Cessna Caravan",
    "C210": "Cessna 210",
    "C25A": "Cessna Citation CJ2",
    "C25B": "Cessna Citation CJ3",
    "C25C": "Cessna Citation CJ4",
    "C510": "Cessna Citation Mustang",
    "C525": "Cessna CitationJet",
    "C550": "Cessna Citation II",
    "C560": "Cessna Citation V",
    "C680": "Cessna Citation Sovereign",
    "C750": "Cessna Citation X",
    "DA40": "Diamond DA40",
    "DA42": "Diamond DA42 Twin Star",
    "DA62": "Diamond DA62",
    "P28A": "Piper Cherokee",
    "PA28": "Piper Cherokee",
    "PA32": "Piper Saratoga",
    "PA34": "Piper Seneca",
    "PA44": "Piper Seminole",
    "PA46": "Piper Malibu",
    "PC12": "Pilatus PC-12",
    "PC24": "Pilatus PC-24",
    "SR20": "Cirrus SR20",
    "SR22": "Cirrus SR22",
    "SF50": "Cirrus Vision Jet",
    "BE20": "Beechcraft King Air 200",
    "BE36": "Beechcraft Bonanza",
    "BE58": "Beechcraft Baron",
    "BE9L": "Beechcraft King Air 90",
    "BE40": "Beechcraft Beechjet 400",
    "B350": "Beechcraft King Air 350",
    "TBM7": "Daher TBM 700",
    "TBM8": "Daher TBM 850",
    "TBM9": "Daher TBM 930",
    "P180": "Piaggio Avanti",
    "C30J": "C-130J Super Hercules",
    "C17": "C-17 Globemaster",
    "F16": "F-16 Fighting Falcon",
    "A10": "A-10 Thunderbolt II",
    "K35R": "KC-135 Stratotanker",
}
