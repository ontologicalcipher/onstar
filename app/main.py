from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "stars.db"

app = Flask(
    __name__,
    template_folder=str(BASE / "app" / "templates"),
    static_folder=str(BASE / "app" / "static"),
)

STARTER_STARS = [
    ("Sirius", "HIP 32349", -1.46, 6.7525, -16.7161, 379.21, 2.637, 8.60, 1.45, 0.00, 9940, "A1V"),
    ("Canopus", "HIP 30438", -0.74, 6.3992, -52.6957, 10.55, 94.79, 309.1, -2.52, 0.15, 7350, "A9II"),
    ("Arcturus", "HIP 69673", -0.05, 14.2610, 19.1824, 88.83, 11.26, 36.72, -0.30, 1.23, 4286, "K1.5IIIp"),
    ("Vega", "HIP 91262", 0.03, 18.6156, 38.7837, 130.23, 7.68, 25.04, 0.58, 0.00, 9602, "A0V"),
    ("Capella", "HIP 24608", 0.08, 5.2782, 45.9980, 76.20, 13.12, 42.79, -0.48, 0.80, 4970, "G8III + G0III"),
    ("Rigel", "HIP 24436", 0.13, 5.2423, -8.2016, 3.78, 264.55, 862.8, -7.84, -0.03, 12100, "B8Ia"),
    ("Procyon", "HIP 37279", 0.34, 7.6550, 5.2250, 285.93, 3.50, 11.41, 2.68, 0.42, 6530, "F5IV-V"),
    ("Betelgeuse", "HIP 27989", 0.42, 5.9195, 7.4071, 5.95, 168.07, 548.2, -5.14, 1.85, 3600, "M1-2Ia-ab"),
    ("Achernar", "HIP 7588", 0.46, 1.6286, -57.2368, 23.39, 42.75, 139.4, -1.77, -0.16, 15000, "B6Vep"),
    ("Altair", "HIP 97649", 0.77, 19.8464, 8.8683, 194.95, 5.13, 16.74, 2.21, 0.22, 7550, "A7V"),
    ("Aldebaran", "HIP 21421", 0.85, 4.5987, 16.5093, 50.09, 19.96, 65.10, -0.63, 1.54, 3910, "K5III"),
    ("Antares", "HIP 80763", 0.96, 16.4901, -26.4319, 5.89, 169.78, 553.7, -5.28, 1.83, 3660, "M1.5Iab-b"),
    ("Spica", "HIP 65474", 0.98, 13.4199, -11.1614, 12.44, 80.39, 262.1, -3.55, -0.23, 22400, "B1III-IV + B4V"),
    ("Pollux", "HIP 37826", 1.14, 7.7553, 28.0262, 96.54, 10.36, 33.79, 1.08, 1.00, 4770, "K0IIIb"),
    ("Deneb", "HIP 102098", 1.25, 20.6905, 45.2803, 2.31, 432.90, 1411.8, -8.38, 0.09, 8525, "A2Ia"),
    ("Regulus", "HIP 49669", 1.40, 10.1395, 11.9672, 41.13, 24.31, 79.30, -0.57, -0.11, 12460, "B7V"),
    ("Polaris", "HIP 11767", 1.98, 2.5303, 89.2641, 7.54, 132.63, 432.6, -3.64, 0.60, 6015, "F7Ib-II"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS stars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id TEXT NOT NULL UNIQUE,
    proper_name TEXT,
    ra REAL NOT NULL,
    dec REAL NOT NULL,
    parallax REAL,
    distance_pc REAL,
    distance_ly REAL,
    apparent_mag REAL,
    absolute_mag REAL,
    color_index REAL,
    temperature REAL,
    spectral_type TEXT,
    source_catalog TEXT NOT NULL,
    import_timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stars_name ON stars(proper_name);
CREATE INDEX IF NOT EXISTS idx_stars_catalog ON stars(catalog_id);
CREATE INDEX IF NOT EXISTS idx_stars_mag ON stars(apparent_mag);
"""

def get_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as con:
        con.executescript(SCHEMA)

def import_starter():
    init_db()
    timestamp = datetime.now(timezone.utc).isoformat()

    sql = """
    INSERT INTO stars (
        catalog_id, proper_name, ra, dec, parallax, distance_pc, distance_ly,
        apparent_mag, absolute_mag, color_index, temperature, spectral_type,
        source_catalog, import_timestamp
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(catalog_id) DO UPDATE SET
        proper_name=excluded.proper_name,
        ra=excluded.ra,
        dec=excluded.dec,
        parallax=excluded.parallax,
        distance_pc=excluded.distance_pc,
        distance_ly=excluded.distance_ly,
        apparent_mag=excluded.apparent_mag,
        absolute_mag=excluded.absolute_mag,
        color_index=excluded.color_index,
        temperature=excluded.temperature,
        spectral_type=excluded.spectral_type,
        source_catalog=excluded.source_catalog,
        import_timestamp=excluded.import_timestamp
    """

    with get_db() as con:
        for name, catalog, mag, ra, dec, parallax, pc, ly, absolute, color, temp, spectral in STARTER_STARS:
            con.execute(sql, (
                catalog, name, ra, dec, parallax, pc, ly, mag, absolute,
                color, temp, spectral, "Hipparcos named-star starter set", timestamp
            ))

    return len(STARTER_STARS)

def get_pagination():
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    try:
        per_page = int(request.args.get("per_page", "50"))
    except ValueError:
        per_page = 50

    return page, min(max(per_page, 1), 200)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    init_db()
    return jsonify({"status": "ok", "database": "sqlite", "catalog": "local"})

@app.get("/api/stats")
def stats():
    init_db()
    with get_db() as con:
        total = con.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
        named = con.execute(
            "SELECT COUNT(*) FROM stars WHERE proper_name IS NOT NULL"
        ).fetchone()[0]
        latest = con.execute(
            "SELECT MAX(import_timestamp) FROM stars"
        ).fetchone()[0]

    return jsonify({
        "total_objects": total,
        "named_objects": named,
        "latest_import": latest,
        "data_mode": "catalog-backed",
    })

@app.get("/api/stars")
def stars():
    init_db()
    query = request.args.get("q", "").strip()
    page, per_page = get_pagination()
    offset = (page - 1) * per_page

    if query:
        pattern = f"%{query}%"
        where = "WHERE proper_name LIKE ? OR catalog_id LIKE ?"
        params = [pattern, pattern]
    else:
        where = ""
        params = []

    with get_db() as con:
        total = con.execute(
            f"SELECT COUNT(*) FROM stars {where}", params
        ).fetchone()[0]

        rows = con.execute(
            f"""
            SELECT id, catalog_id, proper_name, CASE WHEN source_catalog = 'Hipparcos named-star starter set' THEN ra * 15.0 ELSE ra END AS ra, dec, distance_pc,
                   distance_ly, apparent_mag, color_index, temperature,
                   spectral_type, source_catalog
            FROM stars
            {where}
            ORDER BY apparent_mag ASC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

    return jsonify({
        "items": [dict(row) for row in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if total else 0,
    })

@app.get("/api/stars/<int:star_id>")
def star(star_id):
    init_db()
    with get_db() as con:
        row = con.execute(
            "SELECT * FROM stars WHERE id = ?", (star_id,)
        ).fetchone()

    if row is None:
        return jsonify({"error": "Star not found"}), 404

    record = dict(row)
    if record.get("source_catalog") == "Hipparcos named-star starter set":
        record["ra"] = record["ra"] * 15.0
    return jsonify(record)


from app.astronomy_api import astronomy
app.register_blueprint(astronomy)


if __name__ == "__main__":
    print(f"ONSTAR catalog ready: {import_starter()} starter objects")
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )

