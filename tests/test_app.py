import datetime as dt
import json
import os
import unittest
from pathlib import Path
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
        self.assertIn("달 방향".encode(), page.data)
        self.assertNotIn("이 방향으로 고개를 들면 됩니다".encode(), page.data)
        self.assertIn(b'id="appConfig"', page.data)
        self.assertIn(b'id="photoStreetView"', page.data)
        self.assertIn("1시간씩 흐르게".encode(), page.data)
        self.assertNotIn(b"photoMoonHiddenWarning", page.data)
        self.assertNotIn(b"KartaView", page.data)
        self.assertNotIn("현재 위치 찾기".encode(), page.data)
        self.assertNotIn("내 위치로 바로 계산".encode(), page.data)
        self.assertNotIn("거리뷰에서 달 보기".encode(), page.data)
        self.assertNotIn("거리뷰 다시 불러오기".encode(), page.data)
        self.assertNotIn("실제 크기 1배".encode(), page.data)
        self.assertNotIn("보기 쉽게 6배".encode(), page.data)
        self.assertNotIn(b"photoMoonScaleRange", page.data)
        self.assertNotIn("달 크기는 찾기 쉽게 확대했습니다".encode(), page.data)
        self.assertIn("밤 장면 만들기".encode(), page.data)
        self.assertIn("이미지 저장".encode(), page.data)
        self.assertIn(b'id="photoEveningButton"', page.data)
        self.assertIn(b'id="photoEveningSaveButton"', page.data)
        self.assertIn(b'id="photoEveningProgress"', page.data)
        self.assertIn("휴대폰과 PC".encode(), page.data)
        self.assertNotIn(b'id="photoScreenCaptureInput"', page.data)
        self.assertNotIn("화면 공유 창".encode(), page.data)
        self.assertIn(b"html2canvas", page.data)

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
        self.assertIn("evening_scene", payload)
        self.assertNotIn("GEMINI", json.dumps(payload).upper())

    def test_evening_scene_uses_mobile_browser_capture(self):
        source = (Path(__file__).resolve().parents[1] / "static" / "photo-composer.js").read_text(encoding="utf-8")

        self.assertIn("window.html2canvas(view", source)
        self.assertIn("captureVisibleStreetView", source)
        self.assertIn("renderStreetViewPanorama", source)
        self.assertIn("panoramaHeadingOffset", source)
        self.assertIn("this.drawMoonGuide(captured, moon)", source)
        self.assertIn("const diameter = this.moonDisplayDiameter(projection)", source)
        self.assertIn("this.dom.eveningImage.src = generatedSource", source)
        self.assertIn("screenshot.moon", source)
        self.assertNotIn("compositeMoon", source)
        self.assertNotIn("getDisplayMedia", source)
        self.assertNotIn("photoScreenCaptureInput", source)
        self.assertNotIn('/api/screen-capture', source)
        self.assertNotIn("createScreenCaptureMarker", source)
        self.assertNotIn("captureVisibleScreen", source)

    def test_server_screen_capture_endpoint_was_removed(self):
        response = self.client.post(
            "/api/screen-capture",
            environ_base={"REMOTE_ADDR": "192.168.0.25"},
        )
        self.assertEqual(response.status_code, 404)

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
        path = data["hourly_path"]
        self.assertGreater(len(path), 2)
        self.assertIn("label", path[0])
        self.assertIn("map_endpoint", path[0])
        rise_time = dt.datetime.fromisoformat(data["events"]["rise"]["time"])
        start_time = dt.datetime.fromisoformat(path[0]["time"])
        self.assertAlmostEqual((rise_time - start_time).total_seconds() / 3600, 1, delta=0.05)
        gaps = [
            (dt.datetime.fromisoformat(later["time"]) - dt.datetime.fromisoformat(earlier["time"])).total_seconds() / 3600
            for earlier, later in zip(path, path[1:])
        ]
        self.assertTrue(all(0.99 <= gap <= 1.01 for gap in gaps))

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

    def _jpeg_stub(self):
        return __import__("base64").b64encode(b"\xff\xd8\xff" + b"x" * 1200).decode()

    def test_evening_scene_requires_key_and_screenshot(self):
        with patch("app.evening_scene_enabled", return_value=False):
            blocked = self.client.post("/api/evening-scene", json={
                "lat": 37.5665,
                "lon": 126.9780,
                "datetime": "2026-07-13T21:00",
                "timezone": "Asia/Seoul",
                "image": self._jpeg_stub(),
            })
        self.assertEqual(blocked.status_code, 503)
        self.assertIn("GEMINI_API_KEY", blocked.get_json()["error"])

        with patch("app.evening_scene_enabled", return_value=True):
            missing = self.client.post("/api/evening-scene", json={
                "lat": 37.5665,
                "lon": 126.9780,
                "datetime": "2026-07-13T21:00",
                "timezone": "Asia/Seoul",
            })
        self.assertEqual(missing.status_code, 400)
        self.assertIn("화면", missing.get_json()["error"])

    def test_evening_scene_uses_visible_screenshot(self):
        with patch("app.evening_scene_enabled", return_value=True), patch(
            "app.generate_evening_scene",
            return_value={
                "image": "ZmFrZQ==",
                "mime_type": "image/jpeg",
                "notice": "지금 보이는 화면을 바탕으로 만든 예상 밤 장면입니다.",
            },
        ) as generate:
            response = self.client.post(
                "/api/evening-scene",
                json={
                    "lat": 37.5665,
                    "lon": 126.9780,
                    "datetime": "2026-07-13T21:00",
                    "timezone": "Asia/Seoul",
                    "place_name": "서울시청",
                    "image": self._jpeg_stub(),
                    "moon_x_percent": 48.6,
                    "moon_y_percent": 27.4,
                    "moon_diameter_px": 12,
                    "moon_diameter_percent": 2.6,
                },
                environ_base={"REMOTE_ADDR": "192.168.0.25"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["image"], "ZmFrZQ==")
        self.assertEqual(payload["mime_type"], "image/jpeg")
        self.assertIn("밤 장면", payload["notice"])
        generate.assert_called_once()
        extras = generate.call_args[0][2]
        self.assertEqual(extras["moon_x_percent"], 48.6)
        self.assertEqual(extras["moon_y_percent"], 27.4)
        self.assertEqual(extras["moon_diameter_px"], 12)
        self.assertEqual(extras["moon_diameter_percent"], 2.6)

    def test_evening_prompt_forbids_new_buildings(self):
        from evening_scene import DEFAULT_MODEL, build_evening_prompt, closest_aspect_ratio

        self.assertEqual(DEFAULT_MODEL, "gemini-3.1-flash-image")
        self.assertEqual(closest_aspect_ratio(1600, 900), "16:9")
        self.assertEqual(closest_aspect_ratio(1200, 900), "4:3")
        self.assertEqual(closest_aspect_ratio(800, 800), "1:1")

        prompt = build_evening_prompt({
            "position": {
                "altitude_deg": 32,
                "azimuth_deg": 140,
                "direction": "남동",
                "above_horizon": True,
                "angular_diameter_deg": 0.52,
            },
            "phase": {"name": "보름달", "illumination_percent": 99, "angle_deg": 180},
            "sun_position": {"altitude_deg": -18},
        }, {
            "moon_in_view": True,
            "moon_x_percent": 62.5,
            "moon_y_percent": 18.0,
            "moon_diameter_percent": 1.2,
            "view_fov_deg": 70,
        })
        self.assertIn("high-resolution, photorealistic nighttime transformation", prompt)
        self.assertIn("Preserve the exact camera angle, perspective, building layout", prompt)
        self.assertIn("visible guide moon", prompt)
        self.assertIn("Replace that guide with an authentic, highly detailed astronomical moon", prompt)
        self.assertIn("62.5% from the left and 18.0% from the top", prompt)
        self.assertIn("roughly 1.2% of the image width", prompt)
        self.assertIn("Seamlessly integrate the moon into the night sky", prompt)
        self.assertIn("warm ivory to pale straw-yellow at 32.0° altitude", prompt)
        self.assertIn("cool silver-blue moonlight sheen", prompt)
        self.assertIn("deep velvety midnight blue and dark indigo night sky", prompt)
        self.assertIn("natural warm city horizon glow", prompt)
        self.assertIn("balanced, high-quality night photograph", prompt)
        self.assertIn("DSLR-quality night photograph", prompt)

        low_moon_prompt = build_evening_prompt({
            "position": {"altitude_deg": 5, "azimuth_deg": 95, "above_horizon": True},
            "phase": {"name": "보름달", "illumination_percent": 99, "angle_deg": 180},
            "sun_position": {"altitude_deg": -20},
        }, {
            "moon_in_view": True,
            "moon_x_percent": 70,
            "moon_y_percent": 40,
            "moon_diameter_percent": 1.5,
        })
        self.assertIn("warm amber-gold at 5.0° altitude", low_moon_prompt)
        self.assertIn("warm atmospheric haze around the moon", low_moon_prompt)

    def test_evening_scene_uses_nano_banana_2(self):
        from evening_scene import generate_evening_scene

        with patch("evening_scene.gemini_api_key", return_value="test-key"), patch(
            "evening_scene._post_interaction",
            return_value={"output_image": {"data": "ZmFrZQ==", "mime_type": "image/jpeg"}},
        ) as post:
            generate_evening_scene(
                {
                    "position": {"altitude_deg": 32, "azimuth_deg": 140, "above_horizon": True},
                    "phase": {"name": "보름달", "illumination_percent": 99},
                },
                {"image": self._jpeg_stub()},
                {
                    "image_width": 1600,
                    "image_height": 900,
                    "moon_in_view": True,
                    "moon_x_percent": 50,
                    "moon_y_percent": 20,
                    "moon_diameter_percent": 0.8,
                },
            )

        body = post.call_args[0][1]
        self.assertEqual(body["model"], "gemini-3.1-flash-image")
        self.assertEqual(body["input"][0]["type"], "image")
        self.assertEqual(body["input"][1]["type"], "text")
        self.assertEqual(body["response_format"]["aspect_ratio"], "16:9")
        self.assertEqual(body["generation_config"]["thinking_level"], "high")
        prompt = body["input"][1]["text"]
        self.assertIn("high-resolution, photorealistic nighttime transformation", prompt)
        self.assertIn("50.0% from the left and 20.0% from the top", prompt)
if __name__ == "__main__":
    unittest.main()
