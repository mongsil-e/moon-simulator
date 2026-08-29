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
        raise ValueError("현재 화면을 담지 못했습니다. 거리뷰가 화면에 보이도록 한 뒤 다시 눌러 주세요.")

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
        raise ValueError("화면 캡처가 비어 있습니다. 거리뷰가 완전히 보인 뒤 다시 시도해 주세요.")
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
    moon_alt = _finite_number((observation.get("position") or {}).get("altitude_deg"))
    moon_up = bool((observation.get("position") or {}).get("above_horizon")) and (moon_alt or 0) > 0

    if sun_alt is None or sun_alt <= -18:
        sky_tone = "deep velvety midnight blue and dark indigo night sky"
    elif sun_alt <= -12:
        sky_tone = "rich dark indigo twilight night sky with subtle depth"
    elif sun_alt <= -6:
        sky_tone = "deep nautical blue night sky with a soft atmospheric gradient"
    else:
        sky_tone = "atmospheric deep dusk-blue sky"

    stars = "Sprinkle a few faint, realistic stars in the upper clear sky without fantasy nebulas, purple tint, or artificial clouds."
    horizon_glow = "Render a gentle, natural warm city horizon glow that seamlessly blends into the night sky."

    low_moon_scattering = ""
    if moon_up and moon_alt is not None and moon_alt < 12:
        low_moon_scattering = (
            " Because the moon is near the horizon, add a soft, warm atmospheric haze around the moon and lower horizon."
        )

    return (
        f"Render a clear, photorealistic night sky with a {sky_tone}. "
        f"{horizon_glow}{low_moon_scattering} {stars} "
        "Sky luminance should naturally graduate from the horizon to the darker zenith. "
        "Avoid murky charcoal/grey tones, oversaturated fantasy purple hues, or harsh artificial sky gradients."
    )


def _moon_visual_style(position: dict, phase: dict) -> str:
    altitude = _finite_number(position.get("altitude_deg"))
    illumination = _finite_number(phase.get("illumination_percent"))
    if altitude is None:
        color = "warm ivory to pale gold"
    elif altitude < 8:
        color = f"warm amber-gold at {altitude:.1f}° altitude, with gentle atmospheric softening"
    elif altitude < 20:
        color = f"soft pale gold at {altitude:.1f}° altitude"
    else:
        color = f"warm ivory to pale straw-yellow at {altitude:.1f}° altitude"

    if illumination is None:
        phase_desc = "Preserve the natural phase and terminator orientation."
    elif illumination < 5:
        phase_desc = "This is a subtle new moon with extremely faint earthshine."
    elif illumination < 45:
        phase_desc = (
            "Render a luminous crescent with visible surface texture, showing delicate earthshine on the unlit portion."
        )
    elif illumination < 90:
        phase_desc = "Render a bright, textured gibbous moon with a soft curved terminator."
    else:
        phase_desc = (
            "Render a luminous full or near-full disc with detailed lunar maria and crater texture, "
            "retaining highlight contrast without clipping to flat white."
        )

    return f"Render the lunar disc in a realistic {color}. {phase_desc}"


def _moon_edit_instruction(observation: dict, extras: dict | None) -> str:
    extras = extras or {}
    position = observation.get("position") or {}
    phase = observation.get("phase") or {}
    above = bool(position.get("above_horizon"))
    in_view = extras.get("moon_in_view")
    if in_view is None:
        in_view = above
    if not above or not in_view:
        return "The moon is outside the current frame; do not render a visible moon disc or glowing orb."

    left = _percent(extras.get("moon_x_percent"))
    top = _percent(extras.get("moon_y_percent"))
    diameter = _percent(extras.get("moon_diameter_percent"))
    phase_name = _english_phase(phase.get("name"))
    illumination = _finite_number(phase.get("illumination_percent"))
    phase_detail = (
        f"a photorealistic {phase_name} ({illumination:.0f}% illumination)"
        if illumination is not None
        else f"a photorealistic {phase_name}"
    )
    location = "the designated target area"
    if left is not None and top is not None:
        location = f"{left}% from the left and {top}% from the top"
    size_desc = f"roughly {diameter}% of the image width" if diameter is not None else "the guide diameter"

    return (
        "The supplied image already contains a visible guide moon. "
        "CRITICAL SCALE REQUIREMENT: Maintain the EXACT small scale, circular boundary, and diameter of the guide moon visible in the input image. "
        "Do NOT enlarge, expand, or magnify the moon into a giant cinematic supermoon. It must remain a realistic, compact astronomical disc matching the guide circle's small footprint ("
        f"{size_desc}). "
        f"Replace that guide with an authentic, highly detailed astronomical moon: {phase_detail}, centered at {location}. "
        f"{_moon_visual_style(position, phase)} "
        "Seamlessly integrate the moon into the night sky with a soft, subtle natural atmospheric glow along its limb without expanding the disc size itself. "
        "Existing foreground buildings, tree branches, power lines, or clouds must naturally occlude and overlap the moon with realistic edge blending. "
        "Do not enlarge the moon, do not render extra floating orbs, and do not distort the skyline."
    )


def _moonlight_line(observation: dict, extras: dict | None) -> str:
    extras = extras or {}
    position = observation.get("position") or {}
    phase = observation.get("phase") or {}
    altitude = _finite_number(position.get("altitude_deg"))
    illumination = _finite_number(phase.get("illumination_percent")) or 0

    if not position.get("above_horizon"):
        moonlight_desc = "The moon is below the horizon; apply ambient nighttime city illumination."
    else:
        moonlight_desc = (
            "Cast a subtle, elegant cool silver-blue moonlight sheen onto moon-facing rooftops, upper architectural ledges, and upward surfaces."
        )

    return (
        "NIGHT LIGHTING & EXPOSURE: Transform the daytime lighting into a balanced, high-quality night photograph. "
        "Preserve clear visibility and architectural textures on building facades, roadways, and sidewalks without crushing the scene into pitch black. "
        "Neutralize and soften harsh daytime sun shadows into smooth, diffuse nighttime ambient lighting. "
        "Naturally illuminate the urban scene: streetlamps, storefronts, and select building windows should display a warm, cozy ambient night glow that naturally reflects on streets and sidewalks. "
        f"{moonlight_desc} "
        "Do not introduce distorted, artificial high-contrast shadow stripes or conflicting harsh light beams."
    )


def build_evening_prompt(observation: dict, extras: dict | None = None) -> str:
    extras = extras or {}
    return (
        "Perform a high-resolution, photorealistic nighttime transformation of the supplied street view image. "
        "Preserve the exact camera angle, perspective, building layout, street geometry, vehicle placement, and structural composition of the original scene. "
        "Do not alter building architecture, road geometry, or fundamental scene layout. "
        f"ATMOSPHERE: {_sky_physics(observation)} "
        f"MOON: {_moon_edit_instruction(observation, extras)} "
        f"LIGHTING: {_moonlight_line(observation, extras)} "
        "Produce an authentic DSLR-quality night photograph with rich dynamic range, natural night ambiance, readable urban textures, and realistic optical properties. "
        "Do not enlarge the moon into a giant supermoon: strictly maintain the small, realistic scale of the guide moon in the input image. "
        "Avoid murky charcoal skies, pitch-black crushed shadows, sticker-like cutouts, painterly artifacts, or artificial CGI lighting."
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
        return "이미지 생성 요청이 거부되었습니다. 화면 캡처가 끝난 뒤 다시 시도해 주세요."
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
                    "notice": "현재 화면에 보이는 거리뷰와 달을 함께 전달해 만든 예상 밤 장면입니다. 원본 화면 캡처는 저장하지 않습니다.",
                }
            except RuntimeError as extra:
                last_error = extra
                continue

    raise last_error or RuntimeError("이미지 모델이 장면을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.")
