"""Pixel-art icons for LED matrix display.

Each icon is a list of rows, where each row is a list of RGB tuples.
(0, 0, 0) = transparent / off.  Icons are 8x8 or 5x5 pixels.
"""

from typing import Dict, List, Tuple

# Type alias
Pixel = Tuple[int, int, int]
Icon = List[List[Pixel]]

OFF = (0, 0, 0)
W = (255, 255, 255)
C = (0, 200, 255)     # cyan / flight
A = (255, 191, 0)     # amber / weather
G = (0, 255, 64)      # green / calendar
R = (255, 40, 40)     # red / alert
Y = (255, 255, 0)     # yellow / sun
O = (255, 128, 0)     # orange
B = (60, 120, 255)    # blue

# ── 8x8 icons ──────────────────────────────────────────

PLANE_8: Icon = [
    [OFF, OFF, OFF, C,   OFF, OFF, OFF, OFF],
    [OFF, OFF, C,   C,   OFF, OFF, OFF, OFF],
    [OFF, C,   C,   C,   OFF, OFF, OFF, OFF],
    [C,   C,   C,   C,   C,   C,   C,   C  ],
    [OFF, OFF, C,   C,   C,   C,   C,   C  ],
    [OFF, OFF, OFF, C,   OFF, OFF, OFF, OFF],
    [OFF, OFF, C,   C,   C,   OFF, OFF, OFF],
    [OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF],
]

SUN_8: Icon = [
    [OFF, OFF, Y,   OFF, OFF, Y,   OFF, OFF],
    [OFF, OFF, OFF, Y,   Y,   OFF, OFF, OFF],
    [Y,   OFF, Y,   Y,   Y,   Y,   OFF, Y  ],
    [OFF, Y,   Y,   Y,   Y,   Y,   Y,   OFF],
    [OFF, Y,   Y,   Y,   Y,   Y,   Y,   OFF],
    [Y,   OFF, Y,   Y,   Y,   Y,   OFF, Y  ],
    [OFF, OFF, OFF, Y,   Y,   OFF, OFF, OFF],
    [OFF, OFF, Y,   OFF, OFF, Y,   OFF, OFF],
]

CLOUD_8: Icon = [
    [OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF],
    [OFF, OFF, W,   W,   OFF, OFF, OFF, OFF],
    [OFF, W,   W,   W,   W,   OFF, OFF, OFF],
    [OFF, W,   W,   W,   W,   W,   W,   OFF],
    [W,   W,   W,   W,   W,   W,   W,   W  ],
    [W,   W,   W,   W,   W,   W,   W,   W  ],
    [OFF, W,   W,   W,   W,   W,   W,   OFF],
    [OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF],
]

RAIN_8: Icon = [
    [OFF, OFF, W,   W,   W,   OFF, OFF, OFF],
    [OFF, W,   W,   W,   W,   W,   OFF, OFF],
    [W,   W,   W,   W,   W,   W,   W,   OFF],
    [W,   W,   W,   W,   W,   W,   W,   OFF],
    [OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF],
    [OFF, B,   OFF, B,   OFF, B,   OFF, OFF],
    [B,   OFF, B,   OFF, B,   OFF, OFF, OFF],
    [OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF],
]

CALENDAR_8: Icon = [
    [OFF, G,   G,   G,   G,   G,   G,   OFF],
    [G,   G,   G,   G,   G,   G,   G,   G  ],
    [G,   OFF, OFF, OFF, OFF, OFF, OFF, G  ],
    [G,   OFF, W,   OFF, W,   OFF, W,   G  ],
    [G,   OFF, OFF, OFF, OFF, OFF, OFF, G  ],
    [G,   OFF, W,   OFF, W,   OFF, OFF, G  ],
    [G,   OFF, OFF, OFF, OFF, OFF, OFF, G  ],
    [OFF, G,   G,   G,   G,   G,   G,   OFF],
]

CLOCK_8: Icon = [
    [OFF, OFF, W,   W,   W,   W,   OFF, OFF],
    [OFF, W,   OFF, OFF, OFF, OFF, W,   OFF],
    [W,   OFF, OFF, OFF, W,   OFF, OFF, W  ],
    [W,   OFF, OFF, OFF, W,   OFF, OFF, W  ],
    [W,   OFF, OFF, W,   W,   OFF, OFF, W  ],
    [W,   OFF, OFF, OFF, OFF, OFF, OFF, W  ],
    [OFF, W,   OFF, OFF, OFF, OFF, W,   OFF],
    [OFF, OFF, W,   W,   W,   W,   OFF, OFF],
]

# ── 5x5 compact icons ──────────────────────────────────

PLANE_5: Icon = [
    [OFF, OFF, C,   OFF, OFF],
    [OFF, C,   C,   OFF, OFF],
    [C,   C,   C,   C,   C  ],
    [OFF, OFF, C,   C,   C  ],
    [OFF, C,   C,   C,   OFF],
]

SUN_5: Icon = [
    [OFF, Y,   OFF, Y,   OFF],
    [Y,   Y,   Y,   Y,   Y  ],
    [OFF, Y,   Y,   Y,   OFF],
    [Y,   Y,   Y,   Y,   Y  ],
    [OFF, Y,   OFF, Y,   OFF],
]

CALENDAR_5: Icon = [
    [G,   G,   G,   G,   G  ],
    [G,   OFF, OFF, OFF, G  ],
    [G,   OFF, W,   OFF, G  ],
    [G,   OFF, OFF, OFF, G  ],
    [G,   G,   G,   G,   G  ],
]

# Lookup tables
ICONS_8: Dict[str, Icon] = {
    "plane": PLANE_8,
    "sun": SUN_8,
    "cloud": CLOUD_8,
    "rain": RAIN_8,
    "calendar": CALENDAR_8,
    "clock": CLOCK_8,
}

ICONS_5: Dict[str, Icon] = {
    "plane": PLANE_5,
    "sun": SUN_5,
    "calendar": CALENDAR_5,
}


def get_icon(name: str, size: int = 8) -> Icon:
    """Get an icon by name and size (8 or 5)."""
    lookup = ICONS_8 if size == 8 else ICONS_5
    return lookup.get(name, ICONS_8.get(name, []))
