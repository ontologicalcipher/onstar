import json
import unittest
from unittest.mock import patch

from app.main import app
from app.astronomy_api import normalize_gaia


class OnstarTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_home_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ONSTAR", response.data)

    def test_local_stars_endpoint(self):
        response = self.client.get("/api/stars?per_page=20")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("items", payload)
        self.assertGreaterEqual(payload["total"], 16)

    def test_gaia_normalization_and_distance(self):
        star = normalize_gaia({
            "source_id": 123, "ra": 45.5, "dec": -12.25,
            "parallax": 10, "phot_g_mean_mag": 12.2,
            "bp_rp": 0.8, "teff_gspphot": 5000
        })
        self.assertEqual(star["id"], "Gaia DR3 123")
        self.assertAlmostEqual(star["ra"], 45.5)
        self.assertAlmostEqual(star["distance_ly"], 326.156)
        self.assertEqual(star["source"], "ESA Gaia DR3")

    def test_negative_parallax_not_used_as_distance(self):
        star = normalize_gaia({
            "source_id": 2, "ra": 1, "dec": 2, "parallax": -0.2,
            "phot_g_mean_mag": 19, "bp_rp": None, "teff_gspphot": None
        })
        self.assertIsNone(star["distance_ly"])
        self.assertIn("unavailable", star["distance_quality"])

    def test_gaia_route_returns_normalized_records(self):
        fake = [{
            "id": "Gaia DR3 1", "name": "Gaia DR3 1", "catalog_id": "1",
            "source": "ESA Gaia DR3", "ra": 45.0, "dec": 2.0,
            "parallax_mas": 2.0, "distance_ly": 1630.78,
            "magnitude": 12.0, "color_index": None, "temperature_k": None,
            "spectral_type": None, "distance_quality": "positive-parallax estimate"
        }]
        with patch("app.astronomy_api.fetch_gaia", return_value=fake):
            # use a unique tile/limit key to avoid cached state
            response = self.client.get("/api/astronomy/gaia?limit=1&tile=71")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"][0]["id"], "Gaia DR3 1")

    def test_empty_simbad_query_rejected(self):
        response = self.client.get("/api/astronomy/simbad")
        self.assertEqual(response.status_code, 400)

    def test_jpl_requires_query(self):
        response = self.client.get("/api/astronomy/jpl")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
