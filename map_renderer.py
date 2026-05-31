"""Folium map builder: renders airport markers, convective overlays, legend, and label layers."""
import json

import folium
from folium.features import DivIcon

from config import COLOUR_STATE_COLORS, UNAVAILABLE_COLOR
from logic import (
    format_issue_time_utc,
    parse_conditions,
    get_convective_symbol_title,
    get_forecast_display_info,
    colour_state_hex,
)


def ensure_local_icon(icon_path, icon_local_name):
    """Return the local icon path used by the generated HTML."""
    if not icon_path.exists():
        raise FileNotFoundError(f"Missing icon asset: {icon_path}")
    return icon_local_name


def render_convective_marker(location, symbol_type, icon_uri, class_name="airport-convective"):
    """Render a convective weather marker (TS, CB, or TCU). Initially hidden; JS controls visibility."""
    title = get_convective_symbol_title(symbol_type)
    alt = symbol_type

    return folium.Marker(
        location=location,
        icon=DivIcon(
            icon_size=(40, 40),
            icon_anchor=(0, 0),
            class_name=class_name,
            html=(
                '<div style="position:relative;left:-30px;top:-34px;'
                'width:30px;height:30px;display:flex;align-items:center;justify-content:center;'
                'background:rgba(255,255,255,0.96);border:2px solid #111;border-radius:50%;'
                f'box-shadow:0 1px 4px rgba(0,0,0,0.45);" title="{title}">'
                f'<img src="{icon_uri}" '
                f'width="23" height="23" alt="{alt}" style="display:block;"/>'
                '</div>'
            ),
        ),
        opacity=0,
    )


def build_map(features, cb_icon_uri, tcu_icon_uri, ts_icon_uri):
    """Build and return a Folium map with colour-coded airport markers and convective overlays.

    Icon URIs reference locally-bundled PNG assets copied alongside the output HTML.
    Priority for convective overlay display: TS > CB > TCU.
    """
    m = folium.Map(location=[65, 15], zoom_start=4)

    # Add legend to the map
    legend_html = '''
    <div id="map-legend" style="position: fixed; 
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
        <h4 id="map-legend-toggle" style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold;">Color State Criteria <span id="map-legend-arrow" style="font-size:11px;"></span></h4>
        <div id="map-legend-body">
        <div style="display: flex; align-items: center; margin: 4px 0;">
            <div style="width: 20px; height: 20px; background-color: #969696; border: 1px solid #333; border-radius: 50%; margin-right: 8px;"></div>
            <span><strong>GRAY:</strong> Forecast Unavailable (not valid now)</span>
        </div>
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
        <div style="margin-top: 8px; font-size: 11px; color: #555; border-top: 1px solid #ddd; padding-top: 6px;">
            <div style="display: flex; align-items: center; margin-bottom: 4px;">
                <input type="checkbox" id="chk-best" checked style="margin-right: 5px; cursor: pointer; flex-shrink: 0;">
                <div style="width: 20px; height: 20px; border-radius: 50%; border: 3px solid #0000FF; margin-right: 8px; flex-shrink: 0;"></div>
                <label for="chk-best" style="cursor: pointer;"><strong>Outer ring:</strong> best forecast state</label>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 4px;">
                <input type="checkbox" id="chk-worst" checked style="margin-right: 5px; cursor: pointer; flex-shrink: 0;">
                <div style="width: 20px; height: 20px; border-radius: 50%; background-color: #0000FF; border: 1px solid #333; margin-right: 8px; flex-shrink: 0;"></div>
                <label for="chk-worst" style="cursor: pointer;"><strong>Inner fill:</strong> worst forecast state</label>
            </div>
        </div>
        <div style="margin-top: 4px; font-size: 11px; color: #666; border-top: 1px solid #ddd; padding-top: 6px;">
            <div style="display: flex; align-items: center; margin-bottom: 4px;">
                <input type="checkbox" id="chk-convective" checked style="margin-right: 5px; cursor: pointer; flex-shrink: 0;">
                <label for="chk-convective" style="cursor: pointer; font-weight: bold;">Convective symbols</label>
            </div>
            <div style="display: flex; align-items: center; margin-top: 4px; margin-left: 20px;">
                <img src="''' + ts_icon_uri + '''"
                     width="23" height="23" alt="TS" style="margin-right: 6px; border: 2px solid #111; border-radius: 50%; padding: 2px; background: white; box-shadow:0 1px 4px rgba(0,0,0,0.45);"/>
                <span>Thunderstorm (TS) in TAF</span>
            </div>
            <div style="display: flex; align-items: center; margin-top: 4px; margin-left: 20px;">
                <img src="''' + cb_icon_uri + '''"
                     width="23" height="23" alt="CB" style="margin-right: 6px; border: 2px solid #111; border-radius: 50%; padding: 2px; background: white; box-shadow:0 1px 4px rgba(0,0,0,0.45);"/>
                <span>Cumulonimbus (CB) in TAF</span>
            </div>
            <div style="display: flex; align-items: center; margin-top: 4px; margin-left: 20px;">
                <img src="''' + tcu_icon_uri + '''"
                     width="23" height="23" alt="TCU" style="margin-right: 6px; border: 2px solid #111; border-radius: 50%; padding: 2px; background: white; box-shadow:0 1px 4px rgba(0,0,0,0.45);"/>
                <span>Towering Cumulus (TCU) in TAF</span>
            </div>
        </div>
        </div>
    </div>
    <script>
    (function() {
        var LS = 'legend-chk-';
        function applyToggle(cls, visible) {
            document.querySelectorAll('.' + cls).forEach(function(el) {
                el.style.display = visible ? '' : 'none';
            });
        }
        function bindCheckbox(id, cls) {
            var el = document.getElementById(id);
            if (!el) return;
            var saved = localStorage.getItem(LS + id);
            if (saved !== null) { el.checked = (saved === 'true'); }
            applyToggle(cls, el.checked);
            el.addEventListener('change', function() {
                applyToggle(cls, el.checked);
                try { localStorage.setItem(LS + id, el.checked); } catch(e) {}
            });
        }
        window.addEventListener('load', function() {
            bindCheckbox('chk-worst', 'airport-worst');
            bindCheckbox('chk-best', 'airport-best');
            bindCheckbox('chk-convective', 'airport-convective');
        });
    })();
    (function() {
        var mq = window.matchMedia('(max-width: 600px)');
        function setup(mobile) {
            var body  = document.getElementById('map-legend-body');
            var arrow = document.getElementById('map-legend-arrow');
            var hdr   = document.getElementById('map-legend-toggle');
            if (!body || !hdr) return;
            if (mobile) {
                body.style.display = 'none';
                if (arrow) arrow.textContent = ' \u25B6';
                hdr.style.cursor = 'pointer';
                hdr.onclick = function() {
                    var open = body.style.display !== 'none';
                    body.style.display = open ? 'none' : '';
                    if (arrow) arrow.textContent = open ? ' \u25B6' : ' \u25BC';
                };
            } else {
                body.style.display = '';
                if (arrow) arrow.textContent = '';
                hdr.style.cursor = 'default';
                hdr.onclick = null;
            }
        }
        mq.addEventListener('change', function(e) { setup(e.matches); });
        window.addEventListener('load', function() { setup(mq.matches); });
    })();
    </script>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    layer_map = {}
    for feature in features:
        try:
            coords = feature["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]
            properties = feature.get("properties", {})
            name = properties.get("ICAO") or properties.get("stationIdentification") or properties.get("name") or "Unknown"
            has_ts = properties.get("parsedHasTs", False)
            has_cb = properties.get("parsedHasCb", False)
            has_tcu = properties.get("parsedHasTcu", False)
            has_cavok = properties.get("parsedHasCavok", False)
            forecast_available_now = properties.get("parsedForecastAvailableNow", True)
            forecast_unavailable_reason = properties.get("parsedForecastUnavailableReason") or "Unknown reason"

            ceiling_ft, visibility_km, _ = parse_conditions(feature)
            hex_color, color_label, ceiling_display, visibility_display = get_forecast_display_info(
                forecast_available_now, ceiling_ft, visibility_km, has_cavok
            )

            best_hex_color = None
            best_color_label = None
            _periods = properties.get("parsedForecastPeriods") or []
            # Exclude periods with no explicit vis/ceiling/CAVOK data; a
            # wind-only change group carries no colour-state information
            # and must not inflate or deflate the best/worst rank.
            _wx_periods = [
                p for p in _periods
                if p.get("ceilingFt") is not None
                or p.get("visibilityKm") is not None
                or p.get("isCavok")
            ]
            if _wx_periods:
                _best = max(_wx_periods, key=lambda p: p["rank"])
                best_color_label = _best["colourState"]
                best_hex_color = colour_state_hex(best_color_label)

            popup_text = (
                f"<b>{name}</b><br>"
                f"Issue time: {format_issue_time_utc(properties.get('parsedIssueTime')) or 'N/A'} UTC<br>"
                f"Worst state: {color_label}<br>"
                + (f"Best state: {best_color_label}<br>" if best_color_label else "")
                + f"Ceiling/VV: {ceiling_display}<br>"
                f"Visibility: {visibility_display}"
            )
            if not forecast_available_now:
                popup_text += f"<br>Reason: {forecast_unavailable_reason}"

            tooltip_text = (
                f"{name}: {color_label} / {best_color_label}"
                if best_color_label else f"{name}: {color_label}"
            )

            worst_marker = folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color="#333",
                weight=1,
                fill=True,
                fill_color=hex_color,
                fill_opacity=1.0,
                popup=folium.Popup(popup_text, max_width=220),
                tooltip=tooltip_text,
                className="airport-worst",
            )
            worst_marker.add_to(m)

            # Outer ring: static colour set from Python-computed best state so it is
            # visible immediately on page load. JS overrides colour/opacity via
            # updateMapForWindow() whenever the slider moves.
            best_marker = folium.CircleMarker(
                location=[lat, lon],
                radius=16,
                color=best_hex_color if best_hex_color else UNAVAILABLE_COLOR,
                weight=5,
                fill=False,
                opacity=1.0 if best_hex_color else 0,
                tooltip=tooltip_text,
                className="airport-best",
            )
            best_marker.add_to(m)

            # Convective markers: render all three types for any airport that has convective
            # in its forecast. JS shows at most one (priority TS > CB > TCU) per time window.
            _periods = properties.get("parsedForecastPeriods") or []
            _any_convective = any(
                p.get("hasTs") or p.get("hasCb") or p.get("hasTcu") for p in _periods
            )
            ts_name = cb_name = tcu_name = None
            if _any_convective:
                ts_m = render_convective_marker(
                    [lat, lon], "TS", ts_icon_uri, "airport-convective airport-convective-ts"
                )
                ts_m.add_to(m)
                ts_name = ts_m.get_name()
                cb_m = render_convective_marker(
                    [lat, lon], "CB", cb_icon_uri, "airport-convective airport-convective-cb"
                )
                cb_m.add_to(m)
                cb_name = cb_m.get_name()
                tcu_m = render_convective_marker(
                    [lat, lon], "TCU", tcu_icon_uri, "airport-convective airport-convective-tcu"
                )
                tcu_m.add_to(m)
                tcu_name = tcu_m.get_name()

            layer_map[name] = {
                "worst": worst_marker.get_name(),
                "best": best_marker.get_name(),
                "ts": ts_name,
                "cb": cb_name,
                "tcu": tcu_name,
            }

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

    layer_map_json = json.dumps(layer_map)
    colour_state_hex_json = json.dumps(COLOUR_STATE_COLORS)
    unavailable_hex_json = json.dumps(UNAVAILABLE_COLOR)
    m.get_root().html.add_child(folium.Element(
        f'<script>'
        f'window.LAYER_MAP={layer_map_json};'
        f'window.COLOUR_STATE_HEX={colour_state_hex_json};'
        f'window.UNAVAILABLE_HEX={unavailable_hex_json};'
        f'</script>'
    ))
    return m
