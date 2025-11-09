
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parse NOAA/USCG Light List 'CSV' that is really quoted text with multi-line records:
  Line A (lat line): "... <NAME> ... 44-32-15.837N  [Characteristic here]"
  Line B (lon line): "067-05-13.808W ..."

This script:
  • Reads the text file line-by-line (no real commas/tabs needed)
  • Detects latitude lines (…N/…S) and pairs them with the next longitude line (…E/…W)
  • Extracts name, characteristic, lat/lon
  • Filters by bounding box
  • Outputs Bridge Command: Buoy.ini and Light.ini
"""

from __future__ import annotations
import re
from pathlib import Path

# ===================== CONFIG (edit me) =====================

INPUT_FILE = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\Light List for District 1.csv")

# Bounding box (set to New England if testing District 1; set to DR for your maps)
# Dominican Republic example:
# MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = -71.7, 17.3, -68.3, 19.9
MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = -74.36, 40.35, -73.88, 40.73  # District 1 test bbox


OUTPUT_DIR = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\output")
BUOY_OUT  = OUTPUT_DIR / "Buoy.ini"
LIGHT_OUT = OUTPUT_DIR / "Light.ini"

DEFAULT_PERIOD_S  = 4.0
DEFAULT_RANGE_NM  = 6.0
DEFAULT_HEIGHT_M  = 12.0

# Map color words/initials to RGB
LIGHT_COLOR_RGB = {
    "white": (255,255,255),
    "red":   (255,0,0),
    "green": (0,255,0),
    "yellow":(255,255,0),
    "blue":  (0,0,255),
}

# ===================== Helpers =====================

def in_bbox(lon, lat) -> bool:
    return (MIN_LON <= lon <= MAX_LON) and (MIN_LAT <= lat <= MAX_LAT)

# Match HHH-MM-SS.SSS[NSEW]  (degrees-min-sec with hyphens, as in your file)
DMS_RE = re.compile(r"(\d{2,3})-(\d{2})-(\d{2}(?:\.\d+)?)\s*([NSEW])\b")

def dms_to_decimal(d: str, m: str, s: str, hemi: str) -> float:
    val = int(d) + int(m)/60 + float(s)/3600
    if hemi.upper() in ("S","W"): val = -val
    return val

# Characteristic parsing (very tolerant)
def extract_color(text: str) -> str:
    t = text.lower()
    for w,c in [("white","white"),("red","red"),("green","green"),("yellow","yellow"),("blue","blue")]:
        if w in t: return c
    # abbr fallback
    if re.search(r"\bW\b", text): return "white"
    if re.search(r"\bR\b", text): return "red"
    if re.search(r"\bG\b", text): return "green"
    if re.search(r"\bY\b", text): return "yellow"
    if re.search(r"\bB\b", text): return "blue"
    return "white"

def extract_period_seconds(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*s\b", text, re.I)  # e.g., "15s"
    return float(m.group(1)) if m else DEFAULT_PERIOD_S

def extract_range_nm(text: str) -> float:
    # Light List uses M for nautical miles; try to avoid matching minutes by using word boundary
    m = re.search(r"(\d+(?:\.\d+)?)\s*M\b", text)
    return float(m.group(1)) if m else DEFAULT_RANGE_NM

def extract_char_key(text: str) -> str:
    t = text.lower()
    for key in ["iso","oc","lfl","ffl","fl","vq","q"]:
        if re.search(rf"\b{key}\b", t): return key.upper()
    return "FIX"

def sequence(ch: str, period_s: float) -> str:
    """Bridge Command sequence: 'L'/'D' quater-second ticks."""
    P = period_s if period_s > 0.5 else DEFAULT_PERIOD_S
    ticks = max(4, min(80, int(round(P / 0.25))))
    if ch.startswith("FL"):  # single flash ~0.5s on
        on = max(1, int(round(0.5/0.25)))
        return "L"*on + "D"*(ticks-on)
    if ch.startswith("LFL"):  # long flash ~2s
        on = max(1, int(round(2.0/0.25)))
        return "L"*min(on,ticks-1) + "D"*max(1,ticks-on)
    if ch.startswith("ISO"):
        return "L"*(ticks//2) + "D"*(ticks - ticks//2)
    if ch.startswith("OC"):
        on = int(round(ticks*0.6))
        return "L"*on + "D"*(ticks-on)
    if ch in ("Q","VQ"):
        return "LD"*(ticks//2) or "LD"
    return "L"

# ===================== Parsing core =====================

def parse_file(path: Path):
    """
    Reads the quoted, line-based file.
    Detects a LAT line (contains ...N or ...S) then pairs it with the next LON line (...E or ...W).
    Extracts:
      - name_blob: text before the latitude token on the LAT line
      - char_blob: text after the latitude token on the LAT line (often has 'Fl W 10s', range, etc.)
      - lat, lon: decimal degrees
    """
    entries = []
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read all lines, strip quotes and whitespace
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = [ln.strip().strip('"') for ln in f if ln.strip().strip('"')]

    i = 0
    while i < len(lines):
        line = lines[i]
        # Look for a latitude token on this line
        latm = DMS_RE.search(line)
        if latm and latm.group(4).upper() in ("N","S"):
            # Extract name blob (text before the latitude token) and char blob (after)
            name_blob = line[:latm.start()].strip()
            char_blob = line[latm.end():].strip()
            d, m, s, hemi = latm.groups()
            lat = dms_to_decimal(d, m, s, hemi)

            # Now find the next line that has a longitude token
            lon = None
            j = i + 1
            while j < len(lines):
                lonm = DMS_RE.search(lines[j])
                if lonm and lonm.group(4).upper() in ("E","W"):
                    d2, m2, s2, hemi2 = lonm.groups()
                    lon = dms_to_decimal(d2, m2, s2, hemi2)
                    i = j  # jump ahead
                    break
                j += 1

            if lon is not None:
                entries.append({
                    "name_blob": " ".join(name_blob.split()),
                    "char_blob": " ".join(char_blob.split()),
                    "lat": lat,
                    "lon": lon,
                })
        i += 1

    return entries

# ===================== Bridge Command writers =====================

def write_buoy_ini(objs, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"Number={len(objs)}\n"]
    for idx, o in enumerate(objs, start=1):
        lines.append(f'Type({idx})="Special"\n')
        lines.append(f"Long({idx})={o['lon']:.8f}\n")
        lines.append(f"Lat({idx})={o['lat']:.8f}\n\n")
    path.write_text("".join(lines), encoding="utf-8")

def write_light_ini(objs, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"Number={len(objs)}\n\n"]
    for idx, o in enumerate(objs, start=1):
        color = extract_color(o["char_blob"])
        period = extract_period_seconds(o["char_blob"])
        rng = extract_range_nm(o["char_blob"])
        ch = extract_char_key(o["char_blob"])
        seq = sequence(ch, period)
        r,g,b = LIGHT_COLOR_RGB.get(color, (255,255,255))

        lines.append(f"Buoy({idx})={idx}\n")
        lines.append(f"Height({idx})={DEFAULT_HEIGHT_M}\n")
        lines.append(f"Red({idx})={r}\nGreen({idx})={g}\nBlue({idx})={b}\n")
        lines.append(f"Range({idx})={rng}\n")
        lines.append(f'Sequence({idx})="{seq}"\n')
        lines.append(f"StartAngle({idx})=0\nEndAngle({idx})=360\nFloating({idx})=1\n\n")
    path.write_text("".join(lines), encoding="utf-8")

# ===================== Main =====================

def main():
    entries = parse_file(INPUT_FILE)

    # Filter by bbox
    inside = [e for e in entries if in_bbox(e["lon"], e["lat"])]

    # Write Bridge Command files
    write_buoy_ini(inside, BUOY_OUT)
    write_light_ini(inside, LIGHT_OUT)

    print(f"Parsed total entries: {len(entries)}")
    print(f"Inside bbox: {len(inside)}")
    print(f"Wrote: {BUOY_OUT}")
    print(f"Wrote: {LIGHT_OUT}")

if __name__ == "__main__":
    main()
