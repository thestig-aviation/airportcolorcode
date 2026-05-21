## Python Code

import requests
import folium
from folium.features import DivIcon
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

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


def parse_iwxxm_conditions(xml_text):
    """Parse IWXXM XML and return (issue time, ceiling ft, visibility km, has_cb, has_tcu, ceiling source)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None, None, None, False, False, None

    issue_time = None
    issue_time_elem = root.find(".//iwxxm:issueTime/gml:TimeInstant/gml:timePosition", IWXXM_NS)
    if issue_time_elem is not None and (issue_time_elem.text or "").strip():
        issue_time = issue_time_elem.text.strip()

    vis_values = []
    for vis in root.findall(".//iwxxm:prevailingVisibility", IWXXM_NS):
        try:
            vis_value = float((vis.text or "").strip())
        except (TypeError, ValueError):
            continue
        vis_km = _uom_to_km(vis_value, vis.get("uom", "m"))
        if vis_km is not None:
            vis_values.append(vis_km)

    significant_amounts = {"VV", "BKN", "OVC"}
    ceiling_candidates = []

    for vv in root.findall(".//iwxxm:verticalVisibility", IWXXM_NS):
        if not (vv.text or "").strip():
            continue
        try:
            vv_value = float(vv.text.strip())
        except ValueError:
            continue
        vv_ft = _uom_to_ft(vv_value, vv.get("uom", "[ft_i]"))
        if vv_ft is not None:
            ceiling_candidates.append(("VV", vv_ft))

    has_cb = False
    has_tcu = False
    for layer in root.findall(".//iwxxm:CloudLayer", IWXXM_NS):
        amount_elem = layer.find("iwxxm:amount", IWXXM_NS)
        base_elem = layer.find("iwxxm:base", IWXXM_NS)
        cloud_type_elem = layer.find("iwxxm:cloudType", IWXXM_NS)
        if cloud_type_elem is not None:
            cloud_type_href = cloud_type_elem.get(f"{{{IWXXM_NS['xlink']}}}href", "")
            cloud_type_text = (cloud_type_elem.text or "").strip().upper()
            if cloud_type_href.upper().endswith("/CB") or cloud_type_text == "CB":
                has_cb = True
            if cloud_type_href.upper().endswith("/TCU") or cloud_type_text == "TCU":
                has_tcu = True

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
            ceiling_candidates.append((amount_code, base_ft))

    # Use worst visibility and lowest significant cloud base from the TAF.
    visibility_km = min(vis_values) if vis_values else None
    ceiling_source = None
    ceiling_ft = None
    if ceiling_candidates:
        ceiling_source, ceiling_ft = min(ceiling_candidates, key=lambda item: item[1])
    return issue_time, ceiling_ft, visibility_km, has_cb, has_tcu, ceiling_source


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
            issue_time, ceiling_ft, visibility_km, has_cb, has_tcu, ceiling_source = parse_iwxxm_conditions(response.text)
            properties["parsedIssueTime"] = issue_time
            properties["parsedCeilingFt"] = ceiling_ft
            properties["parsedVisibilityKm"] = visibility_km
            properties["parsedHasCb"] = has_cb
            properties["parsedHasTcu"] = has_tcu
            properties["parsedCeilingSource"] = ceiling_source
        except requests.RequestException:
            properties["parsedIssueTime"] = None
            properties["parsedCeilingFt"] = None
            properties["parsedVisibilityKm"] = None
            properties["parsedHasCb"] = False
            properties["parsedHasTcu"] = False
            properties["parsedCeilingSource"] = None


def ensure_local_cb_icon():
    """Return the local CB icon path used by the generated HTML."""
    if not CB_ICON_PATH.exists():
        raise FileNotFoundError(f"Missing CB icon asset: {CB_ICON_PATH}")
    return CB_ICON_LOCAL_NAME


def ensure_local_tcu_icon():
    """Return the local TCU icon path used by the generated HTML."""
    if not TCU_ICON_PATH.exists():
        raise FileNotFoundError(f"Missing TCU icon asset: {TCU_ICON_PATH}")
    return TCU_ICON_LOCAL_NAME


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


def _state_rank(code):
    return {
        "RED": 0,
        "AMB": 1,
        "YLO2": 2,
        "YLO1": 3,
        "GRN": 4,
        "WHT": 5,
        "BLU": 6,
    }[code]


def _is_ceiling_driver(color_code, ceiling_ft, visibility_km):
    ceiling_only = get_colour_state(ceiling_ft, None)
    visibility_only = get_colour_state(None, visibility_km)
    return _state_rank(ceiling_only) <= _state_rank(visibility_only) and color_code == ceiling_only


def build_map(features, cb_icon_uri, tcu_icon_uri):
    m = folium.Map(location=[65, 15], zoom_start=4)

    # Add legend to the map
    legend_html = '''
    <div style="position: fixed; 
                top: 10px; 
                right: 10px; 
                width: 280px; 
                background-color: white; 
                border: 2px solid #888; 
                border-radius: 5px; 
                padding: 10px; 
                font-family: Arial, sans-serif; 
                font-size: 12px; 
                box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                z-index: 9999;">
        <h4 style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold;">Color State Criteria</h4>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #FF0000; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>RED:</strong> &lt;200 ft or &lt;0.8 km</span>
        </div>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #FF8000; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>AMB:</strong> &lt;300 ft or &lt;1.6 km</span>
        </div>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #FFC000; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>YLO2:</strong> &lt;500 ft or &lt;2.5 km</span>
        </div>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #FFF200; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>YLO1:</strong> &lt;700 ft or &lt;3.7 km</span>
        </div>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #00A000; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>GRN:</strong> &lt;1500 ft or &lt;5 km</span>
        </div>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #FFFFFF; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>WHT:</strong> &lt;2500 ft or &lt;8 km</span>
        </div>
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #0000FF; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>BLU:</strong> ≥2500 ft and ≥8 km</span>
        </div>
        <div style="margin-top: 8px; font-size: 11px; color: #666; border-top: 1px solid #ddd; padding-top: 6px;">
            <div style="display: flex; align-items: center; margin-top: 4px;">
                 <img src="''' + cb_icon_uri + '''" 
                     width="23" height="23" alt="CB" style="margin-right: 6px; border: 2px solid #111; border-radius: 50%; padding: 2px; background: white; box-shadow:0 1px 4px rgba(0,0,0,0.45);"/>
                <span>Cumulonimbus (CB) in TAF</span>
            </div>
            <div style="display: flex; align-items: center; margin-top: 4px;">
                <img src="''' + tcu_icon_uri + '''"
                     width="23" height="23" alt="TCU" style="margin-right: 6px; border: 2px solid #111; border-radius: 50%; padding: 2px; background: white; box-shadow:0 1px 4px rgba(0,0,0,0.45);"/>
                <span>Towering Cumulus (TCU) in TAF</span>
            </div>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    for feature in features:
        try:
            coords = feature["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]
            properties = feature.get("properties", {})
            name = properties.get("ICAO") or properties.get("stationIdentification") or properties.get("name") or "Unknown"
            has_cb = properties.get("parsedHasCb", False)
            has_tcu = properties.get("parsedHasTcu", False)

            ceiling_ft, visibility_km, ceiling_source = parse_conditions(feature)
            color_code = get_colour_state(ceiling_ft, visibility_km)
            hex_color = COLOUR_STATE_COLORS[color_code]

            popup_text = (
                f"<b>{name}</b><br>"
                f"Issue time: {format_issue_time_utc(properties.get('parsedIssueTime')) or 'N/A'} UTC<br>"
                f"Color Code: {color_code}<br>"
                f"Ceiling/VV: {ceiling_ft if ceiling_ft is not None else 'N/A'} ft<br>"
                f"Visibility: {visibility_km if visibility_km is not None else 'N/A'} km"
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=11,
                color=hex_color,
                fill=True,
                fill_color=hex_color,
                fill_opacity=0.8,
                popup=folium.Popup(popup_text, max_width=200),
                tooltip=f"{name}: {color_code}",
            ).add_to(m)

            if has_cb:
                # CB takes priority over TCU if both are present.
                folium.Marker(
                    location=[lat, lon],
                    icon=DivIcon(
                        icon_size=(40, 40),
                        icon_anchor=(0, 0),
                        html=(
                            '<div style="position:relative;left:-30px;top:-34px;'
                            'width:30px;height:30px;display:flex;align-items:center;justify-content:center;'
                            'background:rgba(255,255,255,0.96);border:2px solid #111;border-radius:50%;'
                            'box-shadow:0 1px 4px rgba(0,0,0,0.45);" title="Cumulonimbus (CB) in TAF">'
                            f'<img src="{cb_icon_uri}" '
                            'width="23" height="23" alt="CB" style="display:block;"/>'
                            '</div>'
                        ),
                    ),
                ).add_to(m)
            elif has_tcu:
                folium.Marker(
                    location=[lat, lon],
                    icon=DivIcon(
                        icon_size=(40, 40),
                        icon_anchor=(0, 0),
                        html=(
                            '<div style="position:relative;left:-30px;top:-34px;'
                            'width:30px;height:30px;display:flex;align-items:center;justify-content:center;'
                            'background:rgba(255,255,255,0.96);border:2px solid #111;border-radius:50%;'
                            'box-shadow:0 1px 4px rgba(0,0,0,0.45);" title="Towering Cumulus (TCU) in TAF">'
                            f'<img src="{tcu_icon_uri}" '
                            'width="23" height="23" alt="TCU" style="display:block;"/>'
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
                        '<div style="font-size:13px;font-weight:bold;'
                        'line-height:10px;display:inline-block;white-space:nowrap;'
                        'color:#111;background:rgba(255,255,255,0.45);'
                        'padding:0 2px;border-radius:2px;margin-left:6px;">'
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
    tcu_icon_uri = ensure_local_tcu_icon()

    features = data.get("features", [])
    print(f"Found {len(features)} TAF locations.")
    print("Fetching per-location IWXXM data...")
    enrich_features_with_iwxxm(features)

    m = build_map(features, cb_icon_uri, tcu_icon_uri)
    m.save(str(DEFAULT_OUTPUT_FILE))
    
    # Add auto-refresh and header/notice to the HTML file
    with open(DEFAULT_OUTPUT_FILE, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Fetch last commit time from GitHub main branch
    last_deploy_time = None
    try:
        api_url = "https://api.github.com/repos/thestig-aviation/airportcolorcode/commits/main"
        resp = requests.get(api_url, timeout=10)
        if resp.ok:
            commit_data = resp.json()
            last_deploy_time = commit_data["commit"]["committer"]["date"]
            # Format to readable UTC
            dt = datetime.fromisoformat(last_deploy_time.replace("Z", "+00:00"))
            last_deploy_time = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        last_deploy_time = None

    # Centered alpha notice at the top, transparent background, with last deploy time
    alpha_notice_html = f'''
    <div style="position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:10001;font-family:Arial,sans-serif;font-size:15px;color:#222;background:rgba(255,255,255,0.55);padding:6px 18px 6px 16px;border-radius:7px;box-shadow:0 1px 4px rgba(0,0,0,0.07);pointer-events:none;text-align:center;">
        Airport Color Code &mdash; <span style=\"color:#b36b00;\">alpha version</span><br/>
        <span style="font-size:13px;color:#444;">Last Build: {last_deploy_time or 'unavailable'}</span>
    </div>
    '''

    # Insert notice after <body> tag
    if "<body>" in html_content:
        html_content = html_content.replace("<body>", "<body>\n" + alpha_notice_html, 1)
    else:
        html_content = alpha_notice_html + html_content

    # Auto-refresh JavaScript and style to inject
    auto_refresh_code = '''
    <style>
        #countdown-timer {
            position: fixed;
            bottom: 10px;
            right: 10px;
            background-color: rgba(255, 255, 255, 0.95);
            border: 2px solid #888;
            border-radius: 5px;
            padding: 8px 12px;
            font-family: Arial, sans-serif;
            font-size: 13px;
            font-weight: bold;
            color: #333;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            z-index: 9999;
        }
        #countdown-timer .label {
            font-weight: normal;
            font-size: 11px;
            color: #666;
        }
        #countdown-timer .time {
            font-size: 16px;
            color: #0066cc;
            margin-left: 5px;
        }
    </style>
    <script>
        // Refresh at :01, :16, :31, and :46 minutes past each hour
        const TARGET_MINUTES = [1, 16, 31, 46];
        let secondsRemaining = 0;
        function calculateSecondsUntilNextUpdate() {
            const now = new Date();
            const currentMinute = now.getMinutes();
            const currentSecond = now.getSeconds();
            let nextTargetMinute = TARGET_MINUTES.find(m => m > currentMinute);
            if (nextTargetMinute === undefined) {
                nextTargetMinute = TARGET_MINUTES[0] + 60;
            }
            const minutesUntil = nextTargetMinute - currentMinute;
            const secondsUntil = (minutesUntil * 60) - currentSecond;
            return secondsUntil;
        }
        function updateCountdown() {
            const minutes = Math.floor(secondsRemaining / 60);
            const seconds = secondsRemaining % 60;
            const timeString = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
            const timerElement = document.getElementById('countdown-time');
            if (timerElement) {
                timerElement.textContent = timeString;
            }
            if (secondsRemaining <= 0) {
                location.reload();
            } else {
                secondsRemaining--;
            }
        }
        window.addEventListener('load', function() {
            secondsRemaining = calculateSecondsUntilNextUpdate();
            const timerDiv = document.createElement('div');
            timerDiv.id = 'countdown-timer';
            const minutes = Math.floor(secondsRemaining / 60);
            const seconds = secondsRemaining % 60;
            const initialTime = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
            timerDiv.innerHTML = '<span class="label">Next update in:</span><span class="time" id="countdown-time">' + initialTime + '</span>';
            document.body.appendChild(timerDiv);
            setInterval(updateCountdown, 1000);
        });
    </script>
    '''

    # Insert the auto-refresh code in the <head> section
    html_content = html_content.replace('</head>', auto_refresh_code + '</head>')

    with open(DEFAULT_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Map saved to {DEFAULT_OUTPUT_FILE} with auto-refresh enabled")


if __name__ == "__main__":
    main()