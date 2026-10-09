# ONSTAR 

Flask + SQLite + Three.js astronomy explorer for Termux.

## Run in Termux

```bash
cd ~/projects/onstar
python -m pip install -r requirements.txt
python -m app.main
```

Open `http://192.0.0.4:5000` while `192.0.0.4` is the current address of the running Termux server. If Android/Termux assigns a different address, use the address printed by Flask.

## API routes

- `/health`
- `/api/stats`
- `/api/stars?q=Sirius&page=1&per_page=50`
- `/api/astronomy/gaia?limit=250&tile=0` (tiles 0–71; cached 10 minutes)
- `/api/astronomy/simbad?q=Sirius`
- `/api/astronomy/exoplanets?q=Kepler`
- `/api/astronomy/jpl?q=Ceres`
- `/api/astronomy/images?q=nebula`

External catalogue APIs are queried only when requested. A service can time out or rate-limit; local stars remain available. Gaia coordinates are degrees. Distances derived from parallax are shown only for positive parallaxes and remain estimates. The visible decorative glow is a rendering effect, not a catalogue record.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- The named-star starter tuples store right ascension in hours; `import_starter()` converts these to degrees when writing SQLite.
- Gaia queries use bounded sky tiles to avoid repeatedly returning the same narrow region.
- API responses are cached in process for 10 minutes.


## Live moving-object coordinates
The UI includes a JPL Horizons panel that requests fresh apparent right ascension and declination for the selected Solar System body and refreshes every 60 seconds. It uses an Earth-centred observer (`500@399`), not a location-specific local horizon or a telescope stream. External service availability and network access are required. Star catalogues such as Gaia remain catalogue measurements, not second-by-second live feeds.

Endpoint: `/api/astronomy/ephemeris?target=599` (Jupiter by default). Supported IDs are documented in `app/astronomy_api.py`.
