from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request
from skyfield import almanac
from skyfield.api import load, load_file, wgs84


BASE_DIR = Path(__file__).resolve().parent
EPHEMERIS_PATH = BASE_DIR / "de440.bsp"

if not EPHEMERIS_PATH.exists():
    raise RuntimeError(f"천체력 파일을 찾을 수 없습니다: {EPHEMERIS_PATH}")

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def _static_version() -> str:
    newest = 0
    for name in ("app.js", "photo-composer.js", "naver-maps.js", "styles.css"):
        path = BASE_DIR / "static" / name
        if path.is_file():
            newest = max(newest, int(path.stat().st_mtime))
    return str(newest or 1)


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / ".env")


def _env_value(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _naver_maps_client_id() -> str:
    return _env_value("NAVER_MAPS_CLIENT_ID", "NCP_APIGW_API_KEY_ID", "X_NCP_APIGW_API_KEY_ID")


def _public_app_config() -> dict:
    client_id = _naver_maps_client_id()
    return {
        "naver_maps": {
            "enabled": bool(client_id),
            "client_id": client_id or None,
        }
    }


# 네트워크 연결 없이도 같은 계산 결과가 나오도록 프로젝트 안의 천체력을 사용합니다.
planets = load_file(str(EPHEMERIS_PATH))
earth = planets["earth"]
moon = planets["moon"]
sun = planets["sun"]
ts = load.timescale(builtin=True)


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def direction_name(azimuth: float) -> str:
    """0~360도 방위각을 16방위 한국어 이름으로 바꿉니다."""
    names = (
        "북", "북북동", "북동", "동북동",
        "동", "동남동", "남동", "남남동",
        "남", "남남서", "남서", "서남서",
        "서", "서북서", "북서", "북북서",
    )
    return names[int((azimuth % 360 + 11.25) // 22.5) % 16]


def moon_phase_name(angle: float) -> tuple[str, str]:
    """달의 위상각을 한국어 이름과 대표 문자로 바꿉니다."""
    angle %= 360
    if angle < 11.25 or angle >= 348.75:
        return "삭", "🌑"
    if angle < 78.75:
        return "초승달", "🌒"
    if angle < 101.25:
        return "상현달", "🌓"
    if angle < 168.75:
        return "차오르는 달", "🌔"
    if angle < 191.25:
        return "보름달", "🌕"
    if angle < 258.75:
        return "기우는 달", "🌖"
    if angle < 281.25:
        return "하현달", "🌗"
    return "그믐달", "🌘"


def destination_point(lat: float, lon: float, bearing: float, distance_km: float = 5.0) -> tuple[float, float]:
    """지도 방향선을 위한 목적지 좌표를 계산합니다."""
    radius_km = 6371.0088
    angular_distance = distance_km / radius_km
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing)

    dest_lat = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance)
        + math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    dest_lon = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance) - math.sin(lat_rad) * math.sin(dest_lat),
    )
    normalized_lon = (math.degrees(dest_lon) + 540) % 360 - 180
    return math.degrees(dest_lat), normalized_lon


def parse_local_datetime(raw_value: str, timezone_name: str) -> tuple[dt.datetime, ZoneInfo]:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("지원하지 않는 시간대입니다.") from exc

    try:
        parsed = dt.datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("날짜와 시간 형식이 올바르지 않습니다.") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    else:
        parsed = parsed.astimezone(timezone)
    return parsed, timezone


def validate_observer(data: dict) -> tuple[float, float, float]:
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
        elevation = float(data.get("elevation", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("위도, 경도, 고도를 숫자로 입력해 주세요.") from exc

    if not all(math.isfinite(value) for value in (lat, lon, elevation)):
        raise ValueError("위도, 경도, 고도에는 유한한 숫자를 입력해 주세요.")
    if not -90 <= lat <= 90:
        raise ValueError("위도는 -90도에서 90도 사이여야 합니다.")
    if not -180 <= lon <= 180:
        raise ValueError("경도는 -180도에서 180도 사이여야 합니다.")
    if not -500 <= elevation <= 10000:
        raise ValueError("고도는 -500m에서 10,000m 사이여야 합니다.")
    return lat, lon, elevation


def position_payload(observer, skyfield_time, local_time: dt.datetime, lat: float, lon: float) -> dict:
    apparent = observer.at(skyfield_time).observe(moon).apparent()
    geometric_altitude, azimuth, distance = apparent.altaz()
    apparent_altitude, _, _ = apparent.altaz(temperature_C="standard")
    geometric_altitude_deg = float(geometric_altitude.degrees)
    apparent_altitude_deg = float(apparent_altitude.degrees)
    azimuth_deg = float(azimuth.degrees) % 360
    angular_radius_deg = math.degrees(math.asin(min(1.0, 1737.4 / float(distance.km))))
    dest_lat, dest_lon = destination_point(lat, lon, azimuth_deg)
    return {
        "time": local_time.isoformat(timespec="minutes"),
        "altitude_deg": _round(apparent_altitude_deg),
        "altitude_geometric_deg": _round(geometric_altitude_deg),
        "altitude_apparent_deg": _round(apparent_altitude_deg),
        "azimuth_deg": _round(azimuth_deg),
        "distance_km": _round(distance.km, 0),
        "angular_diameter_deg": _round(angular_radius_deg * 2, 3),
        "direction": direction_name(azimuth_deg),
        "above_horizon": apparent_altitude_deg + angular_radius_deg > 0,
        "map_endpoint": {"lat": _round(dest_lat, 6), "lon": _round(dest_lon, 6)},
    }


def find_daily_events(observer, day_start: dt.datetime, day_end: dt.datetime, lat: float, lon: float) -> dict:
    """달의 거리별 시반지름과 표준 굴절을 반영한 월출·월몰을 찾습니다."""
    start_time = ts.from_datetime(day_start)
    end_time = ts.from_datetime(day_end)
    rise_times, rise_occurs = almanac.find_risings(observer, moon, start_time, end_time)
    set_times, set_occurs = almanac.find_settings(observer, moon, start_time, end_time)

    def first_real_event(event_times, event_occurs):
        for event_time, event_is_real in zip(event_times, event_occurs):
            if bool(event_is_real):
                local_time = event_time.astimezone(day_start.tzinfo)
                return position_payload(observer, event_time, local_time, lat, lon)
        return None

    return {
        "rise": first_real_event(rise_times, rise_occurs),
        "set": first_real_event(set_times, set_occurs),
    }


def build_daily_trajectory(observer, day_start: dt.datetime, day_end: dt.datetime) -> list[dict]:
    step = dt.timedelta(minutes=15)
    local_times: list[dt.datetime] = []
    cursor = day_start
    while cursor <= day_end:
        local_times.append(cursor)
        cursor += step

    skyfield_times = ts.from_datetimes(local_times)
    apparent = observer.at(skyfield_times).observe(moon).apparent()
    geometric_altitudes, azimuths, distances = apparent.altaz()
    apparent_altitudes, _, _ = apparent.altaz(temperature_C="standard")
    sun_altitudes, sun_azimuths, _ = observer.at(skyfield_times).observe(sun).apparent().altaz()

    trajectory = []
    for index, local_time in enumerate(local_times):
        altitude = float(apparent_altitudes.degrees[index])
        geometric_altitude = float(geometric_altitudes.degrees[index])
        azimuth = float(azimuths.degrees[index]) % 360
        angular_radius = math.degrees(math.asin(min(1.0, 1737.4 / float(distances.km[index]))))
        trajectory.append(
            {
                "time": local_time.isoformat(timespec="minutes"),
                "minute_of_day": int((local_time - day_start).total_seconds() // 60),
                "altitude_deg": _round(altitude),
                "altitude_geometric_deg": _round(geometric_altitude),
                "azimuth_deg": _round(azimuth),
                "distance_km": _round(distances.km[index], 0),
                "sun_altitude_deg": _round(sun_altitudes.degrees[index]),
                "sun_azimuth_deg": _round(float(sun_azimuths.degrees[index]) % 360),
                "direction": direction_name(azimuth),
                "above_horizon": altitude + angular_radius > 0,
            }
        )
    return trajectory


def build_recommendation(position: dict, best_position: dict | None) -> str:
    if position["above_horizon"]:
        prefix = f"선택한 시각에는 {position['direction']}쪽, 지평선 위 {position['altitude_deg']:.1f}°에서 달을 찾을 수 있습니다."
    else:
        prefix = f"선택한 시각에는 달이 {position['direction']}쪽 지평선 아래 {abs(position['altitude_deg']):.1f}°에 있어 보이지 않습니다."

    if best_position and best_position["altitude_deg"] > 0:
        best_time = dt.datetime.fromisoformat(best_position["time"]).strftime("%H:%M")
        return f"{prefix} 오늘 가장 높이 오르는 시각은 {best_time} 무렵이며 고도는 약 {best_position['altitude_deg']:.1f}°입니다."
    return f"{prefix} 선택한 날짜에는 달이 지평선 위로 올라오는 구간이 없습니다."


def calculate_observation(data: dict) -> dict:
    lat, lon, elevation = validate_observer(data)
    timezone_name = str(data.get("timezone") or "Asia/Seoul")
    raw_datetime = data.get("datetime")
    if not raw_datetime and data.get("date"):
        raw_datetime = f"{data['date']}T12:00"
    if not raw_datetime:
        raise ValueError("관측 날짜와 시간을 입력해 주세요.")

    local_datetime, timezone = parse_local_datetime(str(raw_datetime), timezone_name)
    if not 1550 <= local_datetime.year <= 2649:
        raise ValueError("날짜는 천체력이 지원하는 1550년부터 2649년 사이여야 합니다.")
    topos = wgs84.latlon(lat, lon, elevation_m=elevation)
    observer = earth + topos
    observed_time = ts.from_datetime(local_datetime)

    day_start = dt.datetime.combine(local_datetime.date(), dt.time.min, tzinfo=timezone)
    day_end = day_start + dt.timedelta(days=1)
    position = position_payload(observer, observed_time, local_datetime, lat, lon)
    trajectory = build_daily_trajectory(observer, day_start, day_end)
    events = find_daily_events(observer, day_start, day_end, lat, lon)

    sun_altitude, sun_azimuth, _ = observer.at(observed_time).observe(sun).apparent().altaz()

    phase_angle = float(almanac.moon_phase(planets, observed_time).degrees) % 360
    illumination = float(almanac.fraction_illuminated(planets, "moon", observed_time)) * 100
    phase_name, phase_emoji = moon_phase_name(phase_angle)
    best_position = max(trajectory, key=lambda item: item["altitude_deg"], default=None)

    return {
        "observer": {
            "lat": _round(lat, 6),
            "lon": _round(lon, 6),
            "elevation_m": _round(elevation, 0),
            "timezone": timezone_name,
        },
        "requested_time": local_datetime.isoformat(timespec="minutes"),
        "position": position,
        "sun_position": {
            "altitude_deg": _round(sun_altitude.degrees),
            "azimuth_deg": _round(float(sun_azimuth.degrees) % 360),
        },
        "phase": {
            "name": phase_name,
            "emoji": phase_emoji,
            "angle_deg": _round(phase_angle),
            "illumination_percent": _round(illumination, 1),
        },
        "events": events,
        "trajectory": trajectory,
        "best_position": best_position,
        "recommendation": build_recommendation(position, best_position),
        "notice": "표준 대기 굴절과 달의 겉보기 크기를 반영한 평탄한 천문학적 지평선 기준입니다. 건물, 산, 구름, 주변 빛은 반영하지 않습니다.",
    }


@app.after_request
def disable_static_cache(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/")
def index():
    return render_template(
        "index.html",
        app_config=_public_app_config(),
        static_version=_static_version(),
    )


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "ephemeris": EPHEMERIS_PATH.name,
        "naver_maps": _public_app_config()["naver_maps"]["enabled"],
    })


@app.get("/api/config")
def public_config():
    return jsonify(_public_app_config())


@app.post("/api/moon-position")
@app.post("/calculate")
def moon_position():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(calculate_observation(data))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("달 위치 계산 중 예상하지 못한 오류가 발생했습니다.")
        return jsonify({"error": "달 위치를 계산하지 못했습니다. 잠시 후 다시 시도해 주세요."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
