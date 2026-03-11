"""LED-appropriate color palette.

Colors are tuned for HUB75 RGB LED matrices — bright, saturated values
that read well at low pixel densities.
"""

# Primary palette
AMBER = (255, 191, 0)
GREEN = (0, 255, 64)
CYAN = (0, 200, 255)
RED = (255, 40, 40)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
ORANGE = (255, 128, 0)
BLUE = (60, 120, 255)
MAGENTA = (255, 0, 200)

# Dim variants (for secondary / background text)
DIM_WHITE = (100, 100, 100)
DIM_AMBER = (120, 90, 0)
DIM_GREEN = (0, 100, 30)
DIM_CYAN = (0, 80, 100)

# Semantic aliases
FLIGHT_COLOR = CYAN
WEATHER_COLOR = AMBER
CALENDAR_COLOR = GREEN
CLOCK_COLOR = WHITE
LABEL_COLOR = DIM_WHITE
SEPARATOR_COLOR = (40, 40, 40)
BG_COLOR = (0, 0, 0)
