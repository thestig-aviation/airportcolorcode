import xml.etree.ElementTree as ET

from config import IWXXM_NS


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
