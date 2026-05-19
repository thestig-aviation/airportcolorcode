## Python Code

import requests
import folium
from folium.features import DivIcon
import xml.etree.ElementTree as ET
from pathlib import Path

TAF_API_URL = "https://aviation.met.no/collections/taf/locations"
REQUEST_TIMEOUT_SECONDS = 20
CB_ICON_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Clouds_CL_3.svg/120px-Clouds_CL_3.svg.png"
CB_ICON_LOCAL_NAME = "cb_symbol.png"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_FILE = BASE_DIR / "airport_color_codes.html"

IWXXM_NS = {
    "iwxxm": "http://icao.int/iwxxm/3.0",
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


def fetch_taf_data():
    response = requests.get(
        TAF_API_URL,
        params={"f": "json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


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


def parse_iwxxm_conditions(xml_text):
    """Parse IWXXM XML and return (lowest significant cloud base ft, worst visibility km, has_cb)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None, None, False

    vis_values = []
    for vis in root.findall(".//iwxxm:prevailingVisibility", IWXXM_NS):
        try:
            vis_value = float((vis.text or "").strip())
        except (TypeError, ValueError):
            continue
        vis_km = _uom_to_km(vis_value, vis.get("uom", "m"))
        if vis_km is not None:
            vis_values.append(vis_km)

    significant_amounts = {"SCT", "BKN", "OVC"}
    cloud_bases_ft = []
    has_cb = False
    for layer in root.findall(".//iwxxm:CloudLayer", IWXXM_NS):
        amount_elem = layer.find("iwxxm:amount", IWXXM_NS)
        base_elem = layer.find("iwxxm:base", IWXXM_NS)
        cloud_type_elem = layer.find("iwxxm:cloudType", IWXXM_NS)
        if cloud_type_elem is not None:
            cloud_type_href = cloud_type_elem.get(f"{{{IWXXM_NS['xlink']}}}href", "")
            cloud_type_text = (cloud_type_elem.text or "").strip().upper()
            if cloud_type_href.upper().endswith("/CB") or cloud_type_text == "CB":
                has_cb = True

        if amount_elem is None or base_elem is None or not (base_elem.text or "").strip():
            continue

        amount_href = amount_elem.get(f"{{{IWXXM_NS['xlink']}}}href", "")
        amount_code = amount_href.rsplit("/", 1)[-1].upper() if amount_href else ""
        if amount_code not in significant_amounts:
            continue

        try:
            base_value = float(base_elem.text.strip())
        except ValueError:
            continue
        base_ft = _uom_to_ft(base_value, base_elem.get("uom", "[ft_i]"))
        if base_ft is not None:
            cloud_bases_ft.append(base_ft)

    # Use worst visibility and lowest significant cloud base from the TAF.
    visibility_km = min(vis_values) if vis_values else None
    ceiling_ft = min(cloud_bases_ft) if cloud_bases_ft else None
    return ceiling_ft, visibility_km, has_cb


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
            response.raise_for_status()
            ceiling_ft, visibility_km, has_cb = parse_iwxxm_conditions(response.text)
            properties["parsedCeilingFt"] = ceiling_ft
            properties["parsedVisibilityKm"] = visibility_km
            properties["parsedHasCb"] = has_cb
        except requests.RequestException:
            properties["parsedCeilingFt"] = None
            properties["parsedVisibilityKm"] = None
            properties["parsedHasCb"] = False


def ensure_local_cb_icon():
    """Return online CB icon URL for HTML usage."""
    return CB_ICON_URL


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
    """Extract ceiling and visibility from a TAF feature."""
    ceiling_ft = None
    visibility_km = None

    try:
        properties = feature.get("properties", {})
        parsed_ceiling = properties.get("parsedCeilingFt")
        parsed_visibility = properties.get("parsedVisibilityKm")
        if parsed_ceiling is not None or parsed_visibility is not None:
            return parsed_ceiling, parsed_visibility

        # Visibility in meters, convert to km
        vis_m = properties.get("visibility", {}).get("value")
        if vis_m is not None:
            visibility_km = vis_m / 1000.0

        # Cloud layers - find lowest BKN or OVC layer
        clouds = properties.get("clouds", [])
        for layer in clouds:
            cover = layer.get("amount", "")
            base = layer.get("base", {}).get("value")
            if cover in ("BKN", "OVC") and base is not None:
                if ceiling_ft is None or base < ceiling_ft:
                    ceiling_ft = base
    except Exception:
        pass

    return ceiling_ft, visibility_km


def build_map(features, cb_icon_uri):
    m = folium.Map(location=[65, 15], zoom_start=4)

    for feature in features:
        try:
            coords = feature["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]
            properties = feature.get("properties", {})
            name = properties.get("ICAO") or properties.get("stationIdentification") or properties.get("name") or "Unknown"
            has_cb = properties.get("parsedHasCb", False)

            ceiling_ft, visibility_km = parse_conditions(feature)
            color_code = get_colour_state(ceiling_ft, visibility_km)
            hex_color = COLOUR_STATE_COLORS[color_code]

            popup_text = (
                f"<b>{name}</b><br>"
                f"Color Code: {color_code}<br>"
                f"Ceiling: {ceiling_ft if ceiling_ft is not None else 'N/A'} ft<br>"
                f"Visibility: {visibility_km if visibility_km is not None else 'N/A'} km"
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color=hex_color,
                fill=True,
                fill_color=hex_color,
                fill_opacity=0.8,
                popup=folium.Popup(popup_text, max_width=200),
                tooltip=f"{name}: {color_code}",
            ).add_to(m)

            if has_cb:
                # Add cumulonimbus weather symbol near stations that include CB in TAF.
                folium.Marker(
                    location=[lat, lon],
                    icon=DivIcon(
                        icon_size=(32, 32),
                        icon_anchor=(0, 0),
                        html=(
                            '<div style="position:relative;left:-24px;top:-24px;'
                            'width:22px;height:22px;display:flex;align-items:center;justify-content:center;'
                            'background:rgba(255,255,255,0.96);border:2px solid #111;border-radius:50%;'
                            'box-shadow:0 1px 4px rgba(0,0,0,0.45);" title="Cumulonimbus (CB) in TAF">'
                            f'<img src="{cb_icon_uri}" '
                            'width="17" height="17" alt="CB" style="display:block;"/>'
                            '</div>'
                        ),
                    ),
                ).add_to(m)

            # Persistent label shown next to each marker.
            folium.Marker(
                location=[lat, lon],
                icon=DivIcon(
                    icon_size=(34, 12),
                    icon_anchor=(-5, 6),
                    html=(
                        '<div style="font-size:10px;font-weight:bold;'
                        'line-height:10px;display:inline-block;white-space:nowrap;'
                        'color:#111;background:rgba(255,255,255,0.45);'
                        'padding:0 2px;border-radius:2px;">'
                        f"{name}</div>"
                    ),
                ),
            ).add_to(m)
        except Exception:
            continue

    return m


def main():
    print("Fetching TAF data...")
    data = fetch_taf_data()
    cb_icon_uri = ensure_local_cb_icon()

    features = data.get("features", [])
    print(f"Found {len(features)} TAF locations.")
    print("Fetching per-location IWXXM data...")
    enrich_features_with_iwxxm(features)

    m = build_map(features, cb_icon_uri)
    m.save(str(DEFAULT_OUTPUT_FILE))
    print(f"Map saved to {DEFAULT_OUTPUT_FILE}")


if __name__ == "__main__":
    main()