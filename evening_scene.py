from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.1-flash-image"
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


def build_evening_prompt(observation: dict, extras: dict | None = None) -> str:
    extras = extras or {}
    position = observation.get("position") or {}
    phase = observation.get("phase") or {}
    sun = observation.get("sun_position") or {}
    place = str(extras.get("place_name") or "").strip()
    heading = extras.get("view_heading_deg")

    altitude = position.get("altitude_deg")
    azimuth = position.get("azimuth_deg")
    direction = position.get("direction") or "남"
    above = bool(position.get("above_horizon"))
    phase_name = phase.get("name") or "달"
    illumination = phase.get("illumination_percent")
    sun_alt = sun.get("altitude_deg")

    moon_line = (
        f"Keep the existing moon in the same screen position. It is a {phase_name} "
        f"({illumination}% illuminated), about {altitude}° above the horizon toward {direction} "
        f"(azimuth {azimuth}°). It must look like the real moon actually rose in this sky: "
        "correct angular size for a naked-eye night photo, realistic terminator and crater shading, "
        "not a sticker, icon, or giant fake overlay."
        if above
        else "The moon is below the horizon in this view. Do not add a large fake moon."
    )
    lighting = (
        "true night after nightfall: deep navy-black sky, not dusk, not blue hour, not evening glow"
    )
    place_line = f"Location cue: {place}." if place else "This is a Korean street-level view."
    heading_line = f"The camera is facing heading {heading}°." if heading is not None else ""

    return (
        "Edit this exact street-level screenshot into a photorealistic night photograph. "
        "Preserve the buildings, road, sidewalk, signs, trees, and camera composition as closely as possible. "
        "Do not add any new buildings, houses, towers, or other structures that are not already in the screenshot. "
        "Do not densify the skyline or invent extra architecture. Keep only the existing buildings. "
        "Do not restyle the street into a different city or invent new landmarks. "
        f"{place_line} {heading_line} "
        f"Replace the daytime or washed-out sky with a high-quality {lighting}. "
        "Add realistic layered clouds, faint stars if the sky is dark enough, and atmospheric haze. "
        f"{moon_line} "
        "Obey real-world physics of this environment: atmospheric scattering, perspective, and light transport. "
        "Moonlight must fall from the moon's actual direction onto clouds, rooftops, pavement, and water. "
        "Shadows, highlights, and reflections must match that light direction. "
        "Near the horizon the moon may be slightly warmer from atmosphere; higher up it is cooler and clearer. "
        "Existing street lamps and windows keep local warm light, but they must mix physically with moonlight, not glow unnaturally. "
        "Clouds must occlude or dim the moon only if they sit in front of it. "
        "Make it indistinguishable from a real handheld night photograph of this exact place. "
        "Ultra high-resolution night photography, sharp details, photoreal, no text, no UI, "
        "no watermark, no extra logos, no extra people, 16:9 framing if you crop slightly."
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


def generate_evening_scene(observation: dict, screenshot: dict, extras: dict | None = None) -> dict:
    api_key = gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 .env에 없습니다. Google AI Studio에서 키를 넣어 주세요.")

    mime_type, image_data = parse_screenshot(screenshot)
    prompt = build_evening_prompt(observation, extras)
    model = (os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_MODEL).strip()
    image_size = (os.environ.get("GEMINI_IMAGE_SIZE") or "2K").strip() or "2K"

    body = {
        "model": model,
        "input": [
            {"type": "text", "text": prompt},
            {"type": "image", "mime_type": mime_type, "data": image_data},
        ],
        "response_format": {
            "type": "image",
            "mime_type": "image/jpeg",
            "aspect_ratio": "16:9",
            "image_size": image_size,
        },
        "generation_config": {"thinking_level": "high"},
    }
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
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"이미지 생성 API가 거부했습니다. ({exc.code}) {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("이미지 생성 API에 연결하지 못했습니다. 네트워크를 확인해 주세요.") from exc

    out_mime, out_data = _extract_image(payload)
    return {
        "mime_type": out_mime,
        "image": out_data,
        "notice": "지금 보이는 화면을 바탕으로 만든 예상 밤 장면입니다. 원본 거리뷰는 저장하지 않습니다.",
    }
