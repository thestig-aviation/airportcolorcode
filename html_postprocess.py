"""Post-processing for the generated HTML: injects the status notice, time slider, countdown timer, and auto-refresh logic."""
import json
from datetime import datetime, timezone

import requests


def _fetch_last_deploy_time_text():
    last_deploy_time = None
    try:
        api_url = "https://api.github.com/repos/thestig-aviation/airportcolorcode/commits/main"
        resp = requests.get(api_url, timeout=10)
        if resp.ok:
            commit_data = resp.json()
            last_deploy_time = commit_data["commit"]["committer"]["date"]
            dt = datetime.fromisoformat(last_deploy_time.replace("Z", "+00:00"))
            last_deploy_time = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        last_deploy_time = None
    return last_deploy_time


def _compute_taf_time_range(features):
    """Return (start, end) as UTC datetimes rounded to the hour, covering all parsedForecastPeriods."""
    earliest = None
    latest = None
    for feature in (features or []):
        for period in feature.get("properties", {}).get("parsedForecastPeriods", []):
            for iso_key, is_begin in (("begin", True), ("end", False)):
                iso = period.get(iso_key)
                if not iso:
                    continue
                try:
                    dt = datetime.fromisoformat(iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dt = dt.astimezone(timezone.utc)
                    if is_begin and (earliest is None or dt < earliest):
                        earliest = dt
                    elif not is_begin and (latest is None or dt > latest):
                        latest = dt
                except ValueError:
                    pass
    if earliest is None or latest is None:
        return None, None
    earliest = earliest.replace(minute=0, second=0, microsecond=0)
    latest = latest.replace(minute=0, second=0, microsecond=0)
    return (earliest, latest) if latest > earliest else (None, None)


def _build_time_slider_html(taf_start, taf_end, airport_periods):
    """Build the time-slider CSS/HTML/JS block for injection into the output page."""
    taf_base_ms = int(taf_start.timestamp() * 1000)
    total_hours = int((taf_end - taf_start).total_seconds() / 3600)
    if total_hours < 1:
        return ""
    start_label = taf_start.strftime("%Y-%m-%d %H:%M UTC")
    end_label = taf_end.strftime("%Y-%m-%d %H:%M UTC")
    airport_periods_json = json.dumps(airport_periods)
    return f'''
    <style>
        #taf-time-slider {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            width: 540px;
            background: white;
            border: 2px solid #888;
            border-radius: 7px;
            padding: 10px 20px 14px;
            font-family: Arial, sans-serif;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            z-index: 9998;
        }}
        #taf-slider-header {{
            font-weight: bold;
            font-size: 13px;
            text-align: center;
            margin-bottom: 6px;
            color: #222;
        }}
        #taf-slider-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            color: #444;
            margin-bottom: 4px;
        }}
        #taf-slider-track-area {{
            position: relative;
            height: 24px;
        }}
        #taf-track-bg {{
            position: absolute;
            top: 9px;
            left: 0;
            right: 0;
            height: 6px;
            background: #ddd;
            border-radius: 3px;
        }}
        #taf-track-fill {{
            position: absolute;
            top: 9px;
            height: 6px;
            background: #4a9eff;
            border-radius: 3px;
        }}
        #taf-slider-track-area input[type="range"] {{
            position: absolute;
            width: 100%;
            background: none;
            -webkit-appearance: none;
            appearance: none;
            pointer-events: none;
            height: 24px;
            margin: 0;
            padding: 0;
            top: 0;
        }}
        #taf-slider-track-area input[type="range"]::-webkit-slider-thumb {{
            -webkit-appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #0066cc;
            cursor: pointer;
            pointer-events: all;
            border: 2px solid white;
            box-shadow: 0 1px 4px rgba(0,0,0,0.4);
        }}
        #taf-slider-track-area input[type="range"]::-moz-range-thumb {{
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #0066cc;
            cursor: pointer;
            pointer-events: all;
            border: 2px solid white;
            box-shadow: 0 1px 4px rgba(0,0,0,0.4);
        }}
    </style>
    <div id="taf-time-slider">
        <div id="taf-slider-header">TAF Validity Window</div>
        <div id="taf-slider-labels">
            <span id="taf-start-label">{start_label}</span>
            <span id="taf-end-label">{end_label}</span>
        </div>
        <div id="taf-slider-track-area">
            <div id="taf-track-bg"></div>
            <div id="taf-track-fill"></div>
            <input type="range" id="taf-slider-start" min="0" max="{total_hours}" value="0" step="1">
            <input type="range" id="taf-slider-end"   min="0" max="{total_hours}" value="{total_hours}" step="1">
        </div>
    </div>
    <script>
    var AIRPORT_PERIODS = {airport_periods_json};
    (function() {{
        const BASE_MS = {taf_base_ms};
        const TOTAL_HOURS = {total_hours};
        const LS_START = 'taf-slider-start-ms';
        const LS_END   = 'taf-slider-end-ms';

        function hoursToLabel(h) {{
            const d = new Date(BASE_MS + h * 3600000);
            return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
        }}

        function clamp(v, lo, hi) {{ return Math.max(lo, Math.min(hi, v)); }}

        function updateMapForWindow() {{
            if (typeof window.LAYER_MAP === 'undefined') return;
            var lmap = window.LAYER_MAP;
            var sEl = document.getElementById('taf-slider-start');
            var eEl = document.getElementById('taf-slider-end');
            if (!sEl || !eEl) return;
            var sv = parseInt(sEl.value, 10);
            var ev = parseInt(eEl.value, 10);
            var winStart = BASE_MS + sv * 3600000;
            var winEnd   = BASE_MS + ev * 3600000;
            for (var icao in lmap) {{
                var lm = lmap[icao];
                var periods = (typeof AIRPORT_PERIODS !== 'undefined' && AIRPORT_PERIODS[icao]) || [];
                // Periods that overlap [winStart, winEnd)
                var active = periods.filter(function(p) {{
                    if (!p.begin || !p.end) return false;
                    return new Date(p.begin).getTime() < winEnd &&
                           new Date(p.end).getTime() > winStart;
                }});
                // Weather-bearing periods only (exclude wind-only change groups)
                var wxActive = active.filter(function(p) {{
                    return p.ceilingFt !== null || p.visibilityKm !== null || p.isCavok;
                }});
                // Worst dot colour
                if (window[lm.worst]) {{
                    var worstHex;
                    if (wxActive.length === 0) {{
                        worstHex = window.UNAVAILABLE_HEX;
                    }} else {{
                        var worstP = wxActive.reduce(function(a, b) {{
                            return a.rank < b.rank ? a : b;
                        }});
                        worstHex = window.COLOUR_STATE_HEX[worstP.colourState] || window.UNAVAILABLE_HEX;
                    }}
                    window[lm.worst].setStyle({{fillColor: worstHex}});
                }}
                // Best ring
                if (window[lm.best]) {{
                    if (wxActive.length === 0) {{
                        window[lm.best].setStyle({{opacity: 0}});
                    }} else {{
                        var bestP = wxActive.reduce(function(a, b) {{
                            return a.rank > b.rank ? a : b;
                        }});
                        var bestHex = window.COLOUR_STATE_HEX[bestP.colourState] || window.UNAVAILABLE_HEX;
                        window[lm.best].setStyle({{color: bestHex, opacity: 1}});
                    }}
                }}
                // Convective symbols: show at most one (priority TS > CB > TCU)
                var hasTs  = active.some(function(p) {{ return p.hasTs; }});
                var hasCb  = active.some(function(p) {{ return p.hasCb; }});
                var hasTcu = active.some(function(p) {{ return p.hasTcu; }});
                if (lm.ts  && window[lm.ts])  window[lm.ts].setOpacity(hasTs ? 1 : 0);
                if (lm.cb  && window[lm.cb])  window[lm.cb].setOpacity(!hasTs && hasCb ? 1 : 0);
                if (lm.tcu && window[lm.tcu]) window[lm.tcu].setOpacity(!hasTs && !hasCb && hasTcu ? 1 : 0);
            }}
        }}

        function updateSlider(movedSide) {{
            const sEl = document.getElementById('taf-slider-start');
            const eEl = document.getElementById('taf-slider-end');
            let sv = parseInt(sEl.value, 10);
            let ev = parseInt(eEl.value, 10);
            if (sv >= ev) {{
                if (movedSide === 'start') {{
                    sEl.value = ev > 0 ? ev - 1 : 0;
                    sv = parseInt(sEl.value, 10);
                }} else {{
                    eEl.value = sv < TOTAL_HOURS ? sv + 1 : TOTAL_HOURS;
                    ev = parseInt(eEl.value, 10);
                }}
            }}
            document.getElementById('taf-start-label').textContent = hoursToLabel(sv);
            document.getElementById('taf-end-label').textContent = hoursToLabel(ev);
            const fill = document.getElementById('taf-track-fill');
            fill.style.left  = (sv / TOTAL_HOURS * 100) + '%';
            fill.style.width = ((ev - sv) / TOTAL_HOURS * 100) + '%';
            try {{
                localStorage.setItem(LS_START, BASE_MS + sv * 3600000);
                localStorage.setItem(LS_END,   BASE_MS + ev * 3600000);
            }} catch (e) {{}}
            updateMapForWindow();
        }}

        // Restore previous slider position (saved as UTC ms timestamps).
        try {{
            const savedStart = parseFloat(localStorage.getItem(LS_START));
            const savedEnd   = parseFloat(localStorage.getItem(LS_END));
            if (!isNaN(savedStart) && !isNaN(savedEnd)) {{
                const sv = clamp(Math.round((savedStart - BASE_MS) / 3600000), 0, TOTAL_HOURS - 1);
                const ev = clamp(Math.round((savedEnd   - BASE_MS) / 3600000), sv + 1, TOTAL_HOURS);
                document.getElementById('taf-slider-start').value = sv;
                document.getElementById('taf-slider-end').value   = ev;
            }}
        }} catch (e) {{}}

        document.getElementById('taf-slider-start').addEventListener('input', function() {{ updateSlider('start'); }});
        document.getElementById('taf-slider-end').addEventListener('input',   function() {{ updateSlider('end'); }});
        // Update slider labels and track fill immediately (DOM elements are present).
        updateSlider(null);
        // Leaflet marker objects are created in the <script> block that Folium places
        // AFTER </body>, so they do not yet exist when the IIFE runs.  Defer the
        // marker-opacity pass to window.load, by which time all markers exist.
        window.addEventListener('load', updateMapForWindow);
    }})();
    </script>
    '''


def _extract_latest_issue_time_text_and_icao(features):
    latest_issue_time = None
    latest_issue_icao = None

    for feature in features or []:
        properties = feature.get("properties", {})
        issue_time_text = properties.get("parsedIssueTime")
        icao = properties.get("ICAO") or properties.get("stationIdentification")
        if not issue_time_text:
            continue

        normalized_text = issue_time_text.strip().replace("Z", "+00:00")
        try:
            parsed_time = datetime.fromisoformat(normalized_text)
        except ValueError:
            continue

        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)

        if latest_issue_time is None or parsed_time > latest_issue_time:
            latest_issue_time = parsed_time
            latest_issue_icao = icao

    if latest_issue_time is None:
        return None, None

    return latest_issue_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), latest_issue_icao


def postprocess_generated_html(output_file, features=None):
    # Add auto-refresh and header/notice to the HTML file
    with open(output_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    last_deploy_time = _fetch_last_deploy_time_text()
    latest_issue_time, latest_issue_icao = _extract_latest_issue_time_text_and_icao(features)
    latest_issue_time_display = latest_issue_time or "unavailable"
    if latest_issue_icao:
        latest_issue_time_display = f"{latest_issue_time_display} ({latest_issue_icao})"

    # Centered status notice at the top of the map
    status_notice_html = f'''
    <div id="status-notice" style="position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:10001;font-family:Arial,sans-serif;font-size:15px;color:#222;background:rgba(255,255,255,0.55);padding:6px 18px 6px 16px;border-radius:7px;box-shadow:0 1px 4px rgba(0,0,0,0.07);pointer-events:none;text-align:center;">
        Airport Color Code<br/>
        <span style=\"color:#FF0000;font-weight:bold;\">Prototype - not intended for operational use</span><br/>
        <span style="font-size:13px;color:#444;">Codebase changed: {last_deploy_time or 'unavailable'}</span><br/>
        <span style="font-size:13px;color:#444;">Last Issue Time: {latest_issue_time_display}</span>
    </div>
    '''

    # Insert notice after <body> tag
    if "<body>" in html_content:
        html_content = html_content.replace("<body>", "<body>\n" + status_notice_html, 1)
    else:
        html_content = status_notice_html + html_content

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
        const MAP_VIEW_STORAGE_KEY = 'airportcolorcode.mapView.v1';
        let secondsRemaining = 0;

        function getLeafletMapInstance() {
            for (const value of Object.values(window)) {
                if (value && typeof L !== 'undefined' && value instanceof L.Map) {
                    return value;
                }
            }
            return null;
        }

        function restoreMapView(map) {
            try {
                const saved = localStorage.getItem(MAP_VIEW_STORAGE_KEY);
                if (!saved) {
                    return;
                }
                const view = JSON.parse(saved);
                if (!view || typeof view.lat !== 'number' || typeof view.lng !== 'number' || typeof view.zoom !== 'number') {
                    return;
                }
                map.setView([view.lat, view.lng], view.zoom, { animate: false });
            } catch (err) {
                // Ignore malformed local storage values.
            }
        }

        function persistMapView(map) {
            map.on('moveend', function() {
                try {
                    const center = map.getCenter();
                    const zoom = map.getZoom();
                    localStorage.setItem(
                        MAP_VIEW_STORAGE_KEY,
                        JSON.stringify({ lat: center.lat, lng: center.lng, zoom: zoom })
                    );
                } catch (err) {
                    // Ignore storage quota/privacy errors.
                }
            });
        }

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
            const map = getLeafletMapInstance();
            if (map) {
                restoreMapView(map);
                persistMapView(map);
            }

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

    # Insert the auto-refresh code and mobile stylesheet link in the <head> section
    mobile_css_link = '    <link rel="stylesheet" href="mobile.css"/>\n'
    html_content = html_content.replace('</head>', mobile_css_link + auto_refresh_code + '</head>')

    # Inject time slider before </body>
    airport_periods = {}
    for feature in (features or []):
        props = feature.get("properties", {})
        icao = props.get("ICAO") or props.get("stationIdentification") or props.get("name")
        if icao:
            periods = props.get("parsedForecastPeriods") or []
            if periods:
                airport_periods[icao] = periods

    taf_start, taf_end = _compute_taf_time_range(features)
    if taf_start and taf_end:
        slider_html = _build_time_slider_html(taf_start, taf_end, airport_periods)
        if slider_html:
            if "</body>" in html_content:
                html_content = html_content.replace("</body>", slider_html + "\n</body>", 1)
            else:
                html_content += slider_html

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
