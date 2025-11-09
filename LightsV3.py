#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NOAA/USCG Light List => Bridge Command Buoy.ini + Light.ini
- Works with your "District 1" style file: quoted lines, latitude on one line (ends N/S),
  longitude on the next line (ends E/W), not a true comma-delimited CSV.
- Also supports real CSV/TSV/Excel if you point INPUT_FILE to those.

Usage:
  1) Set INPUT_FILE below (use raw string r"...").
  2) Set BBOX to your area. For DR, use the DR box. For District 1 testing, use New England box.
  3) If your buoys appear one chart to the right/left, adjust the LONGITUDE NORMALIZATION section.
  4) Run:  python Lights_BC_generator.py
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ========================== CONFIG ==========================

# Path to your file (the text/CSV you uploaded). Use r"" to avoid backslash escapes on Windows.
INPUT_FILE = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\Light List for District 1.csv")

# Choose one bounding box.
# Dominican Republic (typical):
# MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = -71.7, 17.3, -68.3, 19.9

# District 1 (New England) for testing your current file:
MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = -74.3, 40.3, -73.8, 40.7

# Output folder
OUTPUT_DIR = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\output")
BUOY_OUT  = OUTPUT_DIR / "Buoy.ini"
LIGHT_OUT = OUTPUT_DIR / "Light.ini"

# Defaults for lights if missing
DEFAULT_PERIOD_S  = 4.0
DEFAULT_RANGE_NM  = 6.0
DEFAULT_HEIGHT_M  = 12.0

# Map of color words/initials to RGB
LIGHT_COLOR_RGB = {
    "white": (255, 255, 255),
    "red":   (255,   0,   0),
    "green": (  0, 255,   0),
    "yellow":(255, 255,   0),
    "blue":  (  0,   0, 255),
}

# =================== LONGITUDE NORMALIZATION ===================
# If your buoys appear shifted one whole chart to the right, tune these.

# LON_MODE:
#   "neg_west"        -> normalize to -180..+180 with west negative (typical)
#   "wrap360"         -> normalize to 0..360
#   "force_west_neg"  -> if input is 0..360, convert west >180 to negative then normalize
LON_MODE = "neg_west"

# Constant longitude offset in degrees to add after normalization (rarely needed).
# Try +360.0 or -360.0 if your world wraps differently.
LON_OFFSET_DEG = 0.0

# If you discover lat/lon got swapped somewhere downstream, set this True to flip them at write time.
SWAP_LAT_LON = False

# ======================== HELPERS ========================

def in_bbox(lon: float, lat: float) -> bool:
    return (MIN_LON <= lon <= MAX_LON) and (MIN_LAT <= lat <= MAX_LAT)

# DMS pattern like "44-32-15.837N" or "067-05-13.808W"
DMS_RE = re.compile(r"(\d{2,3})-(\d{2})-(\d{2}(?:\.\d+)?)\s*([NSEW])\b")

def dms_to_decimal(d: str, m: str, s: str, hemi: str) -> float:
    val = int(d) + int(m)/60.0 + float(s)/3600.0
    if hemi.upper() in ("S", "W"):
        val = -val
    return val

def extract_color(text: str) -> str:
    t = (text or "").lower()
    for word, cname in [("white","white"),("red","red"),("green","green"),("yellow","yellow"),("blue","blue")]:
        if word in t:
            return cname
    # abbreviations fallback if the text has single-letter color tokens
    if re.search(r"\bW\b", text or ""): return "white"
    if re.search(r"\bR\b", text or ""): return "red"
    if re.search(r"\bG\b", text or ""): return "green"
    if re.search(r"\bY\b", text or ""): return "yellow"
    if re.search(r"\bB\b", text or ""): return "blue"
    return "white"

def extract_period_seconds(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*s\b", text or "", re.I)  # e.g., "10s"
    return float(m.group(1)) if m else DEFAULT_PERIOD_S

def extract_range_nm(text: str) -> float:
    # Light List uses M (miles) for range; use word boundary to avoid minutes-of-arc.
    m = re.search(r"(\d+(?:\.\d+)?)\s*M\b", text or "", re.I)
    return float(m.group(1)) if m else DEFAULT_RANGE_NM

def extract_char_key(text: str) -> str:
    t = (text or "").lower()
    for key in ["iso", "oc", "lfl", "ffl", "fl", "vq", "q"]:
        if re.search(rf"\b{key}\b", t):
            return key.upper()
    return "FIX"

def sequence(ch: str, period_s: float) -> str:
    # Bridge Command sequence: 'L' (light) / 'D' (dark) in 0.25 s ticks.
    P = period_s if period_s > 0.5 else DEFAULT_PERIOD_S
    ticks = max(4, min(80, int(round(P / 0.25))))
    if ch.startswith("FL"):
        on = max(1, int(round(0.5 / 0.25)))  # ~0.5 s on
        return "L" * on + "D" * (ticks - on)
    if ch.startswith("LFL"):
        on = max(1, int(round(2.0 / 0.25)))  # long flash ~2s
        on = min(on, ticks - 1)
        return "L" * on + "D" * (ticks - on)
    if ch.startswith("ISO"):
        return "L" * (ticks // 2) + "D" * (ticks - ticks // 2)
    if ch.startswith("OC"):
        on = int(round(ticks * 0.6))
        return "L" * on + "D" * (ticks - on)
    if ch in ("Q", "VQ"):
        return ("LD" * (ticks // 2)) or "LD"
    return "L"

def _wrap360(lon: float) -> float:
    lon = lon % 360.0
    if lon < 0:
        lon += 360.0
    return lon

def _to_neg_west(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0

def norm_coords(lon: float, lat: float) -> Tuple[float, float]:
    # Apply swap first if requested
    if SWAP_LAT_LON:
        lon, lat = lat, lon

    # Normalize longitudes according to chosen mode
    if LON_MODE == "wrap360":
        lon = _wrap360(lon)
    elif LON_MODE == "force_west_neg":
        # If lon > 180 assume it's 0..360 west, convert to negative
        if lon > 180.0:
            lon = lon - 360.0
        lon = _to_neg_west(lon)
    else:  # "neg_west"
        lon = _to_neg_west(lon)

    # Apply constant offset if any
    if LON_OFFSET_DEG:
        lon += float(LON_OFFSET_DEG)

    return lon, lat

# ===================== PARSERS =====================

def parse_text_two_line_format(path: Path) -> List[Dict]:
    """
    Parse your quoted text format with two-line position:
      Line A: ... <name blob> ... <LAT d-m-sH> <char blob>
      Line B: ... <LON d-m-sH> ...
    Returns list of dicts: {name_blob, char_blob, lat, lon}
    """
    entries: List[Dict] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = [ln.strip().strip('"') for ln in f if ln.strip().strip('"')]

    i = 0
    while i < len(lines):
        line = lines[i]
        latm = DMS_RE.search(line)
        if latm and latm.group(4).upper() in ("N", "S"):
            name_blob = " ".join(line[:latm.start()].split())
            char_blob = " ".join(line[latm.end():].split())
            d, m, s, hemi = latm.groups()
            lat = dms_to_decimal(d, m, s, hemi)

            # find the next line containing a longitude token
            lon: Optional[float] = None
            j = i + 1
            while j < len(lines):
                lonm = DMS_RE.search(lines[j])
                if lonm and lonm.group(4).upper() in ("E", "W"):
                    d2, m2, s2, hemi2 = lonm.groups()
                    lon = dms_to_decimal(d2, m2, s2, hemi2)
                    i = j  # jump ahead to the lon line
                    break
                j += 1

            if lon is not None:
                entries.append({"name_blob": name_blob, "char_blob": char_blob, "lat": lat, "lon": lon})
        i += 1

    return entries

def parse_table_like(path: Path) -> List[Dict]:
    """
    Optional fallback for real CSV/TSV/Excel with lat/lon in single rows.
    Tries pandas if available; if not, returns [].
    """
    try:
        import pandas as pd
    except Exception:
        return []
    # Try common formats
    suf = path.suffix.lower()
    loaders = []
    if suf in [".xlsx", ".xls"]:
        loaders.append(("excel", {}))
    # try various CSV-like
    for enc in ["utf-8", "utf-16", "utf-16-le", "utf-16-be", "latin-1"]:
        for sep in [None, ",", "\t", ";", "|"]:
            loaders.append(("csv", {"encoding": enc, "sep": sep, "engine": "python", "on_bad_lines": "skip"}))

    for kind, kw in loaders:
        try:
            if kind == "excel":
                df = pd.read_excel(path, dtype=str)
            else:
                df = pd.read_csv(path, dtype=str, **kw)
            if df is None or df.shape[1] < 2:
                continue
            cols = [c.lower() for c in df.columns]
            col_lat = next((c for c in df.columns if "lat" in c.lower()), None)
            col_lon = next((c for c in df.columns if "lon" in c.lower() or "long" in c.lower()), None)
            col_name = next((c for c in df.columns if "name" in c.lower()), None)
            col_char = next((c for c in df.columns if "char" in c.lower() or "character" in c.lower()), None)
            if not (col_lat and col_lon):
                continue

            # Accept d-m-sH or decimal with hemisphere
            entries: List[Dict] = []
            for _, row in df.iterrows():
                lat_raw = str(row.get(col_lat, "") or "").strip()
                lon_raw = str(row.get(col_lon, "") or "").strip()

                # Try DMS hyphen style first
                latm = DMS_RE.search(lat_raw)
                lonm = DMS_RE.search(lon_raw)
                lat = None
                lon = None
                if latm and latm.group(4).upper() in ("N", "S"):
                    lat = dms_to_decimal(*latm.groups())
                if lonm and lonm.group(4).upper() in ("E", "W"):
                    lon = dms_to_decimal(*lonm.groups())

                # If still None, try decimal with hemisphere "18.4467 N"
                if lat is None:
                    m = re.match(r"^\s*([\-+]?\d+(?:\.\d+)?)\s*([NS])\s*$", lat_raw, re.I)
                    if m:
                        val = float(m.group(1)); hemi = m.group(2).upper()
                        lat = -abs(val) if hemi == "S" else abs(val)
                if lon is None:
                    m = re.match(r"^\s*([\-+]?\d+(?:\.\d+)?)\s*([EW])\s*$", lon_raw, re.I)
                    if m:
                        val = float(m.group(1)); hemi = m.group(2).upper()
                        lon = -abs(val) if hemi == "W" else abs(val)

                if lat is None or lon is None:
                    continue

                name_blob = str(row.get(col_name, "") or "").strip()
                char_blob = str(row.get(col_char, "") or "").strip()
                entries.append({"name_blob": name_blob, "char_blob": char_blob, "lat": lat, "lon": lon})
            if entries:
                return entries
        except Exception:
            continue
    return []

# ===================== WRITERS =====================

def write_buoy_ini(objs: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    out.append("Number={}\n".format(len(objs)))
    for idx, o in enumerate(objs, start=1):
        lon, lat = norm_coords(o["lon"], o["lat"])
        out.append('Type({})="Special"\n'.format(idx))
        out.append("Long({})={:.8f}\n".format(idx, lon))
        out.append("Lat({})={:.8f}\n".format(idx, lat))
        out.append("\n")
    path.write_text("".join(out), encoding="utf-8")

def write_light_ini(objs: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    out.append("Number={}\n\n".format(len(objs)))
    for idx, o in enumerate(objs, start=1):
        color = extract_color(o.get("char_blob", ""))
        period = extract_period_seconds(o.get("char_blob", ""))
        rng = extract_range_nm(o.get("char_blob", ""))
        ch = extract_char_key(o.get("char_blob", ""))
        seq = sequence(ch, period)
        r, g, b = LIGHT_COLOR_RGB.get(color, (255, 255, 255))
        # Attach each light to matching buoy index
        out.append("Buoy({})={}\n".format(idx, idx))
        out.append("Height({})={}\n".format(idx, DEFAULT_HEIGHT_M))
        out.append("Red({})={}\nGreen({})={}\nBlue({})={}\n".format(idx, r, idx, g, idx, b))
        out.append("Range({})={}\n".format(idx, rng))
        out.append('Sequence({})="{}"\n'.format(idx, seq))
        out.append("StartAngle({})=0\nEndAngle({})=360\nFloating({})=1\n\n".format(idx, idx, idx))
    path.write_text("".join(out), encoding="utf-8")

# ======================= MAIN =======================

def main():
    if not INPUT_FILE.exists():
        print("[ERROR] File not found:", INPUT_FILE)
        return

    # Try your two-line text format first; if it yields nothing, try table-like.
    entries = parse_text_two_line_format(INPUT_FILE)
    if not entries:
        entries = parse_table_like(INPUT_FILE)

    if not entries:
        print("[ERROR] No entries parsed. Check INPUT_FILE format.")
        return

    # Filter by BBOX and write
    inside = [e for e in entries if in_bbox(e["lon"], e["lat"])]

    write_buoy_ini(inside, BUOY_OUT)
    write_light_ini(inside, LIGHT_OUT)

    print("Parsed total entries:", len(entries))
    print("Inside bbox:", len(inside))
    print("Wrote:", BUOY_OUT)
    print("Wrote:", LIGHT_OUT)
    if not inside:
        print("Note: If you expected data here, your bbox may not overlap this file's area, or longitude mode may need adjustment.")

if __name__ == "__main__":
    main()

