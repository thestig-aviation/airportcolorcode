import folium
from folium.features import DivIcon

from config import COLOUR_STATE_COLORS
from logic import format_issue_time_utc, get_colour_state, parse_conditions


def ensure_local_cb_icon(cb_icon_path, cb_icon_local_name):
    """Return the local CB icon path used by the generated HTML."""
    if not cb_icon_path.exists():
        raise FileNotFoundError(f"Missing CB icon asset: {cb_icon_path}")
    return cb_icon_local_name


def ensure_local_tcu_icon(tcu_icon_path, tcu_icon_local_name):
    """Return the local TCU icon path used by the generated HTML."""
    if not tcu_icon_path.exists():
        raise FileNotFoundError(f"Missing TCU icon asset: {tcu_icon_path}")
    return tcu_icon_local_name


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
            has_cavok = properties.get("parsedHasCavok", False)

            ceiling_ft, visibility_km, ceiling_source = parse_conditions(feature)
            color_code = get_colour_state(ceiling_ft, visibility_km)
            hex_color = COLOUR_STATE_COLORS[color_code]

            cavok_driven = has_cavok and ceiling_ft is None and visibility_km is None
            ceiling_display = "CAVOK" if cavok_driven else (f"{ceiling_ft} ft" if ceiling_ft is not None else "N/A ft")
            visibility_display = "CAVOK" if cavok_driven else (f"{visibility_km} km" if visibility_km is not None else "N/A km")

            popup_text = (
                f"<b>{name}</b><br>"
                f"Issue time: {format_issue_time_utc(properties.get('parsedIssueTime')) or 'N/A'} UTC<br>"
                f"Color Code: {color_code}<br>"
                f"Ceiling/VV: {ceiling_display}<br>"
                f"Visibility: {visibility_display}"
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color="#333",
                weight=1,
                fill=True,
                fill_color=hex_color,
                fill_opacity=1.0,
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
