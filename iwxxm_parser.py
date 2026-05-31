"""IWXXM XML parser: extracts ceiling, visibility, and convective weather conditions from TAF payloads."""
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import datetime, timezone

from config import IWXXM_NS
from logic import _is_thunderstorm_code, _is_cb_code, _is_tcu_code, get_colour_state, COLOUR_STATE_RANK

ForecastPeriod = namedtuple("ForecastPeriod", [
    "begin",           # datetime (UTC) or None
    "end",             # datetime (UTC) or None
    "change_type",     # "BASE", "TEMPO", "BECMG", "PROB30", "PROB40", ...
    "colour_state",    # "BLU", "WHT", "GRN", etc.
    "rank",            # 0 (RED) .. 6 (BLU)
    "ceiling_ft",      # float or None
    "visibility_km",   # float or None
    "ceiling_source",  # "VV", "BKN", "OVC", or None
    "is_cavok",        # bool
    "has_ts",          # bool: thunderstorm in this period
    "has_cb",          # bool: cumulonimbus in this period
    "has_tcu",         # bool: towering cumulus in this period
])

ParsedConditions = namedtuple("ParsedConditions", [
    "issue_time",
    "forecast_periods",  # list of ForecastPeriod
    "has_ts",
    "has_cb",
    "has_tcu",
    "has_cavok",
    "forecast_available_now",
    "forecast_unavailable_reason",
    "taf_begin",          # ISO 8601 string (UTC) or None
    "taf_end",            # ISO 8601 string (UTC) or None
])


def _uom_to_km(value, uom):
    if value is None:
        return None
    if uom in ("m", "metre", "meter"):
        return value / 1000.0
    if uom in ("km", "kilometre", "kilometer"):
        return value
    if uom in ("[mi_i]", "mi"):
        return value * 1.60934
    return value / 1000.0


def _uom_to_ft(value, uom):
    if value is None:
        return None
    if uom in ("[ft_i]", "ft"):
        return value
    if uom in ("m", "metre", "meter"):
        return value * 3.28084
    return value


def _parse_iso_utc(text):
    if not text:
        return None
    normalized_text = text.strip().replace("Z", "+00:00")
    try:
        parsed_time = datetime.fromisoformat(normalized_text)
    except ValueError:
        return None

    if parsed_time.tzinfo is None:
        parsed_time = parsed_time.replace(tzinfo=timezone.utc)
    return parsed_time.astimezone(timezone.utc)


def _find_has_thunderstorm(root):
    """Extract thunderstorm presence from IWXXM weather elements."""
    weather_paths = (
        ".//iwxxm:weather",
        ".//iwxxm:forecastWeather",
        ".//iwxxm:AerodromeForecastWeather",
    )
    xlink_href_key = f"{{{IWXXM_NS['xlink']}}}href"
    xlink_title_key = f"{{{IWXXM_NS['xlink']}}}title"

    for path in weather_paths:
        for weather_elem in root.findall(path, IWXXM_NS):
            candidates = []
            candidates.extend(weather_elem.attrib.values())
            candidates.append(weather_elem.get(xlink_href_key, ""))
            candidates.append(weather_elem.get(xlink_title_key, ""))
            candidates.append(weather_elem.text or "")

            for candidate in candidates:
                if _is_thunderstorm_code(candidate):
                    return True
    return False


def _make_base_period(template, begin, end):
    """Return a new BASE-typed ForecastPeriod whose conditions are copied from *template*."""
    return ForecastPeriod(
        begin=begin, end=end, change_type="BASE",
        colour_state=template.colour_state, rank=template.rank,
        ceiling_ft=template.ceiling_ft, visibility_km=template.visibility_km,
        ceiling_source=template.ceiling_source, is_cavok=template.is_cavok,
        has_ts=template.has_ts, has_cb=template.has_cb, has_tcu=template.has_tcu,
    )


def _apply_becmg_base_splits(periods):
    """Split the BASE period at BECMG boundaries for correct time-slider filtering.

    For each BECMG (sorted by end time):
      - The pre-BECMG BASE segment is kept running up to becmg.end, so that
        during the transition window the original (pessimistic) conditions are
        still present for worst-state computation.
      - A synthetic BASE period is inserted from becmg.end onwards carrying the
        BECMG's completed conditions.

    BECMG periods with missing or zero-length time bounds are skipped (no split).
    Returns a new list; the input is not modified.
    To disable entirely: set BECMG_BASE_SPLIT = False in config.py.
    """
    valid_becmgs = sorted(
        [
            p for p in periods
            if p.change_type == "BECOMING"
            and p.begin is not None
            and p.end is not None
            and p.end > p.begin
            # Only split on BECMGs that carry explicit vis/ceiling information.
            # Wind-only BECMGs (no vis, no ceiling, not CAVOK) do not define a
            # new visibility/ceiling baseline, so they must not trigger a split.
            and (p.visibility_km is not None or p.ceiling_ft is not None or p.is_cavok)
        ],
        key=lambda p: p.end,
    )
    if not valid_becmgs:
        return list(periods)

    base_periods = [p for p in periods if p.change_type == "BASE"]
    if not base_periods:
        return list(periods)

    base = base_periods[0]
    all_becmg = [p for p in periods if p.change_type == "BECOMING"]
    other = [p for p in periods if p.change_type not in ("BASE", "BECOMING")]

    result_bases = []
    current_start = base.begin
    current_conditions = base

    for becmg in valid_becmgs:
        if current_start is None:
            break
        # BECMG already completed before the current segment starts — just advance.
        if becmg.end <= current_start:
            current_conditions = becmg
            current_start = becmg.end
            continue
        # Emit the pre-BECMG base segment up to becmg.end.
        seg_end = becmg.end if (base.end is None or becmg.end <= base.end) else base.end
        if seg_end > current_start:
            result_bases.append(_make_base_period(current_conditions, current_start, seg_end))
        current_conditions = becmg
        current_start = becmg.end

    # Emit the tail from the last BECMG.end to the end of the TAF.
    if current_start is not None and base.end is not None and current_start < base.end:
        result_bases.append(_make_base_period(current_conditions, current_start, base.end))

    # Preserve any unexpected additional base periods beyond the first.
    return result_bases + base_periods[1:] + all_becmg + other


def _parse_single_period(forecast_el, taf_begin, taf_end):
    """Parse one MeteorologicalAerodromeForecast element into a ForecastPeriod."""
    change_indicator = (forecast_el.get("changeIndicator") or "").strip()
    change_type = change_indicator if change_indicator else "BASE"

    # Time bounds: use inline phenomenonTime TimePeriod if present, else TAF valid period.
    begin, end = taf_begin, taf_end
    time_period = forecast_el.find("iwxxm:phenomenonTime/gml:TimePeriod", IWXXM_NS)
    if time_period is not None:
        b_el = time_period.find("gml:beginPosition", IWXXM_NS)
        e_el = time_period.find("gml:endPosition", IWXXM_NS)
        begin = _parse_iso_utc((b_el.text or "") if b_el is not None else "") or taf_begin
        end = _parse_iso_utc((e_el.text or "") if e_el is not None else "") or taf_end

    is_cavok = (forecast_el.get("cloudAndVisibilityOK") or "").strip().lower() == "true"
    if is_cavok:
        return ForecastPeriod(
            begin=begin, end=end, change_type=change_type,
            colour_state="BLU", rank=COLOUR_STATE_RANK["BLU"],
            ceiling_ft=None, visibility_km=None, ceiling_source=None, is_cavok=True,
            has_ts=False, has_cb=False, has_tcu=False,
        )

    # Visibility
    vis_km = None
    vis_el = forecast_el.find("iwxxm:prevailingVisibility", IWXXM_NS)
    if vis_el is not None and (vis_el.text or "").strip():
        try:
            vis_km = _uom_to_km(float(vis_el.text.strip()), vis_el.get("uom", "m"))
        except ValueError:
            pass

    # Ceiling: vertical visibility takes precedence over cloud layers.
    ceiling_ft = None
    ceiling_source = None
    vv_el = forecast_el.find(".//iwxxm:verticalVisibility", IWXXM_NS)
    if vv_el is not None and (vv_el.text or "").strip():
        try:
            vv_ft = _uom_to_ft(float(vv_el.text.strip()), vv_el.get("uom", "[ft_i]"))
            if vv_ft is not None:
                ceiling_ft, ceiling_source = vv_ft, "VV"
        except ValueError:
            pass

    # BKN/OVC cloud layers — lowest base wins.
    for layer in forecast_el.findall(".//iwxxm:CloudLayer", IWXXM_NS):
        amt_el = layer.find("iwxxm:amount", IWXXM_NS)
        base_el = layer.find("iwxxm:base", IWXXM_NS)
        if amt_el is None or base_el is None or not (base_el.text or "").strip():
            continue
        amt_href = amt_el.get(f"{{{IWXXM_NS['xlink']}}}href", "")
        amt_code = amt_href.rsplit("/", 1)[-1].upper() if amt_href else ""
        if amt_code not in {"BKN", "OVC"}:
            continue
        try:
            base_ft = _uom_to_ft(float(base_el.text.strip()), base_el.get("uom", "[ft_i]"))
        except ValueError:
            continue
        if base_ft is not None and (ceiling_ft is None or base_ft < ceiling_ft):
            ceiling_ft, ceiling_source = base_ft, amt_code

    colour_state = get_colour_state(ceiling_ft, vis_km)

    # Convective weather detection within this period.
    has_ts = _find_has_thunderstorm(forecast_el)
    has_cb = False
    has_tcu = False
    _xlink_href_key = f"{{{IWXXM_NS['xlink']}}}href"
    for _layer in forecast_el.findall(".//iwxxm:CloudLayer", IWXXM_NS):
        _ct = _layer.find("iwxxm:cloudType", IWXXM_NS)
        if _ct is None:
            continue
        _type = (_ct.text or "").strip() or _ct.get(_xlink_href_key, "").rsplit("/", 1)[-1]
        if _is_cb_code(_type):
            has_cb = True
        if _is_tcu_code(_type):
            has_tcu = True

    return ForecastPeriod(
        begin=begin, end=end, change_type=change_type,
        colour_state=colour_state, rank=COLOUR_STATE_RANK[colour_state],
        ceiling_ft=ceiling_ft, visibility_km=vis_km,
        ceiling_source=ceiling_source, is_cavok=False,
        has_ts=has_ts, has_cb=has_cb, has_tcu=has_tcu,
    )


def parse_iwxxm_conditions(xml_text):
    """Parse IWXXM XML and return a ParsedConditions with per-period forecast data."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ParsedConditions(
            issue_time=None, forecast_periods=[],
            has_ts=False, has_cb=False, has_tcu=False,
            has_cavok=False,
            forecast_available_now=False, forecast_unavailable_reason="TAF data unavailable",
        )

    issue_time = None
    issue_time_elem = root.find(".//iwxxm:issueTime/gml:TimeInstant/gml:timePosition", IWXXM_NS)
    if issue_time_elem is not None and (issue_time_elem.text or "").strip():
        issue_time = issue_time_elem.text.strip()

    taf_begin = None
    taf_end = None
    valid_from_elem = root.find(".//iwxxm:validPeriod/gml:TimePeriod/gml:beginPosition", IWXXM_NS)
    valid_to_elem = root.find(".//iwxxm:validPeriod/gml:TimePeriod/gml:endPosition", IWXXM_NS)
    if valid_from_elem is not None:
        taf_begin = _parse_iso_utc(valid_from_elem.text)
    if valid_to_elem is not None:
        taf_end = _parse_iso_utc(valid_to_elem.text)

    forecast_available_now = bool(taf_begin and taf_end)
    forecast_unavailable_reason = None if forecast_available_now else "No current TAF"

    # Parse each forecast period independently; colour state is computed per period.
    forecast_periods = [
        _parse_single_period(el, taf_begin, taf_end)
        for el in root.findall(".//iwxxm:MeteorologicalAerodromeForecast", IWXXM_NS)
    ]

    forecast_periods = _apply_becmg_base_splits(forecast_periods)

    has_cavok = any(p.is_cavok for p in forecast_periods)
    has_ts = any(p.has_ts for p in forecast_periods)
    has_cb = any(p.has_cb for p in forecast_periods)
    has_tcu = any(p.has_tcu for p in forecast_periods)

    return ParsedConditions(
        issue_time=issue_time,
        forecast_periods=forecast_periods,
        has_ts=has_ts,
        has_cb=has_cb,
        has_tcu=has_tcu,
        has_cavok=has_cavok,
        forecast_available_now=forecast_available_now,
        forecast_unavailable_reason=forecast_unavailable_reason,
        taf_begin=taf_begin.isoformat() if taf_begin else None,
        taf_end=taf_end.isoformat() if taf_end else None,
    )
