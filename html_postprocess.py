"""Post-processing for the generated HTML: injects the status notice, countdown timer, and auto-refresh logic."""
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
    <div style="position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:10001;font-family:Arial,sans-serif;font-size:15px;color:#222;background:rgba(255,255,255,0.55);padding:6px 18px 6px 16px;border-radius:7px;box-shadow:0 1px 4px rgba(0,0,0,0.07);pointer-events:none;text-align:center;">
        Airport Color Code &mdash; <span style=\"color:#FF0000;font-weight:bold;\">Prototype - not intended for operational use</span><br/>
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

    # Insert the auto-refresh code in the <head> section
    html_content = html_content.replace('</head>', auto_refresh_code + '</head>')

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
