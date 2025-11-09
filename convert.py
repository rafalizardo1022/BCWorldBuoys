import pdfplumber, pandas as pd, re, sys
from pathlib import Path


pdf_path = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\Light List for District 1.pdf")# your downloaded file
csv_out  = pdf_path.with_suffix(".csv")

rows = []
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            # skip headers and empty lines
            if not line.strip() or line.lower().startswith("no."):
                continue
            # basic pattern: name ... characteristic ... range ... lat ... lon
            m = re.search(r"([0-9]{2,5})\s+(.*?)\s+([A-Z][a-z].*?)\s+(\d{1,2}°.*[NS])\s+(\d{1,3}°.*[EW])", line)
            if m:
                number, name, char, lat, lon = m.groups()
                rows.append({"number": number, "name": name, "char": char, "lat": lat, "lon": lon})

# export to CSV
pd.DataFrame(rows).to_csv(csv_out, index=False)
print(f"Wrote {len(rows)} rows → {csv_out}")
