const NAVER_FOV_MIN = 20;
const NAVER_FOV_MAX = 100;

const normalizeDegrees = (value) => ((Number(value) % 360) + 360) % 360;
const shortestDelta = (from, to) => ((Number(to) - Number(from) + 540) % 360) - 180;

let loadingPromise = null;

export function azimuthToPan(azimuth) {
    const normalized = normalizeDegrees(azimuth);
    return normalized > 180 ? normalized - 360 : normalized;
}

export function panToAzimuth(pan) {
    return normalizeDegrees(pan);
}

export function clampStreetViewFov(value) {
    const fov = Number(value);
    if (!Number.isFinite(fov)) return 70;
    return Math.min(NAVER_FOV_MAX, Math.max(NAVER_FOV_MIN, fov));
}

export function moonPovFromPosition(position, currentFov = 70) {
    const altitude = Number(position?.altitude_deg);
    return {
        pan: azimuthToPan(position?.azimuth_deg),
        tilt: Math.min(80, Math.max(-25, Number.isFinite(altitude) ? altitude : 0)),
        fov: clampStreetViewFov(currentFov),
    };
}

export function projectMoonOnStreetView(position, pov, width, height) {
    const safeWidth = Math.max(1, Number(width) || 1);
    const safeHeight = Math.max(1, Number(height) || 1);
    const fovDeg = clampStreetViewFov(pov?.fov);
    const fov = fovDeg * Math.PI / 180;
    const pitch = Number(pov?.tilt || 0) * Math.PI / 180;
    const altitude = Number(position?.altitude_deg) * Math.PI / 180;
    const deltaPan = shortestDelta(panToAzimuth(pov?.pan), position?.azimuth_deg);
    const delta = deltaPan * Math.PI / 180;
    const cosAltitude = Math.cos(altitude);
    const xCamera = cosAltitude * Math.sin(delta);
    const yCamera = Math.cos(pitch) * Math.sin(altitude)
        - Math.sin(pitch) * cosAltitude * Math.cos(delta);
    const zCamera = Math.sin(pitch) * Math.sin(altitude)
        + Math.cos(pitch) * cosAltitude * Math.cos(delta);
    const vfov = 2 * Math.atan(Math.tan(fov / 2) * (safeHeight / safeWidth)) * (180 / Math.PI);
    const distance = Number(position?.distance_km || 384400);
    const angularDiameter = Number(position?.angular_diameter_deg)
        || (2 * Math.asin(Math.min(1, 1737.4 / distance)) * (180 / Math.PI));

    if (zCamera <= 0.02) {
        return {
            x: safeWidth / 2,
            y: safeHeight / 2,
            radius: 0,
            fov: fovDeg,
            vfov,
            deltaPan,
            state: "behind",
            canDraw: false,
            width: safeWidth,
            height: safeHeight,
        };
    }

    const focalLength = (safeWidth / 2) / Math.tan(fov / 2);
    const x = safeWidth / 2 + focalLength * xCamera / zCamera;
    const y = safeHeight / 2 - focalLength * yCamera / zCamera;
    const radius = Math.max(2, focalLength * Math.tan((angularDiameter * Math.PI / 180) / 2) / zCamera);
    const intersects = x + radius >= 0 && x - radius <= safeWidth && y + radius >= 0 && y - radius <= safeHeight;
    const fullyInside = x - radius >= 0 && x + radius <= safeWidth && y - radius >= 0 && y + radius <= safeHeight;
    return {
        x,
        y,
        radius,
        fov: fovDeg,
        vfov,
        deltaPan,
        state: !intersects ? "outside" : fullyInside ? "inside" : "partial",
        canDraw: intersects,
        width: safeWidth,
        height: safeHeight,
    };
}

export function loadNaverMaps(clientId) {
    if (window.naver?.maps?.Panorama) return Promise.resolve(window.naver.maps);
    if (loadingPromise) return loadingPromise;
    if (!clientId) {
        return Promise.reject(new Error("네이버 지도 Client ID가 없습니다."));
    }

    loadingPromise = new Promise((resolve, reject) => {
        const finish = () => {
            const maps = window.naver?.maps;
            if (maps?.Panorama) {
                resolve(maps);
                return true;
            }
            return false;
        };

        const existing = document.querySelector("script[data-naver-maps]");
        const attach = (script) => {
            script.addEventListener("load", () => {
                if (finish()) return;
                if (typeof window.naver?.maps?.onJSContentLoaded === "function"
                    || "onJSContentLoaded" in (window.naver?.maps || {})) {
                    const previous = window.naver.maps.onJSContentLoaded;
                    window.naver.maps.onJSContentLoaded = () => {
                        previous?.();
                        if (!finish()) reject(new Error("네이버 거리뷰 모듈을 불러오지 못했습니다."));
                    };
                }
                window.setTimeout(() => {
                    if (!finish()) {
                        loadingPromise = null;
                        reject(new Error("네이버 거리뷰 모듈을 불러오지 못했습니다."));
                    }
                }, 4000);
            }, { once: true });
            script.addEventListener("error", () => {
                loadingPromise = null;
                reject(new Error("네이버 지도 스크립트를 불러오지 못했습니다. 웹 서비스 URL에 localhost가 등록됐는지 확인해 주세요."));
            }, { once: true });
        };

        if (existing) {
            attach(existing);
            return;
        }

        const script = document.createElement("script");
        const params = new URLSearchParams({
            ncpKeyId: clientId,
            ncpClientId: clientId,
            submodules: "panorama",
        });
        script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?${params}`;
        script.async = true;
        script.dataset.naverMaps = "true";
        attach(script);
        document.head.appendChild(script);
    });
    return loadingPromise;
}

export { NAVER_FOV_MIN, NAVER_FOV_MAX };
