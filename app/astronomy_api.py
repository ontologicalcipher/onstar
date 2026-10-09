"""Backend adapters for public astronomy services. Results are cached briefly."""
import csv
import io
import json
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request

astronomy = Blueprint("astronomy", __name__)
GAIA = "https://gea.esac.esa.int/tap-server/tap/sync"
SIMBAD = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
EXOPLANETS = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
JPL = "https://ssd-api.jpl.nasa.gov/sbdb.api"
NASA_IMAGES = "https://images-api.nasa.gov/search"

_cache = {}
_cache_lock = threading.Lock()
CACHE_SECONDS = 600


def cached(key, loader, ttl=CACHE_SECONDS):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1], True
    value = loader()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value, False


def get_url(url, params, timeout=25):
    request_url = url + "?" + urlencode(params)
    req = Request(request_url, headers={
        "User-Agent": "ONSTAR/0.2 astronomy-explorer",
        "Accept": "application/json, text/csv, */*",
    })
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")


def csv_rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def normalize_gaia(row):
    """Normalize Gaia's degree coordinates and nullable astrometry."""
    source_id = str(row.get("source_id", ""))
    parallax = row.get("parallax")
    try:
        parallax = float(parallax) if parallax is not None else None
    except (TypeError, ValueError):
        parallax = None
    distance_ly = 3261.56 / parallax if parallax and parallax > 0 else None
    return {
        "id": "Gaia DR3 " + source_id,
        "name": "Gaia DR3 " + source_id,
        "catalog_id": source_id,
        "source": "ESA Gaia DR3",
        "ra": float(row["ra"]),
        "dec": float(row["dec"]),
        "parallax_mas": parallax,
        "distance_ly": distance_ly,
        "magnitude": _float_or_none(row.get("phot_g_mean_mag")),
        "color_index": _float_or_none(row.get("bp_rp")),
        "temperature_k": _float_or_none(row.get("teff_gspphot")),
        "spectral_type": None,
        "distance_quality": "positive-parallax estimate" if distance_ly else "unavailable: parallax missing or non-positive",
    }


def _float_or_none(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fetch_gaia(limit=100, tile=0):
    # A bounded RA/Dec tile avoids scanning the same small patch of sky on every request.
    # Tile index cycles through a coarse all-sky grid. Coordinates returned by Gaia are degrees.
    tile = max(0, int(tile))
    ra_start = (tile % 12) * 30
    dec_band = ((tile // 12) % 6)
    dec_start = -90 + dec_band * 30
    dec_end = min(90, dec_start + 30)
    ra_end = ra_start + 30
    query = (
        f"SELECT TOP {limit} source_id, ra, dec, parallax, phot_g_mean_mag, bp_rp, teff_gspphot "
        f"FROM gaiadr3.gaia_source WHERE ra >= {ra_start} AND ra < {ra_end} "
        f"AND dec >= {dec_start} AND dec < {dec_end} "
        "AND phot_g_mean_mag IS NOT NULL"
    )
    raw = get_url(GAIA, {
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query,
    }, timeout=90)
    data = json.loads(raw)
    fields = [x["name"] for x in data.get("metadata", [])]
    rows = [dict(zip(fields, row)) for row in data.get("data", [])]
    return [normalize_gaia(row) for row in rows]


@astronomy.get("/api/astronomy/gaia")
def gaia():
    limit = min(500, max(1, request.args.get("limit", 100, type=int)))
    tile = min(71, max(0, request.args.get("tile", 0, type=int)))
    key = ("gaia", limit, tile)
    try:
        items, was_cached = cached(key, lambda: fetch_gaia(limit, tile))
        return jsonify({"source": "ESA Gaia DR3", "items": items,
                        "count": len(items), "tile": tile, "cached": was_cached,
                        "note": "Gaia positions are catalogue coordinates; distances are estimates only for positive parallaxes."})
    except Exception:
        return jsonify({"error": "Gaia query failed",
                        "detail": "The Gaia service timed out or returned an error. Retry later; local catalogue remains available."}), 502


@astronomy.get("/api/astronomy/simbad")
def simbad():
    q = request.args.get("q", "").strip()[:100]
    if not q:
        return jsonify({"error": "Supply ?q=Sirius"}), 400
    safe = q.replace("\\", "\\\\").replace("'", "''")
    query = ("SELECT TOP 20 main_id, ra, dec, otype, plx_value "
             "FROM basic WHERE main_id LIKE '%" + safe + "%'")
    try:
        def load():
            return csv_rows(get_url(SIMBAD, {"query": query, "format": "csv"}))
        items, was_cached = cached(("simbad", q.lower()), load)
        return jsonify({"source": "SIMBAD", "items": items, "cached": was_cached})
    except Exception:
        return jsonify({"error": "SIMBAD lookup failed", "detail": "Remote service unavailable; try again later."}), 502


@astronomy.get("/api/astronomy/exoplanets")
def exoplanets():
    q = request.args.get("q", "").strip()[:100]
    query = ("SELECT TOP 100 pl_name, hostname, ra, dec, sy_dist, discoverymethod "
             "FROM ps WHERE ra IS NOT NULL AND dec IS NOT NULL")
    if q:
        safe = q.replace("'", "''")
        query += f" AND (pl_name LIKE '%{safe}%' OR hostname LIKE '%{safe}%')"
    try:
        def load():
            return json.loads(get_url(EXOPLANETS, {"query": query, "format": "json"}))
        data, was_cached = cached(("exoplanets", q.lower()), load)
        return jsonify({"source": "NASA Exoplanet Archive", "items": data,
                        "cached": was_cached})
    except Exception:
        return jsonify({"error": "Exoplanet query failed", "detail": "NASA archive unavailable; try again later."}), 502


@astronomy.get("/api/astronomy/jpl")
def jpl():
    q = request.args.get("q", "").strip()[:100]
    if not q:
        return jsonify({"error": "Supply ?q=Ceres"}), 400
    try:
        data, was_cached = cached(("jpl", q.lower()), lambda: json.loads(get_url(
            JPL, {"sstr": q, "phys-par": "true", "orbit": "true"}, timeout=25)))
        return jsonify({"source": "NASA JPL Small-Body Database", "object": data,
                        "cached": was_cached})
    except Exception:
        return jsonify({"error": "JPL lookup failed", "detail": "JPL service unavailable; try again later."}), 502


@astronomy.get("/api/astronomy/images")
def images():
    q = request.args.get("q", "nebula").strip()[:100]
    try:
        def load():
            data = json.loads(get_url(NASA_IMAGES, {
                "q": q, "media_type": "image", "page_size": 20,
            }))
            items = []
            for item in data.get("collection", {}).get("items", []):
                meta = item.get("data", [{}])[0]
                links = item.get("links", [])
                items.append({
                    "title": meta.get("title"), "description": meta.get("description"),
                    "date_created": meta.get("date_created"), "nasa_id": meta.get("nasa_id"),
                    "url": links[0].get("href") if links else None,
                })
            return items
        items, was_cached = cached(("images", q.lower()), load)
        return jsonify({"source": "NASA Image and Video Library", "items": items,
                        "cached": was_cached})
    except Exception:
        return jsonify({"error": "NASA image search failed", "detail": "NASA Images service unavailable; try again later."}), 502


@astronomy.get("/api/astronomy/search")
def search():
    q = request.args.get("q", "").strip()[:100]
    if not q:
        return jsonify({"error": "Supply ?q=Sirius"}), 400
    return jsonify({
        "query": q,
        "sources": {
            "SIMBAD": "/api/astronomy/simbad?q=" + q,
            "Gaia": "/api/astronomy/gaia?limit=100&tile=0",
            "Exoplanets": "/api/astronomy/exoplanets?q=" + q,
            "JPL": "/api/astronomy/jpl?q=" + q,
            "NASA Images": "/api/astronomy/images?q=" + q,
        },
    })


# Live observer ephemeris from NASA/JPL Horizons. Unlike a star catalogue,
# this endpoint calculates a moving Solar System object's apparent position
# for the requested epoch. Results are deliberately not cached.
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"

@astronomy.get("/api/astronomy/ephemeris")
def ephemeris():
    """Get a current topocentric/geocentric apparent position from JPL Horizons.

    Example: /api/astronomy/ephemeris?target=599
    Common target IDs: Sun=10, Mercury=199, Venus=299, Earth=399,
    Mars=499, Jupiter=599, Saturn=699, Uranus=799, Neptune=899, Moon=301.
    CENTER=500@399 is Earth-centred; use a Horizons site code/coordinates
    for a local horizon view in a future extension.
    """
    target = request.args.get("target", "599").strip()[:30]
    allowed = {"10", "199", "299", "399", "499", "599", "699", "799", "899", "301"}
    if target not in allowed:
        return jsonify({"error": "Unsupported target", "allowed_targets": sorted(allowed)}), 400
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stop = now + timedelta(minutes=2)
    params = {
        "format": "json", "COMMAND": f"'{target}'", "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES", "EPHEM_TYPE": "OBSERVER", "CENTER": "'500@399'",
        "START_TIME": f"'{now.strftime('%Y-%m-%d %H:%M')}'",
        "STOP_TIME": f"'{stop.strftime('%Y-%m-%d %H:%M')}'", "STEP_SIZE": "'1 m'",
        "QUANTITIES": "'1,2,4,9,20'", "CSV_FORMAT": "YES",
    }
    try:
        payload = json.loads(get_url(HORIZONS, params, timeout=35))
        result_text = payload.get("result", "")
        if payload.get("error") or "$$SOE" not in result_text:
            return jsonify({"error": "JPL Horizons returned no ephemeris", "detail": "Try again shortly."}), 502
        section = result_text.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
        # Horizons CSV quantities: calendar date, RA, DEC, apparent azimuth,
        # apparent elevation, range. Preserve the raw row if service format changes.
        row = next((line.strip() for line in section.splitlines() if line.strip()), "")
        values = next(csv.reader([row])) if row else []
        if len(values) < 3:
            return jsonify({"error": "Unrecognized JPL ephemeris format", "raw": row[:300]}), 502
        return jsonify({
            "source": "NASA/JPL Horizons", "target_id": target,
            "target_name": {"10":"Sun","199":"Mercury","299":"Venus","399":"Earth","499":"Mars","599":"Jupiter","699":"Saturn","799":"Uranus","899":"Neptune","301":"Moon"}.get(target, target),
            "epoch_utc": now.isoformat(), "ra": values[1].strip(), "dec": values[2].strip(),
            "raw_row": row, "center": "Earth center (500@399)",
            "note": "Fresh apparent ephemeris from JPL Horizons; not a live telescope feed."
        })
    except Exception:
        return jsonify({"error": "JPL Horizons unavailable", "detail": "The ephemeris service timed out or returned an error. Retry shortly."}), 502
