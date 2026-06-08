"""Normalise the GDELT 20-year export into a historical baseline layer.

Reads examples/data/gdelt_baseline.json (BigQuery export: directed country-pair
aggregates over ~2005+, ISO3 codes + avg Goldstein + CAMEO quad-class counts) and
writes a clean per-pair signed "historical" stance keyed by our country names.

    python examples/extract_gdelt_baseline.py
        → examples/data/world_observer_gdelt.json
"""

from __future__ import annotations

import json
from pathlib import Path

SRC = Path(__file__).parent / "data" / "gdelt_baseline.json"
OUT = Path(__file__).parent / "data" / "world_observer_gdelt.json"
MIN_EVENTS = 1000  # 20-year directed pair must have >= this many events to count

NAME_ISO3 = {
    "Afghanistan": "AFG",
    "Albania": "ALB",
    "Algeria": "DZA",
    "Argentina": "ARG",
    "Armenia": "ARM",
    "Australia": "AUS",
    "Azerbaijan": "AZE",
    "Bahrain": "BHR",
    "Bangladesh": "BGD",
    "Belarus": "BLR",
    "Bolivia": "BOL",
    "Bosnia and Herzegovina": "BIH",
    "Brazil": "BRA",
    "Burkina Faso": "BFA",
    "Cambodia": "KHM",
    "Canada": "CAN",
    "Chile": "CHL",
    "China": "CHN",
    "Colombia": "COL",
    "Congo": "COG",
    "Cuba": "CUB",
    "Cyprus": "CYP",
    "Czech Republic": "CZE",
    "DR Congo": "COD",
    "Denmark": "DNK",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "Estonia": "EST",
    "Ethiopia": "ETH",
    "Finland": "FIN",
    "France": "FRA",
    "Germany": "DEU",
    "Ghana": "GHA",
    "Greece": "GRC",
    "Guatemala": "GTM",
    "Hong Kong": "HKG",
    "Hungary": "HUN",
    "India": "IND",
    "Indonesia": "IDN",
    "Iran": "IRN",
    "Ireland": "IRL",
    "Israel": "ISR",
    "Italy": "ITA",
    "Ivory Coast": "CIV",
    "Jamaica": "JAM",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Kazakhstan": "KAZ",
    "Kenya": "KEN",
    "Kuwait": "KWT",
    "Kyrgyzstan": "KGZ",
    "Laos": "LAO",
    "Latvia": "LVA",
    "Lebanon": "LBN",
    "Luxembourg": "LUX",
    "Malaysia": "MYS",
    "Mali": "MLI",
    "Mexico": "MEX",
    "Montenegro": "MNE",
    "Morocco": "MAR",
    "Myanmar": "MMR",
    "Namibia": "NAM",
    "Nepal": "NPL",
    "Netherlands": "NLD",
    "New Zealand": "NZL",
    "Niger": "NER",
    "Nigeria": "NGA",
    "North Korea": "PRK",
    "Norway": "NOR",
    "Pakistan": "PAK",
    "Palestine": "PSE",
    "Panama": "PAN",
    "Papua New Guinea": "PNG",
    "Paraguay": "PRY",
    "Philippines": "PHL",
    "Poland": "POL",
    "Portugal": "PRT",
    "Qatar": "QAT",
    "Romania": "ROU",
    "Russia": "RUS",
    "Rwanda": "RWA",
    "Saudi Arabia": "SAU",
    "Senegal": "SEN",
    "Serbia": "SRB",
    "Singapore": "SGP",
    "Slovakia": "SVK",
    "Somalia": "SOM",
    "South Africa": "ZAF",
    "South Korea": "KOR",
    "Sudan": "SDN",
    "Sweden": "SWE",
    "Switzerland": "CHE",
    "Syria": "SYR",
    "Taiwan": "TWN",
    "Thailand": "THA",
    "Timor-Leste": "TLS",
    "Tunisia": "TUN",
    "Turkey": "TUR",
    "Uganda": "UGA",
    "Ukraine": "UKR",
    "United Kingdom": "GBR",
    "United States": "USA",
    "Uruguay": "URY",
    "Uzbekistan": "UZB",
    "Venezuela": "VEN",
    "Vietnam": "VNM",
    "Yemen": "YEM",
    "Zimbabwe": "ZWE",
}
ISO3_NAME = {v: k for k, v in NAME_ISO3.items()}


def main() -> None:
    if not SRC.exists():
        print(f"{SRC} not found — export the GDELT BigQuery query there first.")
        return
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        a, b = ISO3_NAME.get(r["a"]), ISO3_NAME.get(r["b"])
        if not a or not b or a == b or int(r["events"]) < MIN_EVENTS:
            continue
        out.append(
            {
                "a": a,
                "b": b,
                "net": round(float(r["avg_goldstein"]), 2),  # net tone over ~20y (-10..+10)
                "events": int(r["events"]),
            }
        )
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(out)} historical directed pairs (>= {MIN_EVENTS} events) -> {OUT}")


if __name__ == "__main__":
    main()
