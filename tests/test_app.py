import json
import os
import unittest
from unittest.mock import patch

from app import app


class MoonSimulatorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def observation(self, **overrides):
        payload = {
            "lat": 37.5665,
            "lon": 126.9780,
            "elevation": 38,
            "datetime": "2026-07-13T21:00",
            "timezone": "Asia/Seoul",
        }
        payload.update(overrides)
        return self.client.post("/api/moon-position", json=payload)

    def test_health_and_korean_dashboard(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["ephemeris"], "de440.bsp")

        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("달빛 나침반".encode(), page.data)
        self.assertIn("이 위치에서 달 보기".encode(), page.data)
        self.assertIn("달 찾기".encode(), page.data)
        self.assertIn("거리뷰 보기".encode(), page.data)
        self.assertIn("내 위치".encode(), page.data)
        self.assertIn("즐겨찾기".encode(), page.data)
        self.assertIn(b'id="mapOverlay"', page.data)
        self.assertIn(b'id="mapLocationButton"', page.data)
        self.assertIn(b'id="dateInput"', page.data)
        self.assertIn(b'id="timeInput"', page.data)
        self.assertNotIn(b"datetime-local", page.data)
        self.assertIn(b'id="favoriteList"', page.data)
        self.assertIn("보이면 노란 달".encode(), page.data)
        self.assertIn(b'id="appConfig"', page.data)
        self.assertIn(b'id="photoStreetView"', page.data)
        self.assertNotIn(b"KartaView", page.data)
        self.assertNotIn("현재 위치 찾기".encode(), page.data)
        self.assertNotIn("내 위치로 바로 계산".encode(), page.data)
        self.assertNotIn("거리뷰에서 달 보기".encode(), page.data)
        self.assertNotIn("거리뷰 다시 불러오기".encode(), page.data)
        self.assertNotIn("실제 크기 1배".encode(), page.data)
        self.assertNotIn("보기 쉽게 6배".encode(), page.data)
        self.assertNotIn(b"photoMoonScaleRange", page.data)
        self.assertNotIn("달 크기는 찾기 쉽게 확대했습니다".encode(), page.data)

    def test_config_hides_naver_secret_and_exposes_client_id(self):
        with patch.dict(
            os.environ,
            {
                "NAVER_MAPS_CLIENT_ID": "public-client-id",
                "NAVER_MAPS_CLIENT_SECRET": "super-secret-key",
            },
            clear=False,
        ):
            config = self.client.get("/api/config")
            health = self.client.get("/api/health")
            page = self.client.get("/")

        self.assertEqual(config.status_code, 200)
        payload = config.get_json()
        self.assertEqual(payload["naver_maps"], {
            "enabled": True,
            "client_id": "public-client-id",
        })
        self.assertTrue(health.get_json()["naver_maps"])
        self.assertIn(b"public-client-id", page.data)
        self.assertNotIn(b"super-secret-key", config.data)
        self.assertNotIn(b"super-secret-key", page.data)
        self.assertNotIn("secret", json.dumps(payload))

    def test_current_position_and_daily_trajectory(self):
        response = self.observation()
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertEqual(data["observer"]["timezone"], "Asia/Seoul")
        self.assertEqual(data["position"]["time"], "2026-07-13T21:00+09:00")
        self.assertGreaterEqual(data["position"]["azimuth_deg"], 0)
        self.assertLess(data["position"]["azimuth_deg"], 360)
        self.assertIn("altitude_geometric_deg", data["position"])
        self.assertIn("altitude_apparent_deg", data["position"])
        self.assertEqual(len(data["trajectory"]), 97)
        self.assertEqual(data["trajectory"][0]["minute_of_day"], 0)
        self.assertEqual(data["trajectory"][-1]["minute_of_day"], 1440)

    def test_lunar_events_use_moon_specific_horizon(self):
        response = self.observation()
        data = response.get_json()
        self.assertEqual(data["events"]["rise"]["time"][11:16], "03:21")
        self.assertEqual(data["events"]["set"]["time"][11:16], "19:12")

    def test_invalid_inputs_return_korean_client_errors(self):
        invalid_latitude = self.observation(lat=91)
        self.assertEqual(invalid_latitude.status_code, 400)
        self.assertIn("위도", invalid_latitude.get_json()["error"])

        invalid_timezone = self.observation(timezone="Not/A_Timezone")
        self.assertEqual(invalid_timezone.status_code, 400)
        self.assertIn("시간대", invalid_timezone.get_json()["error"])

        invalid_date = self.observation(datetime="2700-01-01T00:00")
        self.assertEqual(invalid_date.status_code, 400)
        self.assertIn("천체력", invalid_date.get_json()["error"])

    def test_legacy_route_accepts_date(self):
        response = self.client.post("/calculate", json={
            "lat": 35.1796,
            "lon": 129.0756,
            "date": "2026-07-13",
            "timezone": "Asia/Seoul",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["requested_time"], "2026-07-13T12:00+09:00")

    def test_observer_timezone_is_not_fixed_to_korea(self):
        response = self.observation(
            lat=40.7128,
            lon=-74.0060,
            datetime="2026-07-13T21:00",
            timezone="America/New_York",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["observer"]["timezone"], "America/New_York")
        self.assertTrue(data["requested_time"].endswith("-04:00"))


if __name__ == "__main__":
    unittest.main()
