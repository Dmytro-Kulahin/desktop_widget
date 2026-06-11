import os

# ==============================================================================
# BASE DIRECTORY AND STORAGE PATHS
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "input.csv")
DB_PATH = os.path.join(BASE_DIR, "prices.db")
CLOCK_ASSET_DIR = os.path.join(BASE_DIR, "static", "digits")
BACKGROUND_ASSET_DIR = os.path.join(BASE_DIR, "static", "bg")

# ==============================================================================
# DAY/NIGHT CLOCK MODE SETTINGS (24-hour format)
# ==============================================================================
DAY_START_HOUR = 6      # Day starts
DAY_START_MINUTE = 00   # Day starts
DAY_END_HOUR = 21       # Night starts at
DAY_END_MINUTE = 00     # Night starts at

# ==============================================================================
# SYSTEM ENGINE SETTINGS
# ==============================================================================
DATA_REFRESH_INTERVAL_MS = 30000

# ==============================================================================
# VISUAL LOOK AND FEEL CONFIGURATION (COSMETIC ENGINE)
# ==============================================================================
# Available BACKGROUND_TYPE options:
# 1. "color" -> Zero-overhead mode. Completely ignores media assets. Uses BACKGROUND_COLOR.
# 2. "image" -> Static backdrop. Loads a high-quality uncompressed image from BACKGROUND_IMAGE_FILE.
# 3. "video" -> Hardware-accelerated dynamic backdrop. Plays BACKGROUND_VIDEO_FILE in a loop.
#               WARNING: Video file must be strictly encoded in H.264 (Base Profile) 
#               at 480p/720p max to prevent 100% CPU lock on legacy single-core hardware.
BACKGROUND_TYPE = "color"
BACKGROUND_COLOR = "#000000"
BACKGROUND_IMAGE_FILE = "img_background.jpg"
BACKGROUND_VIDEO_FILE = "video_background.mp4"

# ==============================================================================
# PORTFOLIO TABLE WIDGET STYLES
# ==============================================================================
TABLE_WIDGET_WIDTH = "800px"
TABLE_FONT_SIZE = "12px"
TABLE_BACKGROUND_COLOR = "rgba(0, 0, 0, 0.75)"
TABLE_TEXT_DEFAULT_COLOR = "#FFFFFF"
TABLE_HEADER_TEXT_COLOR = "#FFFF00"
TABLE_BORDER_COLOR = "#333333"

# ==============================================================================
# 7-SEGMENT CLOCK WIDGET STYLES
# ==============================================================================


CLOCK_DIGIT_WIDTH = "180px"
CLOCK_DIGIT_HEIGHT = "230px"
CLOCK_WIDGET_MARGIN_TOP = "40px"