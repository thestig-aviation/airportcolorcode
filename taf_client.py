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
    issue_time=None, ceiling_ft=None, visibility_km=None,
    has_ts=False, has_cb=False, has_tcu=False,
    ceiling_source=None, has_cavok=False,
    forecast_available_now=False, forecast_unavailable_reason="No current TAF",
)

_UNAVAILABLE_CONDITIONS = ParsedConditions(
    issue_time=None, ceiling_ft=None, visibility_km=None,
    has_ts=False, has_cb=False, has_tcu=False,
    ceiling_source=None, has_cavok=False,
    forecast_available_now=False, forecast_unavailable_reason="TAF data unavailable",
)


def _apply_parsed_properties(properties, conditions):
    """Write a ParsedConditions namedtuple onto a feature properties dict."""
    properties["parsedIssueTime"] = conditions.issue_time
    properties["parsedCeilingFt"] = conditions.ceiling_ft
    properties["parsedVisibilityKm"] = conditions.visibility_km
    properties["parsedHasTs"] = conditions.has_ts
    properties["parsedHasCb"] = conditions.has_cb
    properties["parsedHasTcu"] = conditions.has_tcu
    properties["parsedCeilingSource"] = conditions.ceiling_source
    properties["parsedHasCavok"] = conditions.has_cavok
    properties["parsedForecastAvailableNow"] = conditions.forecast_available_now
    properties["parsedForecastUnavailableReason"] = conditions.forecast_unavailable_reason


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
