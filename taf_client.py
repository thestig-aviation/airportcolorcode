import requests

from config import REQUEST_TIMEOUT_SECONDS, TAF_API_URL
from iwxxm_parser import parse_iwxxm_conditions


def fetch_taf_data():
    response = requests.get(
        TAF_API_URL,
        params={"f": "json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def enrich_features_with_iwxxm(features):
    """Fetch per-location IWXXM payload and attach parsed ceiling/visibility to each feature."""
    session = requests.Session()

    for feature in features:
        properties = feature.get("properties", {})
        icao = properties.get("ICAO") or properties.get("stationIdentification")
        if not icao:
            continue

        try:
            response = session.get(
                f"{TAF_API_URL}/{icao}",
                params={"f": "json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 204:
                properties["parsedIssueTime"] = None
                properties["parsedCeilingFt"] = None
                properties["parsedVisibilityKm"] = None
                properties["parsedHasTs"] = False
                properties["parsedHasCb"] = False
                properties["parsedHasTcu"] = False
                properties["parsedCeilingSource"] = None
                properties["parsedHasCavok"] = False
                properties["parsedForecastAvailableNow"] = False
                properties["parsedForecastUnavailableReason"] = "No current TAF"
                continue

            response.raise_for_status()
            (
                issue_time,
                ceiling_ft,
                visibility_km,
                has_ts,
                has_cb,
                has_tcu,
                ceiling_source,
                has_cavok,
                forecast_available_now,
                forecast_unavailable_reason,
            ) = parse_iwxxm_conditions(response.text)
            properties["parsedIssueTime"] = issue_time
            properties["parsedCeilingFt"] = ceiling_ft
            properties["parsedVisibilityKm"] = visibility_km
            properties["parsedHasTs"] = has_ts
            properties["parsedHasCb"] = has_cb
            properties["parsedHasTcu"] = has_tcu
            properties["parsedCeilingSource"] = ceiling_source
            properties["parsedHasCavok"] = has_cavok
            properties["parsedForecastAvailableNow"] = forecast_available_now
            properties["parsedForecastUnavailableReason"] = forecast_unavailable_reason
        except requests.RequestException:
            properties["parsedIssueTime"] = None
            properties["parsedCeilingFt"] = None
            properties["parsedVisibilityKm"] = None
            properties["parsedHasTs"] = False
            properties["parsedHasCb"] = False
            properties["parsedHasTcu"] = False
            properties["parsedCeilingSource"] = None
            properties["parsedHasCavok"] = False
            properties["parsedForecastAvailableNow"] = False
            properties["parsedForecastUnavailableReason"] = "TAF data unavailable"
