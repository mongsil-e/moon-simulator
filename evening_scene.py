from __future__ import annotations

import base64
import json
import math
import os
import re
import urllib.error
import urllib.request


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Nano Banana 2. Legacy Nano Banana is gemini-2.5-flash-image.
DEFAULT_MODEL = "gemini-3.1-flash-image"
FALLBACK_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
)
THINKING_MODELS = {"gemini-3.1-flash-image"}
SUPPORTED_ASPECT_RATIOS = (
    (1, 1),
    (3, 2),
    (2, 3),
    (3, 4),
    (4, 3),
    (4, 5),
    (5, 4),
    (9, 16),
    (16, 9),
    (21, 9),
    (9, 21),
    (1, 4),
    (4, 1),
    (1, 8),
    (8, 1),
)
PHASE_ENGLISH = {
    "삭": "new moon",
    "초승달": "waxing crescent",
    "상현달": "first quarter",
    "차오르는 달": "waxing gibbous",
    "보름달": "full moon",
    "망": "full moon",
    "기우는 달": "waning gibbous",
    "하현달": "last quarter",
    "그믐달": "waning crescent",
}
MAX_IMAGE_BYTES = 4 * 1024 * 1024
DATA_URL_RE = re.compile(r"^data:(image/(?:jpeg|jpg|png|webp));base64,(.+)$", re.IGNORECASE)


def gemini_api_key() -> str:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def evening_scene_enabled() -> bool:
    return bool(gemini_api_key())


def parse_screenshot(payload: dict) -> tuple[str, str]:
    raw = str(payload.get("image") or payload.get("screenshot") or "").strip()
    if not raw:
        raise ValueError("지금 보이는 화면을 담지 못했습니다. 거리뷰가 열린 뒤 다시 눌러 주세요.")

    mime_type = "image/jpeg"
    data = raw
    match = DATA_URL_RE.match(raw.replace("\n", ""))
    if match:
        mime_type = match.group(1).lower().replace("image/jpg", "image/jpeg")
        data = match.group(2)

    data = re.sub(r"\s+", "", data)
    try:
        decoded = base64.b64decode(data, validate=True)
    except Exception as exc:
        raise ValueError("화면 캡처 형식이 올바르지 않습니다.") from exc

    if len(decoded) < 800:
        raise ValueError("화면 캡처가 비어 있습니다. 거리뷰가 완전히 뜬 뒤 다시 시도해 주세요.")
    if len(decoded) > MAX_IMAGE_BYTES:
        raise ValueError("화면 캡처가 너무 큽니다. 창을 조금 줄인 뒤 다시 시도해 주세요.")

    return mime_type, data


def closest_aspect_ratio(width: float | int | None, height: float | int | None) -> str:
    try:
        safe_width = float(width or 0)
        safe_height = float(height or 0)
    except (TypeError, ValueError):
        return "16:9"
    if safe_width <= 0 or safe_height <= 0:
        return "16:9"
    target = safe_width / safe_height
    best_w, best_h = min(
        SUPPORTED_ASPECT_RATIOS,
        key=lambda pair: abs((pair[0] / pair[1]) - target),
    )
    return f"{best_w}:{best_h}"


def _jpeg_dimensions(b64_data: str) -> tuple[int, int] | None:
    try:
        raw = base64.b64decode(b64_data, validate=False)
    except Exception:
        return None
    if raw[:2] != b"\xff\xd8":
        return None
    index = 2
    length = len(raw)
    while index + 9 < length:
        if raw[index] != 0xFF:
            index += 1
            continue
        marker = raw[index + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height = int.from_bytes(raw[index + 5:index + 7], "big")
            width = int.from_bytes(raw[index + 7:index + 9], "big")
            if width > 0 and height > 0:
                return width, height
            return None
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        size = int.from_bytes(raw[index + 2:index + 4], "big")
        if size < 2:
            return None
        index += 2 + size
    return None


def _finite_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _percent(value) -> str | None:
    number = _finite_number(value)
    if number is None:
        return None
    return f"{max(0.0, min(100.0, number)):.1f}"


def _english_phase(name: str) -> str:
    raw = str(name or "").strip()
    return PHASE_ENGLISH.get(raw, "moon")


def _sky_physics(observation: dict) -> str:
    sun_alt = _finite_number((observation.get("sun_position") or {}).get("altitude_deg"))
    illumination = _finite_number((observation.get("phase") or {}).get("illumination_percent")) or 0
    moon_alt = _finite_number((observation.get("position") or {}).get("altitude_deg"))
    moon_up = bool((observation.get("position") or {}).get("above_horizon")) and (moon_alt or 0) > 0

    if sun_alt is None or sun_alt <= -18:
        band = (
            "astronomical night: near-black to very dark navy sky, a little brighter and greyer "
            "toward the horizon from airglow and urban light pollution"
        )
    elif sun_alt <= -12:
        band = (
            "astronomical twilight: very dark blue-black sky, only a faint residual glow on the "
            "sun's azimuth, no sunset orange"
        )
    elif sun_alt <= -6:
        band = (
            "nautical twilight: deep blue night with a weak horizon band, not dusk, not blue hour"
        )
    else:
        band = (
            "civil twilight: dark blue twilight, not full night and not a sunset. No orange-pink sky"
        )

    if moon_up and illumination >= 90:
        wash = (
            "Full moonlight physically washes the sky to a pale gray-blue; the Milky Way is invisible; "
            "only the brightest stars remain."
        )
    elif moon_up and illumination >= 50:
        wash = "Gibbous moonlight mildly brightens the sky; a handful of stars; not pitch black."
    elif moon_up and illumination >= 15:
        wash = (
            "Crescent moonlight is weak. The sky stays darker with more stars, but this is a city street "
            "so keep a low orange-brown light-pollution glow near the horizon."
        )
    else:
        wash = (
            "Little or no moonlight. Dark urban night: orange-brown light pollution near the horizon, "
            "a few stars higher up, no fantasy nebula."
        )
    return (
        f"Follow atmospheric physics for {band}. {wash} "
        "Sky luminance must increase slightly toward the horizon and stay darker at the zenith. "
        "No purple CGI sky, no painted galaxy, no fake volumetric fog, no sunset."
    )


def _terminator_line(phase: dict) -> str:
    name = _english_phase(phase.get("name"))
    angle = _finite_number(phase.get("angle_deg"))
    illumination = _finite_number(phase.get("illumination_percent"))
    lit = (
        f"{illumination:.0f}% of the disc is sunlit"
        if illumination is not None
        else "the sunlit fraction matches this phase"
    )
    if angle is None:
        side = "Draw the correct terminator for this phase as seen from the northern hemisphere."
    elif angle < 11 or angle >= 349:
        side = "This is essentially a new moon: do not draw a bright disc."
    elif angle < 180:
        side = "Northern hemisphere: the RIGHT side of the disc is sunlit (waxing)."
    elif angle <= 191:
        side = "Full moon: the whole earth-facing disc is sunlit, with no cartoon outline."
    else:
        side = "Northern hemisphere: the LEFT side of the disc is sunlit (waning)."
    return (
        f"It is a {name}; {lit}. {side} "
        "The terminator is a soft physical shadow on a sphere, not a flat sticker or Pac-Man shape. "
        "Show real lunar maria and craters. If the dark part is visible, use faint earthshine, not a black cutout."
    )


def _moon_appearance(altitude: float | None) -> str:
    if altitude is None:
        return "Cool white-gray lunar albedo, like a real telephoto moon, not neon yellow."
    if altitude < 8:
        return (
            f"Altitude {altitude:.1f}°: strong atmospheric scattering makes it dimmer and warm yellow-orange, "
            "with only a mild horizon haze. No giant bloom."
        )
    if altitude < 20:
        return (
            f"Altitude {altitude:.1f}°: pale gold-white from remaining atmosphere. Tiny natural halo at most."
        )
    return (
        f"Altitude {altitude:.1f}°: cool white-gray lunar disc, sharp limb against the sky, "
        "no large glow, no lens flare, no 3D sphere floating in front of the camera."
    )


def _moon_size_line(observation: dict, extras: dict) -> str:
    angular = _finite_number((observation.get("position") or {}).get("angular_diameter_deg")) or 0.5
    fov = _finite_number(extras.get("view_fov_deg")) or 70.0
    width_pct = max(0.3, min(2.5, (angular / max(fov, 1.0)) * 100.0))
    return (
        f"Physical apparent diameter is {angular:.2f}° in a {fov:.0f}° wide street-view field of view, "
        f"so the moon disc must be about {width_pct:.1f}% of the image width — a small distant object, "
        "exactly like a real night photograph from a phone or street camera. "
        "NEVER a large decorative moon, never an oversized CGI orb."
    )


def _moon_edit_instruction(observation: dict, extras: dict | None) -> str:
    extras = extras or {}
    position = observation.get("position") or {}
    phase = observation.get("phase") or {}
    above = bool(position.get("above_horizon"))
    in_view = extras.get("moon_in_view")
    if in_view is None:
        in_view = above
    if not above or not in_view:
        return (
            "The moon is not in this view. Do not add a moon, glowing orb, planet, or extra sky light."
        )

    altitude = _finite_number(position.get("altitude_deg"))
    left = _percent(extras.get("moon_x_percent"))
    top = _percent(extras.get("moon_y_percent"))
    location = (
        f"Place its center at {left}% from the left and {top}% from the top of this crop. "
        if left and top
        else "Place it in the sky at the calculated moon position for this camera. "
    )
    return (
        "There is no moon in the input photo. Add exactly one physically real moon. "
        f"{location}"
        f"{_moon_size_line(observation, extras)} "
        f"{_terminator_line(phase)} "
        f"{_moon_appearance(altitude)} "
        "Do not add a second moon. If that coordinate sits on a building, keep the building and put the moon "
        "in the nearest visible sky at the same horizontal position."
    )


def _moonlight_line(observation: dict, extras: dict | None) -> str:
    extras = extras or {}
    position = observation.get("position") or {}
    phase = observation.get("phase") or {}
    if not position.get("above_horizon"):
        return (
            "No moonlight. Darken existing building and pavement pixels as a night color grade only. "
            "Do not invent new streetlights or window lights."
        )
    illumination = _finite_number(phase.get("illumination_percent")) or 0
    strength = (
        "strong cool-white moonlight"
        if illumination >= 85
        else "moderate cool moonlight"
        if illumination >= 40
        else "weak silvery moonlight"
    )
    left = _percent(extras.get("moon_x_percent"))
    direction = (
        f"from the moon at {left}% from the left of the frame"
        if left
        else "from the moon's position in the sky"
    )
    return (
        f"Existing surfaces may receive {strength} {direction}. "
        "Shadows of the existing buildings and trees fall away from the moon. "
        "Do not redraw architecture. Do not add new streetlights, new signs, or extra window lights."
    )


def build_evening_prompt(observation: dict, extras: dict | None = None) -> str:
    return (
        "고화질로 생성하세요. 단, 구도와 달의 위치는 절대 변경하지 마세요. "
        "밤하늘만 사실적으로 구현하고, 달은 스티커나 아이콘이 아닌 실제 천체 사진처럼 보이도록 하세요. "
        "실제로 밤이 된 현장을 촬영한 것처럼 전체 장면에 물리적으로 자연스럽게 표현하세요. "
        "실제 밤하늘을 사진 찍은 것처럼 달의 크기가 너무 커지지 않도록 하세요. "
        "달의 위치를 변경하지 말고 그대로 유지하세요. "
        "나머지는 원본 그대로 유지하세요. "
        "새로운 건물, 사람, 차, 구조물 등을 생성하지 마세요. "
        "빛, 그림자, 반사 등 물리 법칙을 따르세요."
    )


def _extract_image(payload: dict) -> tuple[str, str]:
    image = payload.get("output_image") or {}
    if isinstance(image, dict) and image.get("data"):
        mime = str(image.get("mime_type") or "image/jpeg")
        return mime, str(image["data"])

    for step in payload.get("steps") or []:
        blocks = step.get("content") or step.get("summary") or []
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"image", "image_data"} and block.get("data"):
                mime = str(block.get("mime_type") or "image/jpeg")
                return mime, str(block["data"])
    raise RuntimeError("이미지 모델이 장면을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _friendly_api_error(status: int, detail: str) -> str:
    text = (detail or "").lower()
    if "billing" in text or "payment" in text or "credits" in text:
        return "유료 결제가 이 API 키가 속한 Google 프로젝트에 연결되어 있지 않습니다. 키를 만든 계정으로 AI Studio 결제를 확인해 주세요."
    if status in (401, 403) or "api key" in text or "api_key" in text:
        return "API 키가 거부되었습니다. 키를 발급한 Google 계정과 결제 계정이 같은지 확인해 주세요. 다른 계정으로만 결제하면 키가 그대로여도 막힙니다."
    if status == 429 or "quota" in text or "resource_exhausted" in text:
        return "이미지 생성 한도를 넘었습니다. 잠시 후 다시 시도해 주세요."
    if status == 404:
        return "이 키에서 해당 이미지 모델을 쓸 수 없습니다."
    if status == 400:
        return "이미지 생성 요청이 거부되었습니다. 거리뷰가 완전히 뜬 뒤 다시 시도해 주세요."
    return f"이미지 생성 API가 거부했습니다. ({status})"


def _post_interaction(api_key: str, body: dict) -> dict:
    request = urllib.request.Request(
        GEMINI_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as extra:
        detail = extra.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(_friendly_api_error(extra.code, detail)) from extra
    except urllib.error.URLError as extra:
        raise RuntimeError("이미지 생성 API에 연결하지 못했습니다. 네트워크를 확인해 주세요.") from extra


def generate_evening_scene(observation: dict, screenshot: dict, extras: dict | None = None) -> dict:
    api_key = gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 .env에 없습니다. Google AI Studio에서 키를 넣어 주세요.")

    mime_type, image_data = parse_screenshot(screenshot)
    extras = dict(extras or {})
    jpeg_size = _jpeg_dimensions(image_data) if mime_type == "image/jpeg" else None
    width = extras.get("image_width") or (jpeg_size[0] if jpeg_size else None)
    height = extras.get("image_height") or (jpeg_size[1] if jpeg_size else None)
    extras["image_width"] = width
    extras["image_height"] = height
    prompt = build_evening_prompt(observation, extras)
    preferred = (os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_MODEL).strip()
    models = [preferred, *[name for name in FALLBACK_MODELS if name != preferred]]
    sizes = [(os.environ.get("GEMINI_IMAGE_SIZE") or "1K").strip() or "1K", "1K"]
    aspect_ratio = closest_aspect_ratio(width, height)
    last_error = None

    for model in models:
        for image_size in dict.fromkeys(sizes):
            body = {
                "model": model,
                "input": [
                    {"type": "image", "mime_type": mime_type, "data": image_data},
                    {"type": "text", "text": prompt},
                ],
                "response_format": {
                    "type": "image",
                    "mime_type": "image/jpeg",
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                },
            }
            if model in THINKING_MODELS:
                body["generation_config"] = {"thinking_level": "high"}
            try:
                payload = _post_interaction(api_key, body)
                out_mime, out_data = _extract_image(payload)
                return {
                    "mime_type": out_mime,
                    "image": out_data,
                    "notice": "지금 보이는 거리뷰를 그대로 두고 하늘만 밤으로 바꾼 예상 장면입니다. 원본 거리뷰는 저장하지 않습니다.",
                }
            except RuntimeError as extra:
                last_error = extra
                continue

    raise last_error or RuntimeError("이미지 모델이 장면을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.")
