#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NOAA / USCG Light-List  ➜  Bridge Command  (Buoy.ini + Light.ini)

• Filters to a chosen bounding box (area lock)
• Works with CSV that has lat+lon on the same line
• Infers correct Bridge Command buoy type from colour / structure
"""

from __future__ import annotations
import re, csv
from pathlib import Path

# ============================================================
# 🔧 CONFIGURATION
# ============================================================

INPUT_FILE = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\Discrict1.csv")
OUTPUT_DIR = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\output")

# ---- Area-lock (bounding box) ----
# Use decimal degrees  (W longitudes are negative)
MIN_LAT, MAX_LAT = 40.35, 40.73         # Dominican Republic example
MIN_LON, MAX_LON = -74.36, -73.88

DEFAULT_HEIGHT_M = 10.0
DEFAULT_RANGE_NM = 10.0
DEFAULT_PERIOD_S = 4.0

# ============================================================
# 🧩 HELPERS
# ============================================================

def dms_to_decimal(dms: str) -> float | None:
    m = re.match(r"(\d+)[^\d]+(\d+)[^\d]+(\d+(?:\.\d+)?)([NSEW])", dms.strip(), re.I)
    if not m:
        return None
    d, mnt, s, hemi = m.groups()
    val = float(d) + float(mnt)/60 + float(s)/3600
    if hemi.upper() in ("S","W"):
        val = -val
    return val

def extract_color(txt: str) -> str:
    t = (txt or "").upper()
    if "RED" in t or re.search(r"\bR\b", t):    return "red"
    if "GREEN" in t or re.search(r"\bG\b", t):  return "green"
    if "YELLOW" in t or "AMBER" in t or re.search(r"\bY\b", t): return "yellow"
    return "white"

def extract_period_seconds(txt: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*s", txt, re.I)
    return float(m.group(1)) if m else DEFAULT_PERIOD_S

def extract_range_nm(txt: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*M\b", txt, re.I)
    return float(m.group(1)) if m else DEFAULT_RANGE_NM

def extract_height_m(txt: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*m\b", txt, re.I)
    return float(m.group(1)) if m else DEFAULT_HEIGHT_M

def sequence(ch: str, period: float) -> str:
    ticks = max(4, min(80, int(round(period / 0.25))))
    if "FL" in ch.upper():
        on = int(0.5 / 0.25)
        return "L"*on + "D"*(ticks-on)
    if "ISO" in ch.upper():
        return "L"*(ticks//2) + "D"*(ticks - ticks//2)
    if "OC" in ch.upper():
        on = int(ticks*0.6)
        return "L"*on + "D"*(ticks-on)
    return "L"

# ============================================================
# ⚓ TYPE-INFERENCE LOGIC
# ============================================================

def infer_type(text: str) -> str:
    t = (text or "").upper()

    if "CARDINAL" in t:
        if "NORTH" in t: return "north_small"
        if "EAST"  in t: return "east_small"
        if "SOUTH" in t: return "south_small"
        if "WEST"  in t: return "west_small"
        return "north_small"

    if "MO(A)" in t or "MORSE (A)" in t or "R/W" in t or "RW" in t:
        return "safe"

    if "ISOLATED" in t or "DANGER" in t or "(2)" in t:
        return "danger_small"

    if "YELLOW" in t or "AMBER" in t:
        return "special_small"
    if any(k in t for k in ["CABLE","ANCHOR","RESEARCH","OBSTRUCTION","TEMP"]):
        return "special_small"

    if "RG" in t or "R/G" in t or "RED AND GREEN" in t:
        return "pref_stbd_small"
    if "GR" in t or "G/R" in t or "GREEN AND RED" in t:
        return "pref_port_small"

    if "R NUN" in t or ("RED" in t and "NUN" in t):
        return "stbd_post"
    if "G CAN" in t or ("GREEN" in t and "CAN" in t):
        return "port_post"
    if "RED" in t or re.search(r"\bR\b", t):
        return "stbd_small"
    if "GREEN" in t or re.search(r"\bG\b", t):
        return "port_small"

    if "MOOR" in t or "ANCHOR" in t:
        return "mooring"

    return "special_small"

# ============================================================
# 🚀 CONVERTER
# ============================================================

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for line in reader:
            if not any(line): 
                continue
            row = [c.strip() for c in line if c.strip()]
            if len(row) < 4:
                continue

            name = row[0]
            lat = dms_to_decimal(row[1])
            lon = dms_to_decimal(row[2])
            char = " ".join(row[3:])

            if lat is None or lon is None:
                continue

            # --- 🧭 Area-lock filter ---
            if not (MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON):
                continue

            rows.append({"name": name, "lat": lat, "lon": lon, "char": char})

    print(f"Parsed {len(rows)} entries inside bounding box.")

    # ---------- Write Buoy.ini ----------
    lines_buoy = [f"Number={len(rows)}\n"]
    for i, r in enumerate(rows, start=1):
        btype = infer_type(r["char"])
        lines_buoy.append(f'Type({i})="{btype}"\n')
        lines_buoy.append(f"Long({i})={r['lon']:.6f}\n")
        lines_buoy.append(f"Lat({i})={r['lat']:.6f}\n\n")
    (OUTPUT_DIR / "Buoy.ini").write_text("".join(lines_buoy), encoding="utf-8")

    # ---------- Write Light.ini ----------
    lines_light = [f"Number={len(rows)}\n\n"]
    for i, r in enumerate(rows, start=1):
        color = extract_color(r["char"])
        period = extract_period_seconds(r["char"])
        rng = extract_range_nm(r["char"])
        hgt = extract_height_m(r["char"])
        seq = sequence(r["char"], period)

        rgb = {
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "yellow": (255, 255, 0),
            "white": (255, 255, 255)
        }.get(color, (255, 255, 255))
        rcol, gcol, bcol = rgb

        lines_light += [
            f"Buoy({i})={i}\n",
            f"Height({i})={hgt}\n",
            f"Red({i})={rcol}\nGreen({i})={gcol}\nBlue({i})={bcol}\n",
            f"Range({i})={rng}\n",
            f'Sequence({i})="{seq}"\n',
            "StartAngle({})=0\nEndAngle({})=360\nFloating({})=1\n\n".format(i, i, i)
        ]

    (OUTPUT_DIR / "Light.ini").write_text("".join(lines_light), encoding="utf-8")
    print(f"✅ Created Buoy.ini and Light.ini in {OUTPUT_DIR}")

# ============================================================

if __name__ == "__main__":
    main()
