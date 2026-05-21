from datetime import datetime, timezone


def format_issue_time_utc(issue_time_text):
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
    if ceiling_ft is None:
        ceiling_ft = float("inf")
    if visibility_km is None:
        visibility_km = float("inf")

    # UK/European Colour State criteria (cloud ft / visibility km)
    # Boundaries are inclusive to the better category (handled by < checks).
    if ceiling_ft < 200 or visibility_km < 0.8:
        return "RED"
    elif ceiling_ft < 300 or visibility_km < 1.6:
        return "AMB"
    elif ceiling_ft < 500 or visibility_km < 2.5:
        return "YLO2"
    elif ceiling_ft < 700 or visibility_km < 3.7:
        return "YLO1"
    elif ceiling_ft < 1500 or visibility_km < 5:
        return "GRN"
    elif ceiling_ft < 2500 or visibility_km < 8:
        return "WHT"
    else:
        return "BLU"


def parse_conditions(feature):
    """Extract ceiling, visibility, and ceiling source from a TAF feature."""
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
