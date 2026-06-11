import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "input.csv")
DB_PATH = os.path.join(BASE_DIR, "prices.db")
CLOCK_ASSET_DIR = os.path.join(BASE_DIR, "static", "digits")
BACKGROUND_ASSET_DIR = os.path.join(BASE_DIR, "static", "bg")

# Clock day/night mode (24h format)
DAY_START_HOUR = 6
DAY_START_MINUTE = 0
DAY_END_HOUR = 21
DAY_END_MINUTE = 0

# Portfolio polling interval (ms) — clock polling is hardcoded in dashboard.js
DATA_REFRESH_INTERVAL_MS = 30000

# Background: "color" | "image" | "video"
#   color — solid BACKGROUND_COLOR only
#   image — static backdrop from BACKGROUND_IMAGE_FILE
#   video — looped H.264 Base Profile ≤720p (for legacy CPU)
BACKGROUND_TYPE = "color"
BACKGROUND_COLOR = "#000000"
BACKGROUND_IMAGE_FILE = "img_background.jpg"
BACKGROUND_VIDEO_FILE = "video_background.mp4"

# Portfolio table styles
TABLE_WIDGET_WIDTH = "800px"
TABLE_FONT_SIZE = "12px"
TABLE_BACKGROUND_COLOR = "rgba(0, 0, 0, 0.75)"
TABLE_TEXT_DEFAULT_COLOR = "#FFFFFF"
TABLE_HEADER_TEXT_COLOR = "#FFFF00"
TABLE_BORDER_COLOR = "#333333"

# Clock widget digit size and position
CLOCK_DIGIT_WIDTH = "180px"
CLOCK_DIGIT_HEIGHT = "230px"
CLOCK_WIDGET_MARGIN_TOP = "40px"
