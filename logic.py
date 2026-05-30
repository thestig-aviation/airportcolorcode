"""Business logic: colour state rules, convective weather detection, symbol priority, and forecast display value generation."""
from datetime import datetime, timezone
import re

from config import COLOUR_STATE_COLORS, UNAVAILABLE_COLOR

# Numeric rank for each colour state: higher = better conditions.
COLOUR_STATE_RANK = {"RED": 0, "AMB": 1, "YLO2": 2, "YLO1": 3, "GRN": 4, "WHT": 5, "BLU": 6}

# Ordered threshold table used by get_colour_state.
# Each entry: (ceiling_ft_threshold, visibility_km_threshold, state).
_COLOUR_STATE_THRESHOLDS = [
    (200,  0.8,  "RED"),
    (300,  1.6,  "AMB"),
    (500,  2.5,  "YLO2"),
    (700,  3.7,  "YLO1"),
    (1500, 5.0,  "GRN"),
    (2500, 8.0,  "WHT"),
]


def _is_thunderstorm_code(value):
    """Check if a weather code value indicates thunderstorms (TS/TSRA/VCTS/+TSRA/thunder)."""
    if not value:
        return False

    normalized_value = value.strip().upper()
    if not normalized_value:
        return False

    if "THUNDER" in normalized_value:
        return True

    # Handle common codes: TS, TSRA, VCTS, +TSRA, -TSRA, etc.
    return bool(re.search(r"(^|[^A-Z0-9])TS([A-Z0-9]{0,5})([^A-Z0-9]|$)", normalized_value))


def _is_cb_code(value):
    """Check if a cloud type or weather code indicates cumulonimbus (CB)."""
    if not value:
        return False

    normalized_value = value.strip().upper()
    return normalized_value == "CB" or "CUMULONIMBUS" in normalized_value


def _is_tcu_code(value):
    """Check if a cloud type or weather code indicates towering cumulus (TCU)."""
    if not value:
        return False

    normalized_value = value.strip().upper()
    return normalized_value == "TCU" or "TOWERING" in normalized_value


def get_priority_convective_symbol(has_ts, has_cb, has_tcu):
    """Determine which convective symbol should be displayed.
    
    Priority order: TS > CB > TCU
    Returns: "TS", "CB", "TCU", or None
    """
    if has_ts:
        return "TS"
    elif has_cb:
        return "CB"
    elif has_tcu:
        return "TCU"
    return None


def format_issue_time_utc(issue_time_text):
    """Format an ISO 8601 issue time string as HH:MM UTC. Returns None if input is absent."""
    if not issue_time_text:
        return None

    normalized_text = issue_time_text.strip().replace("Z", "+00:00")
    try:
        parsed_time = datetime.fromisoformat(normalized_text)
    except ValueError:
        return issue_time_text.strip()

    if parsed_time.tzinfo is None:
        parsed_time = parsed_time.replace(tzinfo=timezone.utc)

    return parsed_time.astimezone(timezone.utc).strftime("%H:%M")


def get_colour_state(ceiling_ft, visibility_km):
    """Return the UK/European aviation colour state for given ceiling and visibility.

    Uses _COLOUR_STATE_THRESHOLDS for a table-driven lookup ordered by COLOUR_STATE_RANK.
    None inputs are treated as unlimited (best-case). Ceiling in ft, visibility in km.
    """
    ceiling_ft = float("inf") if ceiling_ft is None else ceiling_ft
    visibility_km = float("inf") if visibility_km is None else visibility_km
    for ceil_thresh, vis_thresh, state in _COLOUR_STATE_THRESHOLDS:
        if ceiling_ft < ceil_thresh or visibility_km < vis_thresh:
            return state
    return "BLU"


def colour_state_hex(state_code):
    """Return the hex fill colour for a colour state code."""
    return COLOUR_STATE_COLORS[state_code]


def parse_conditions(feature):
    """Extract ceiling (ft), visibility (km), and ceiling source from a TAF feature.

    Reads IWXXM-enriched properties (parsedCeilingFt etc.) when available,
    falling back to raw API cloud/visibility fields.
    ceiling_source indicates the layer type that drove the ceiling: "VV", "BKN", or "OVC".
    """
    ceiling_ft = None
    visibility_km = None
    ceiling_source = None

    try:
        properties = feature.get("properties", {})
        parsed_ceiling = properties.get("parsedCeilingFt")
        parsed_visibility = properties.get("parsedVisibilityKm")
        parsed_ceiling_source = properties.get("parsedCeilingSource")
        if parsed_ceiling is not None or parsed_visibility is not None:
            return parsed_ceiling, parsed_visibility, parsed_ceiling_source

        # Visibility in meters, convert to km
        vis_m = properties.get("visibility", {}).get("value")
        if vis_m is not None:
            visibility_km = vis_m / 1000.0

        # Cloud layers - find lowest BKN, OVC, or VV layer
        clouds = properties.get("clouds", [])
        for layer in clouds:
            cover = layer.get("amount", "")
            base = layer.get("base", {}).get("value")
            if cover in ("BKN", "OVC", "VV") and base is not None:
                if ceiling_ft is None or base < ceiling_ft:
                    ceiling_ft = base
                    ceiling_source = cover
    except Exception:
        pass

    return ceiling_ft, visibility_km, ceiling_source


def get_convective_symbol_title(symbol_type):
    """Get the display title for a convective symbol type."""
    titles = {
        "TS": "Thunderstorm (TS) in TAF",
        "CB": "Cumulonimbus (CB) in TAF",
        "TCU": "Towering Cumulus (TCU) in TAF",
    }
    return titles.get(symbol_type, "")


def get_forecast_display_info(forecast_available_now, ceiling_ft, visibility_km, has_cavok):
    """Get color, labels, and display values based on forecast availability and conditions.
    
    Returns tuple: (hex_color, color_label, ceiling_display, visibility_display)
    """
    if forecast_available_now:
        color_code = get_colour_state(ceiling_ft, visibility_km)
        hex_color = COLOUR_STATE_COLORS[color_code]
        cavok_driven = has_cavok and ceiling_ft is None and visibility_km is None
        ceiling_display = "CAVOK" if cavok_driven else (f"{int(ceiling_ft)} ft" if ceiling_ft is not None else "N/A ft")
        visibility_display = "CAVOK" if cavok_driven else (f"{visibility_km} km" if visibility_km is not None else "N/A km")
        color_label = color_code
    else:
        hex_color = UNAVAILABLE_COLOR
        ceiling_display = "Forecast Unavailable"
        visibility_display = "Forecast Unavailable"
        color_label = "Forecast Unavailable"
    
    return hex_color, color_label, ceiling_display, visibility_display

