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

# Dim variants — bright enough to read clearly on LED panels.
# Values below ~80 per channel are barely visible on most HUB75 matrices.
DIM_WHITE = (140, 140, 140)
DIM_AMBER = (160, 120, 0)
DIM_GREEN = (0, 140, 45)
DIM_CYAN = (0, 130, 160)

# Semantic aliases
FLIGHT_COLOR = CYAN
WEATHER_COLOR = AMBER
CALENDAR_COLOR = GREEN
CLOCK_COLOR = WHITE
LABEL_COLOR = DIM_WHITE
SEPARATOR_COLOR = (60, 60, 60)
BG_COLOR = (0, 0, 0)

# Sleep / idle screen — very dim so the display is unobtrusive at night
SLEEP_CLOCK_COLOR = (50, 50, 70)   # dim blue-white
SLEEP_DATE_COLOR  = (45, 30, 0)    # dim amber
