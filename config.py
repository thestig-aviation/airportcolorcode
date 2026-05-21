from pathlib import Path

TAF_API_URL = "https://aviation.met.no/collections/taf/locations"
REQUEST_TIMEOUT_SECONDS = 20

CB_ICON_LOCAL_NAME = "cb_symbol.png"
TCU_ICON_LOCAL_NAME = "tcu_symbol.png"

BASE_DIR = Path(__file__).resolve().parent
CB_ICON_PATH = BASE_DIR / CB_ICON_LOCAL_NAME
TCU_ICON_PATH = BASE_DIR / TCU_ICON_LOCAL_NAME
DEFAULT_OUTPUT_FILE = BASE_DIR / "airport_color_codes.html"

IWXXM_NS = {
    "iwxxm": "http://icao.int/iwxxm/3.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "xlink": "http://www.w3.org/1999/xlink",
}

COLOUR_STATE_COLORS = {
    "BLU": "#0000FF",
    "WHT": "#FFFFFF",
    "GRN": "#00A000",
    "YLO1": "#FFF200",
    "YLO2": "#FFC000",
    "AMB": "#FF8000",
    "RED": "#FF0000",
}
