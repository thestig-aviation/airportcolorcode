"""TAF data retrieval: fetches the full airport list and per-airport IWXXM payloads concurrently."""
import requests
from concurrent.futures import ThreadPoolExecutor

from config import REQUEST_TIMEOUT_SECONDS, TAF_API_URL
from iwxxm_parser import ParsedConditions, parse_iwxxm_conditions


def fetch_taf_data():
    response = requests.get(
        TAF_API_URL,
        params={"f": "json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


_NO_TAF_CONDITIONS = ParsedConditions(
    issue_time=None, forecast_periods=[],
    has_ts=False, has_cb=False, has_tcu=False,
    has_cavok=False,
    forecast_available_now=False, forecast_unavailable_reason="No current TAF",
    taf_begin=None, taf_end=None,
)

_UNAVAILABLE_CONDITIONS = ParsedConditions(
    issue_time=None, forecast_periods=[],
    has_ts=False, has_cb=False, has_tcu=False,
    has_cavok=False,
    forecast_available_now=False, forecast_unavailable_reason="TAF data unavailable",
    taf_begin=None, taf_end=None,
)


def _apply_parsed_properties(properties, conditions):
    """Write a ParsedConditions namedtuple onto a feature properties dict."""
    periods = conditions.forecast_periods

    # Derive worst-case ceiling and visibility across all periods for popup display.
    all_ceilings = [(p.ceiling_ft, p.ceiling_source) for p in periods if p.ceiling_ft is not None]
    all_vis = [p.visibility_km for p in periods if p.visibility_km is not None]
    if all_ceilings:
        min_ceil_ft, min_ceil_source = min(all_ceilings, key=lambda x: x[0])
    else:
        min_ceil_ft, min_ceil_source = None, None

    properties["parsedIssueTime"] = conditions.issue_time
    properties["parsedCeilingFt"] = min_ceil_ft
    properties["parsedVisibilityKm"] = min(all_vis) if all_vis else None
    properties["parsedCeilingSource"] = min_ceil_source
    properties["parsedHasTs"] = conditions.has_ts
    properties["parsedHasCb"] = conditions.has_cb
    properties["parsedHasTcu"] = conditions.has_tcu
    properties["parsedHasCavok"] = conditions.has_cavok
    properties["parsedForecastAvailableNow"] = conditions.forecast_available_now
    properties["parsedForecastUnavailableReason"] = conditions.forecast_unavailable_reason
    properties["parsedTafBegin"] = conditions.taf_begin
    properties["parsedTafEnd"] = conditions.taf_end
    properties["parsedForecastPeriods"] = [
        {
            "begin": p.begin.isoformat() if p.begin else None,
            "end": p.end.isoformat() if p.end else None,
            "changeType": p.change_type,
            "colourState": p.colour_state,
            "rank": p.rank,
            "ceilingFt": p.ceiling_ft,
            "visibilityKm": p.visibility_km,
            "ceilingSource": p.ceiling_source,
            "isCavok": p.is_cavok,
            "hasTs": p.has_ts,
            "hasCb": p.has_cb,
            "hasTcu": p.has_tcu,
        }
        for p in periods
    ]


def _fetch_single_airport(session, feature):
    """Fetch the IWXXM payload for a single airport and write parsed conditions to its properties dict."""
    properties = feature.get("properties", {})
    icao = properties.get("ICAO") or properties.get("stationIdentification")
    if not icao:
        return
    try:
        response = session.get(
            f"{TAF_API_URL}/{icao}",
            params={"f": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 204:
            _apply_parsed_properties(properties, _NO_TAF_CONDITIONS)
            return
        response.raise_for_status()
        _apply_parsed_properties(properties, parse_iwxxm_conditions(response.text))
    except requests.RequestException:
        _apply_parsed_properties(properties, _UNAVAILABLE_CONDITIONS)


def enrich_features_with_iwxxm(features):
    """Fetch per-location IWXXM payloads concurrently and attach parsed conditions to each feature."""
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(lambda f: _fetch_single_airport(session, f), features))
