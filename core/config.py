"""UI configuration constants and color definitions.
"""

# Grid and sizing
CELL_SIZE = 120  # Even larger
GRID_W = 6
GRID_H = 6
STATUS_BAR_HEIGHT = 40
STATS_PANEL_WIDTH = 320

# Derived sizes
WIDTH = CELL_SIZE * GRID_W + 80 + STATS_PANEL_WIDTH
HEIGHT = CELL_SIZE * GRID_H + 400 + STATUS_BAR_HEIGHT

# Colors
BLACK = (20, 20, 30)
WHITE = (240, 240, 240)
GRAY = (60, 60, 80)
BLUE = (80, 180, 255)
GREEN = (80, 220, 120)
RED = (255, 80, 80)
YELLOW = (255, 220, 80)
ROOM_BORDER = (180, 180, 220)
CONNECTION = (60, 60, 120)
