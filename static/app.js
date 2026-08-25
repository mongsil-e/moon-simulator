import { PhotoComposer } from "./photo-composer.js";

let THREE = null;


const byId = (id) => document.getElementById(id);
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const normalizeDegrees = (value) => ((value % 360) + 360) % 360;
const signedAngle = (value) => ((value + 540) % 360) - 180;
const degToRad = (value) => (Number(value) * Math.PI) / 180;
const radToDeg = (value) => (Number(value) * 180) / Math.PI;

const dom = {
    skyView: byId("skyView"),
    skyLoading: byId("skyLoading"),
    visibilityBadge: byId("visibilityBadge"),
    viewDirection: byId("viewDirection"),
    viewHeading: byId("viewHeading"),
    moonSceneLabel: byId("moonSceneLabel"),
    focusMoonButton: byId("focusMoonButton"),
    orientationButton: byId("orientationButton"),
    timeSlider: byId("timeSlider"),
    timelineTime: byId("timelineTime"),
    playButton: byId("playButton"),
    headerLocationButton: byId("headerLocationButton"),
    mapLocationButton: byId("mapLocationButton"),
    locationButton: byId("locationButton"),
    locationStatusDot: byId("locationStatusDot"),
    locationStatusText: byId("locationStatusText"),
    timezoneChip: byId("timezoneChip"),
    observationForm: byId("observationForm"),
    dateInput: byId("dateInput"),
    timeInput: byId("timeInput"),
    latitudeInput: byId("latitudeInput"),
    longitudeInput: byId("longitudeInput"),
    elevationInput: byId("elevationInput"),
    nowButton: byId("nowButton"),
    calculateButton: byId("calculateButton"),
    streetViewButton: byId("streetViewButton"),
    phaseOrb: byId("phaseOrb"),
    observationTitle: byId("observationTitle"),
    phaseText: byId("phaseText"),
    directionValue: byId("directionValue"),
    bearingDial: byId("bearingDial"),
    azimuthValue: byId("azimuthValue"),
    altitudeValue: byId("altitudeValue"),
    illuminationValue: byId("illuminationValue"),
    distanceValue: byId("distanceValue"),
    relativeGuide: byId("relativeGuide"),
    eventDate: byId("eventDate"),
    moonriseTime: byId("moonriseTime"),
    moonriseDirection: byId("moonriseDirection"),
    moonsetTime: byId("moonsetTime"),
    moonsetDirection: byId("moonsetDirection"),
    recommendationText: byId("recommendationText"),
    accuracyNote: byId("accuracyNote"),
    toast: byId("toast"),
    favoriteToggleButton: byId("favoriteToggleButton"),
    favoriteCloseButton: byId("favoriteCloseButton"),
    favoriteForm: byId("favoriteForm"),
    favoriteNameInput: byId("favoriteNameInput"),
    favoriteList: byId("favoriteList"),
    mapFavorites: byId("mapFavorites"),
};

const FAVORITES_KEY = "moon-simulator-favorites";
const FAVORITES_LIMIT = 20;

const state = {
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Seoul",
    data: null,
    activePosition: null,
    requestController: null,
    toastTimer: null,
    playbackTimer: null,
    locationSource: "default",
    hasFocusedOnce: false,
    map: null,
    mapLayers: null,
    mapReady: false,
    scene: null,
    camera: null,
    renderer: null,
    moonMesh: null,
    moonGlow: null,
    sunLight: null,
    trajectoryLine: null,
    resizeObserver: null,
    viewHeading: 0,
    viewPitch: 12,
    pointerActive: false,
    pointerX: 0,
    pointerY: 0,
    sensorEnabled: false,
    sensorReceived: false,
    photoComposer: null,
    nearbyPhoto: null,
    observationPromise: null,
    mapUpdating: false,
};


function pad(value) {
    return String(value).padStart(2, "0");
}


function toLocalInputValue(date) {
    return [
        date.getFullYear(), "-", pad(date.getMonth() + 1), "-", pad(date.getDate()),
        "T", pad(date.getHours()), ":", pad(date.getMinutes()),
    ].join("");
}


function isoToInputValue(isoValue) {
    return String(isoValue).slice(0, 16);
}


function getDateTimeInputValue() {
    const date = dom.dateInput?.value || "";
    const time = (dom.timeInput?.value || "00:00").slice(0, 5);
    return date ? `${date}T${time}` : "";
}


function setDateTimeInputValue(value) {
    const raw = String(value || "");
    const [datePart, timePart = "00:00"] = raw.split("T");
    if (dom.dateInput) dom.dateInput.value = datePart || "";
    if (dom.timeInput) dom.timeInput.value = timePart.slice(0, 5);
}


function timeFromIso(isoValue) {
    if (!isoValue) return "--:--";
    const match = String(isoValue).match(/T(\d{2}):(\d{2})/);
    return match ? `${match[1]}:${match[2]}` : "--:--";
}


function dateLabel(isoValue) {
    try {
        return new Intl.DateTimeFormat("ko-KR", { month: "long", day: "numeric" }).format(new Date(isoValue));
    } catch {
        return "선택한 날짜";
    }
}


function directionForHeading(heading) {
    const names = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"];
    return names[Math.round(normalizeDegrees(heading) / 45) % 8];
}


function minuteFromIso(isoValue) {
    const match = String(isoValue).match(/T(\d{2}):(\d{2})/);
    return match ? Number(match[1]) * 60 + Number(match[2]) : 720;
}


function formatNumber(value, digits = 1) {
    return Number(value).toLocaleString("ko-KR", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
}


function showToast(message, isError = false) {
    window.clearTimeout(state.toastTimer);
    dom.toast.textContent = message;
    dom.toast.classList.toggle("is-error", isError);
    dom.toast.classList.add("is-visible");
    state.toastTimer = window.setTimeout(() => dom.toast.classList.remove("is-visible"), 3600);
}


function setLoading(isLoading) {
    dom.calculateButton.disabled = isLoading;
    dom.streetViewButton.disabled = isLoading;
    dom.calculateButton.classList.toggle("is-loading", isLoading);
    const calculateLabel = dom.calculateButton.querySelector(".button-label");
    const streetLabel = dom.streetViewButton.querySelector(".button-label");
    if (calculateLabel) calculateLabel.textContent = isLoading ? "달 찾는 중" : "달 찾기";
    if (streetLabel) streetLabel.textContent = isLoading ? "준비 중" : "거리뷰 보기";
    if (isLoading && !state.data) {
        dom.visibilityBadge.textContent = "계산 중";
        dom.visibilityBadge.className = "visibility-badge is-loading";
    }
}


function setLocationStatus(text, active = false) {
    dom.locationStatusText.textContent = text;
    dom.locationStatusDot.classList.toggle("is-active", active);
}


async function requestObservation({ moveMap = false, focusMoon = true, openPhoto = false } = {}) {
    if (state.observationPromise) {
        const completed = await state.observationPromise;
        if (completed && openPhoto) state.photoComposer?.open();
        return completed;
    }

    if (dom.observationForm && !dom.observationForm.reportValidity()) {
        setLoading(false);
        return false;
    }

    const requestController = new AbortController();
    state.requestController = requestController;
    setLoading(true);

    state.observationPromise = (async () => {
        const loadingWatchdog = window.setTimeout(() => requestController.abort(), 20000);
        let completed = false;
        try {
            const response = await fetch("/api/moon-position", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    lat: Number(dom.latitudeInput.value),
                    lon: Number(dom.longitudeInput.value),
                    elevation: Number(dom.elevationInput.value || 0),
                    datetime: getDateTimeInputValue(),
                    timezone: state.timezone,
                }),
                signal: requestController.signal,
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "달 위치를 계산하지 못했습니다.");

            state.data = result;
            state.activePosition = result.position;
            dom.timeSlider.value = String(minuteFromIso(result.requested_time));
            updateDayInformation(result);
            updateTrajectory(result.trajectory);
            updateObservation(result.position, { moveMap, focusMoon });
            completed = true;
        } catch (error) {
            if (error.name === "AbortError") {
                showToast("달 위치 계산이 너무 오래 걸립니다. 다시 눌러 주세요.", true);
            } else {
                showToast(error.message || "서버와 연결하지 못했습니다.", true);
            }
        } finally {
            window.clearTimeout(loadingWatchdog);
            state.requestController = null;
            state.observationPromise = null;
            setLoading(false);
        }

        if (completed && openPhoto) state.photoComposer?.open();
        return completed;
    })();

    return state.observationPromise;
}


function updateDayInformation(data) {
    dom.phaseOrb.textContent = data.phase.emoji;
    dom.phaseText.textContent = `${data.phase.name} · 밝은 면 ${formatNumber(data.phase.illumination_percent)}%`;
    dom.illuminationValue.textContent = `${formatNumber(data.phase.illumination_percent)}%`;
    dom.eventDate.textContent = dateLabel(data.requested_time);
    dom.recommendationText.textContent = data.recommendation;
    dom.accuracyNote.textContent = data.notice;
    updateEvent(dom.moonriseTime, dom.moonriseDirection, data.events.rise);
    updateEvent(dom.moonsetTime, dom.moonsetDirection, data.events.set);
}


function updateEvent(timeElement, directionElement, eventData) {
    if (!eventData) {
        timeElement.textContent = "오늘 없음";
        directionElement.textContent = "지평선 교차 없음";
        return;
    }
    timeElement.textContent = timeFromIso(eventData.time);
    directionElement.textContent = `${eventData.direction} · ${formatNumber(eventData.azimuth_deg)}°`;
}


function updateObservation(position, { moveMap = false, focusMoon = false } = {}) {
    if (!position) return;
    state.activePosition = position;

    const above = Boolean(position.above_horizon);
    dom.visibilityBadge.textContent = above ? "지평선 위 · 관측 가능" : "지평선 아래 · 현재 안 보임";
    dom.visibilityBadge.className = `visibility-badge${above ? "" : " is-below"}`;
    dom.observationTitle.textContent = above ? "달이 지평선 위에 있습니다" : "달이 지평선 아래에 있습니다";
    dom.directionValue.textContent = `${position.direction} ${formatNumber(position.azimuth_deg)}°`;
    dom.azimuthValue.textContent = `${formatNumber(position.azimuth_deg)}°`;
    dom.altitudeValue.textContent = `${formatNumber(position.altitude_deg)}°`;
    dom.distanceValue.textContent = `${Math.round(position.distance_km || state.data.position.distance_km).toLocaleString("ko-KR")} km`;
    dom.timelineTime.textContent = timeFromIso(position.time);
    dom.bearingDial.querySelector(".dial-needle").style.transform = `rotate(${normalizeDegrees(position.azimuth_deg)}deg)`;
    updateRecommendation(position);

    updateMoonScene(position);
    updateMap(position, moveMap);
    updateRelativeGuide();
    state.photoComposer?.sync();
    if (focusMoon || !state.hasFocusedOnce) {
        focusViewOnMoon();
        state.hasFocusedOnce = true;
    }
}


function updateRecommendation(position) {
    const locationText = position.above_horizon
        ? `선택한 시각에는 ${position.direction}쪽, 지평선 위 ${formatNumber(position.altitude_deg)}°에서 달을 찾을 수 있습니다.`
        : `선택한 시각에는 달이 ${position.direction}쪽 지평선 아래 ${formatNumber(Math.abs(position.altitude_deg))}°에 있어 보이지 않습니다.`;
    const best = state.data?.best_position;
    const bestText = best?.altitude_deg > 0
        ? ` 오늘 가장 높이 오르는 시각은 ${timeFromIso(best.time)} 무렵이며 고도는 약 ${formatNumber(best.altitude_deg)}°입니다.`
        : " 선택한 날짜에는 달이 지평선 위로 올라오는 구간이 없습니다.";
    dom.recommendationText.textContent = locationText + bestText;
}


function updateFromSlider() {
    if (!state.data?.trajectory?.length) return;
    const minute = Number(dom.timeSlider.value);
    const closest = state.data.trajectory.reduce((best, item) => (
        Math.abs(item.minute_of_day - minute) < Math.abs(best.minute_of_day - minute) ? item : best
    ));
    setDateTimeInputValue(isoToInputValue(closest.time));
    updateObservation(closest);
}


function togglePlayback() {
    if (state.playbackTimer) {
        window.clearInterval(state.playbackTimer);
        state.playbackTimer = null;
        dom.playButton.classList.remove("is-playing");
        dom.playButton.setAttribute("aria-label", "시간 흐름 재생");
        return;
    }

    dom.playButton.classList.add("is-playing");
    dom.playButton.setAttribute("aria-label", "시간 흐름 멈추기");
    state.playbackTimer = window.setInterval(() => {
        let minute = Number(dom.timeSlider.value) + 15;
        if (minute > 1440) minute = 0;
        dom.timeSlider.value = String(minute);
        updateFromSlider();
    }, 520);
}


function useCurrentTime() {
    setDateTimeInputValue(toLocalInputValue(new Date()));
    requestObservation({ focusMoon: true });
}


function locateUser({ silent = false } = {}) {
    if (!("geolocation" in navigator)) {
        showToast("이 브라우저는 현재 위치 기능을 지원하지 않습니다. 지도를 눌러 위치를 지정해 주세요.", true);
        return;
    }

    setLocationStatus("현재 위치를 확인하는 중", false);
    dom.mapLocationButton?.classList.add("is-busy");
    const finish = () => dom.mapLocationButton?.classList.remove("is-busy");

    navigator.geolocation.getCurrentPosition(
        (position) => {
            finish();
            const { latitude, longitude, altitude, accuracy } = position.coords;
            dom.latitudeInput.value = latitude.toFixed(6);
            dom.longitudeInput.value = longitude.toFixed(6);
            if (Number.isFinite(altitude)) dom.elevationInput.value = String(Math.round(altitude));
            state.locationSource = "device";
            const accuracyText = Number.isFinite(accuracy) ? ` · 오차 약 ${Math.round(accuracy)}m` : "";
            setLocationStatus(`내 현재 위치${accuracyText}`, true);
            requestObservation({ moveMap: true, focusMoon: true });
            if (!silent) showToast("현재 위치를 기준으로 달의 방향을 계산했습니다.");
        },
        (error) => {
            finish();
            const insecure = !window.isSecureContext
                && location.hostname !== "localhost"
                && location.hostname !== "127.0.0.1";
            const messages = {
                1: insecure
                    ? "아이폰 사파리는 보안 연결이 아니면 위치를 막을 수 있습니다. 지도를 눌러 위치를 지정해 주세요."
                    : "위치 권한이 거부되었습니다. 설정에서 위치 접근을 허용하거나 지도를 눌러 주세요.",
                2: "현재 위치를 확인할 수 없습니다. 잠시 후 다시 시도하거나 지도를 눌러 주세요.",
                3: "위치 확인 시간이 초과되었습니다. 야외에서 다시 누르거나 지도를 눌러 주세요.",
            };
            setLocationStatus("위치 권한을 확인해 주세요", false);
            if (!silent) showToast(messages[error.code] || "현재 위치를 불러오지 못했습니다.", true);
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 10000 },
    );
}


function useGrantedLocationIfAvailable() {
    const insecure = !window.isSecureContext
        && location.hostname !== "localhost"
        && location.hostname !== "127.0.0.1";
    if (insecure || !navigator.permissions?.query) return;
    navigator.permissions.query({ name: "geolocation" }).then((permission) => {
        if (permission.state === "granted") locateUser({ silent: true });
    }).catch(() => {});
}


function loadFavorites() {
    try {
        const parsed = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}


function saveFavorites(items) {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(items.slice(0, FAVORITES_LIMIT)));
}


function currentPlace() {
    const lat = Number(dom.latitudeInput.value);
    const lon = Number(dom.longitudeInput.value);
    const elevation = Number(dom.elevationInput.value || 0);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return { lat, lon, elevation };
}


function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[char]));
}


function favoriteKey(place) {
    return `${place.lat.toFixed(5)},${place.lon.toFixed(5)}`;
}


function defaultFavoriteName(place) {
    return `위도 ${place.lat.toFixed(4)} · 경도 ${place.lon.toFixed(4)}`;
}


function renderFavorites() {
    const items = loadFavorites();
    const current = currentPlace();
    const currentKey = current ? favoriteKey(current) : "";
    if (!items.length) {
        dom.favoriteList.innerHTML = '<li class="map-favorites-empty">저장한 장소가 없습니다</li>';
        return;
    }
    dom.favoriteList.innerHTML = items.map((item) => {
        const active = favoriteKey(item) === currentKey ? " is-active" : "";
        return `<li>
            <button class="map-favorite-item${active}" type="button" data-favorite-id="${item.id}">
                <strong>${escapeHtml(item.name)}</strong>
                <small>${item.lat.toFixed(4)}, ${item.lon.toFixed(4)}</small>
            </button>
            <button class="map-favorite-delete" type="button" data-delete-id="${item.id}" aria-label="${escapeHtml(item.name)} 삭제">삭제</button>
        </li>`;
    }).join("");
}


function addFavorite(event) {
    event.preventDefault();
    const place = currentPlace();
    if (!place) {
        showToast("먼저 지도에서 위치를 선택해 주세요.", true);
        return;
    }
    const name = (dom.favoriteNameInput.value || "").trim() || defaultFavoriteName(place);
    const items = loadFavorites();
    if (items.some((item) => favoriteKey(item) === favoriteKey(place))) {
        showToast("이미 즐겨찾기에 있는 장소입니다.");
        return;
    }
    items.unshift({
        id: `${Date.now()}`,
        name,
        lat: place.lat,
        lon: place.lon,
        elevation: place.elevation,
    });
    saveFavorites(items);
    dom.favoriteNameInput.value = "";
    renderFavorites();
    showToast(`‘${name}’을 즐겨찾기에 넣었습니다.`);
}


function selectFavorite(id) {
    const item = loadFavorites().find((favorite) => favorite.id === id);
    if (!item) return;
    dom.latitudeInput.value = item.lat.toFixed(6);
    dom.longitudeInput.value = item.lon.toFixed(6);
    dom.elevationInput.value = String(Math.round(item.elevation || 0));
    state.locationSource = "favorite";
    setLocationStatus(`즐겨찾기 · ${item.name}`, true);
    closeFavorites();
    requestObservation({ moveMap: true, focusMoon: true });
    showToast(`‘${item.name}’으로 이동했습니다.`);
}


function deleteFavorite(id) {
    saveFavorites(loadFavorites().filter((item) => item.id !== id));
    renderFavorites();
}


function openFavorites() {
    renderFavorites();
    const place = currentPlace();
    if (place && !dom.favoriteNameInput.value) dom.favoriteNameInput.placeholder = defaultFavoriteName(place);
    dom.mapFavorites.hidden = false;
    dom.favoriteToggleButton.classList.add("is-active");
}


function closeFavorites() {
    dom.mapFavorites.hidden = true;
    dom.favoriteToggleButton.classList.remove("is-active");
}


function toggleFavorites() {
    if (dom.mapFavorites.hidden) openFavorites();
    else closeFavorites();
}


function destinationPoint(lat, lon, bearing, distanceKm = 5) {
    const radius = 6371.0088;
    const angularDistance = distanceKm / radius;
    const latRad = degToRad(lat);
    const lonRad = degToRad(lon);
    const bearingRad = degToRad(bearing);
    const destLat = Math.asin(
        Math.sin(latRad) * Math.cos(angularDistance)
        + Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearingRad),
    );
    const destLon = lonRad + Math.atan2(
        Math.sin(bearingRad) * Math.sin(angularDistance) * Math.cos(latRad),
        Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(destLat),
    );
    return [radToDeg(destLat), ((radToDeg(destLon) + 540) % 360) - 180];
}


function attachMapOverlay(map) {
    const overlay = byId("mapOverlay");
    const container = map && map.getContainer();
    if (!overlay || !container) return;
    if (overlay.parentElement !== container) {
        container.appendChild(overlay);
    }
    window.L.DomEvent.disableClickPropagation(overlay);
    window.L.DomEvent.disableScrollPropagation(overlay);
}


function initMap(attempt = 0) {
    if (state.mapReady) return;
    if (!window.L) {
        if (attempt < 40) {
            window.setTimeout(() => initMap(attempt + 1), 80);
            return;
        }
        const mapNode = byId("map");
        if (mapNode) mapNode.textContent = "지도를 불러오지 못했습니다. 네트워크 연결을 확인해 주세요.";
        showToast("지도 모듈을 불러오지 못했습니다. 좌표를 직접 입력해 주세요.", true);
        return;
    }

    state.map = window.L.map("map", { zoomControl: false, attributionControl: true }).setView([37.5665, 126.978], 12);
    attachMapOverlay(state.map);
    window.L.control.zoom({ zoomInTitle: "지도 확대", zoomOutTitle: "지도 축소" }).addTo(state.map);
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(state.map);
    state.mapLayers = window.L.layerGroup().addTo(state.map);
    state.map.on("click", (event) => {
        dom.latitudeInput.value = event.latlng.lat.toFixed(6);
        dom.longitudeInput.value = event.latlng.lng.toFixed(6);
        state.locationSource = "map";
        setLocationStatus("지도에서 선택한 위치", true);
        requestObservation({ moveMap: true, focusMoon: true });
    });
    state.mapReady = true;
    window.setTimeout(() => state.map.invalidateSize(), 120);
    if (state.activePosition) updateMap(state.activePosition, true);
}


function mapPointAlongBearing(lat, lon, azimuthDeg, fraction = 0.36) {
    return destinationPoint(lat, lon, azimuthDeg, 1.6 * (0.7 + fraction));
}


function moonMapFraction(altitudeDeg) {
    const altitude = Number(altitudeDeg);
    if (!Number.isFinite(altitude) || altitude <= 0) return 0.22;
    return clamp(0.22 + (altitude / 90) * 0.32, 0.22, 0.54);
}


function addMoonMarker(latlng, item, { current = false } = {}) {
    const above = Boolean(item.above_horizon);
    const label = item.label || timeFromIso(item.time);
    const moonIcon = window.L.divIcon({
        className: "map-leaflet-icon",
        html: `<div class="map-moon-marker ${above ? "is-visible" : "is-hidden"}${current ? " is-current" : ""}"><span class="map-moon-orb"></span><span class="map-moon-time">${label}</span></div>`,
        iconSize: [44, 48],
        iconAnchor: [22, 16],
    });
    window.L.marker(latlng, {
        icon: moonIcon,
        interactive: false,
        keyboard: false,
        zIndexOffset: current ? 700 : 500,
    }).addTo(state.mapLayers);
}


function updateMap(position, moveMap = false) {
    if (!state.mapReady || !state.data || state.mapUpdating) return;
    state.mapUpdating = true;
    try {
    const lat = Number(state.data.observer.lat);
    const lon = Number(state.data.observer.lon);
    const origin = [lat, lon];
    const hourly = Array.isArray(state.data.hourly_path) ? state.data.hourly_path : [];
    const azimuth = normalizeDegrees(position.azimuth_deg);
    const above = Boolean(position.above_horizon);
    const moonPoint = mapPointAlongBearing(lat, lon, azimuth, moonMapFraction(position.altitude_deg));
    const lineEnd = mapPointAlongBearing(lat, lon, azimuth, moonMapFraction(position.altitude_deg) + 0.1);
    const wedgeLeft = mapPointAlongBearing(lat, lon, azimuth - 16, moonMapFraction(position.altitude_deg) + 0.08);
    const wedgeRight = mapPointAlongBearing(lat, lon, azimuth + 16, moonMapFraction(position.altitude_deg) + 0.08);
    const lineColor = above ? "#f5d98b" : "#9aa7a2";

    state.mapLayers.clearLayers();
    window.L.polygon([origin, wedgeLeft, wedgeRight], {
        stroke: false,
        fillColor: lineColor,
        fillOpacity: above ? 0.18 : 0.1,
        interactive: false,
    }).addTo(state.mapLayers);
    window.L.polyline([origin, lineEnd], {
        color: lineColor,
        weight: 4,
        opacity: above ? 0.9 : 0.55,
        dashArray: above ? null : "7 8",
        lineCap: "round",
        interactive: false,
    }).addTo(state.mapLayers);

    const hourlyPoints = hourly.map((item) => mapPointAlongBearing(
        lat,
        lon,
        item.azimuth_deg,
        moonMapFraction(item.altitude_deg),
    ));
    if (hourlyPoints.length > 1) {
        window.L.polyline(hourlyPoints, {
            color: "rgba(245, 217, 139, 0.72)",
            weight: 3,
            opacity: 0.9,
            lineCap: "round",
            lineJoin: "round",
            interactive: false,
        }).addTo(state.mapLayers);
    }
    let closestIndex = -1;
    let closestDiff = Infinity;
    const selectedMs = new Date(position.time).getTime();
    hourly.forEach((item, index) => {
        const diff = Math.abs(new Date(item.time).getTime() - selectedMs);
        if (diff < closestDiff) {
            closestDiff = diff;
            closestIndex = index;
        }
    });
    hourly.forEach((item, index) => {
        addMoonMarker(hourlyPoints[index], item, { current: index === closestIndex && closestDiff < 45 * 60 * 1000 });
    });
    if (!hourly.length || closestDiff >= 45 * 60 * 1000) {
        addMoonMarker(moonPoint, {
            ...position,
            label: timeFromIso(position.time),
        }, { current: true });
    }

    const observerIcon = window.L.divIcon({
        className: "map-leaflet-icon",
        html: '<div class="observer-marker"></div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
    });
    window.L.marker(origin, { icon: observerIcon, zIndexOffset: 800 })
        .bindTooltip(`내가 서 있는 곳<br>위도 ${lat.toFixed(4)} · 경도 ${lon.toFixed(4)}`, { direction: "top" })
        .addTo(state.mapLayers);

    const observerKey = `${lat.toFixed(5)},${lon.toFixed(5)}`;
    if (state.nearbyPhoto?.observer_key === observerKey) {
        const photoIcon = window.L.divIcon({
            className: "map-leaflet-icon",
            html: '<div class="photo-location-marker" aria-hidden="true">뷰</div>',
            iconSize: [42, 24],
            iconAnchor: [21, 12],
        });
        window.L.marker([state.nearbyPhoto.lat, state.nearbyPhoto.lon], {
            icon: photoIcon,
            title: "거리뷰 촬영 지점",
            alt: "거리뷰 촬영 지점",
        })
            .bindTooltip("네이버 거리뷰 촬영 지점", { direction: "top" })
            .addTo(state.mapLayers);
    }

    if (moveMap) {
        if (hourlyPoints.length) {
            const bounds = window.L.latLngBounds([origin, ...hourlyPoints]);
            state.map.fitBounds(bounds, { padding: [36, 36], maxZoom: 14, animate: false });
        } else {
            const targetZoom = state.map.getZoom() || 13;
            const current = state.map.getCenter();
            const target = window.L.latLng(origin);
            if (!current || current.distanceTo(target) > 12) {
                state.map.setView(origin, targetZoom, { animate: false });
            }
        }
    }
    } finally {
        state.mapUpdating = false;
    }
}


function scenePosition(azimuth, altitude, radius = 40) {
    const azimuthRad = degToRad(azimuth);
    const altitudeRad = degToRad(altitude);
    const horizontal = Math.cos(altitudeRad) * radius;
    return new THREE.Vector3(
        Math.sin(azimuthRad) * horizontal,
        1.7 + Math.sin(altitudeRad) * radius,
        Math.cos(azimuthRad) * horizontal,
    );
}


function createSkyMaterial() {
    return new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: {},
        vertexShader: `
            varying vec3 vWorldPosition;
            void main() {
                vec4 worldPosition = modelMatrix * vec4(position, 1.0);
                vWorldPosition = worldPosition.xyz;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            varying vec3 vWorldPosition;
            void main() {
                float height = normalize(vWorldPosition).y;
                vec3 horizon = vec3(0.075, 0.20, 0.165);
                vec3 zenith = vec3(0.008, 0.035, 0.050);
                vec3 below = vec3(0.025, 0.070, 0.055);
                vec3 color = height >= 0.0
                    ? mix(horizon, zenith, smoothstep(0.0, 0.9, height))
                    : mix(horizon, below, smoothstep(0.0, -0.65, height));
                gl_FragColor = vec4(color, 1.0);
            }
        `,
    });
}


function createMoonTexture() {
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 512;
    const context = canvas.getContext("2d");
    const gradient = context.createRadialGradient(178, 154, 18, 256, 256, 256);
    gradient.addColorStop(0, "#fff8d4");
    gradient.addColorStop(0.55, "#d9cfad");
    gradient.addColorStop(1, "#817b69");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 512, 512);

    const craters = [
        [132, 150, 35, 0.17], [318, 115, 28, 0.13], [356, 255, 49, 0.16],
        [218, 315, 37, 0.13], [105, 340, 22, 0.12], [280, 205, 19, 0.12],
        [408, 350, 27, 0.12], [190, 92, 14, 0.13], [260, 405, 44, 0.09],
    ];
    craters.forEach(([x, y, radius, alpha]) => {
        const crater = context.createRadialGradient(x - radius * 0.25, y - radius * 0.25, 1, x, y, radius);
        crater.addColorStop(0, `rgba(92, 89, 77, ${alpha * 1.4})`);
        crater.addColorStop(0.72, `rgba(68, 66, 57, ${alpha})`);
        crater.addColorStop(1, "rgba(255,255,255,0.04)");
        context.fillStyle = crater;
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.fill();
    });
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
}


function createGlowTexture() {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const context = canvas.getContext("2d");
    const gradient = context.createRadialGradient(64, 64, 5, 64, 64, 64);
    gradient.addColorStop(0, "rgba(255, 237, 180, 0.7)");
    gradient.addColorStop(0.18, "rgba(255, 231, 164, 0.3)");
    gradient.addColorStop(1, "rgba(255, 220, 140, 0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(canvas);
}


function createTextSprite(text, color = "#d6eee5", fontSize = 54) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 128;
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.font = `800 ${fontSize}px sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.shadowColor = "rgba(0, 0, 0, 0.7)";
    context.shadowBlur = 12;
    context.fillStyle = color;
    context.fillText(text, 128, 64);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
    sprite.scale.set(4.8, 2.4, 1);
    return sprite;
}


function addHorizonGuides() {
    const horizonMaterial = new THREE.LineBasicMaterial({ color: 0x85d9b7, transparent: true, opacity: 0.26 });
    const subtleMaterial = new THREE.LineDashedMaterial({ color: 0xb8d7cb, transparent: true, opacity: 0.13, dashSize: 0.8, gapSize: 1.2 });

    [0, 30, 60].forEach((altitude) => {
        const points = [];
        for (let azimuth = 0; azimuth <= 360; azimuth += 3) points.push(scenePosition(azimuth, altitude, 43));
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.LineLoop(geometry, altitude === 0 ? horizonMaterial : subtleMaterial);
        if (altitude !== 0) line.computeLineDistances();
        state.scene.add(line);
    });

    [0, 45, 90, 135, 180, 225, 270, 315].forEach((azimuth) => {
        const points = [];
        for (let altitude = 0; altitude <= 90; altitude += 3) points.push(scenePosition(azimuth, altitude, 43));
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), subtleMaterial);
        line.computeLineDistances();
        state.scene.add(line);
    });

    const cardinals = [
        ["북", 0, "#ff9b8f"], ["동", 90, "#d6eee5"],
        ["남", 180, "#d6eee5"], ["서", 270, "#d6eee5"],
    ];
    cardinals.forEach(([label, azimuth, color]) => {
        const sprite = createTextSprite(label, color);
        sprite.position.copy(scenePosition(azimuth, 3, 42));
        state.scene.add(sprite);
    });

    [["30°", 30], ["60°", 60]].forEach(([label, altitude]) => {
        const sprite = createTextSprite(label, "#78998e", 36);
        sprite.scale.set(3.2, 1.6, 1);
        sprite.position.copy(scenePosition(0, altitude, 43));
        state.scene.add(sprite);
    });
}


function addStars() {
    const positions = [];
    let seed = 9371;
    const random = () => {
        seed = (seed * 16807) % 2147483647;
        return (seed - 1) / 2147483646;
    };
    for (let index = 0; index < 520; index += 1) {
        const azimuth = random() * 360;
        const altitude = -8 + random() * 98;
        const point = scenePosition(azimuth, altitude, 68 + random() * 5);
        positions.push(point.x, point.y, point.z);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
        color: 0xe3f5ef,
        size: 0.11,
        transparent: true,
        opacity: 0.64,
        sizeAttenuation: true,
        depthWrite: false,
    });
    state.scene.add(new THREE.Points(geometry, material));
}


function hideSkyLoading() {
    dom.skyLoading?.classList.add("is-hidden");
}


async function loadThreeLibrary() {
    const urls = [
        "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
        "https://unpkg.com/three@0.180.0/build/three.module.js",
    ];
    let lastError = null;
    for (const url of urls) {
        try {
            THREE = await import(url);
            return THREE;
        } catch (error) {
            lastError = error;
        }
    }
    throw lastError || new Error("Three.js를 불러오지 못했습니다.");
}


function initThreeScene() {
    if (!THREE) return;
    try {
        state.scene = new THREE.Scene();
        state.scene.fog = new THREE.FogExp2(0x07110f, 0.004);
        state.camera = new THREE.PerspectiveCamera(58, 1, 0.1, 180);
        state.camera.position.set(0, 1.7, 0);
        state.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        state.renderer.outputColorSpace = THREE.SRGBColorSpace;
        state.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        state.renderer.toneMappingExposure = 1.08;
        dom.skyView.prepend(state.renderer.domElement);

        const sky = new THREE.Mesh(new THREE.SphereGeometry(82, 48, 30), createSkyMaterial());
        sky.position.y = 1.7;
        state.scene.add(sky);

        const ground = new THREE.Mesh(
            new THREE.CircleGeometry(70, 128),
            new THREE.MeshStandardMaterial({ color: 0x09140f, roughness: 1, metalness: 0 }),
        );
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = -0.02;
        state.scene.add(ground);

        addStars();
        addHorizonGuides();

        state.moonMesh = new THREE.Mesh(
            new THREE.SphereGeometry(1.38, 48, 32),
            new THREE.MeshStandardMaterial({
                map: createMoonTexture(),
                color: 0xfff5d7,
                roughness: 1,
                metalness: 0,
                transparent: true,
            }),
        );
        state.moonMesh.position.copy(scenePosition(60, 25));
        state.scene.add(state.moonMesh);

        state.moonGlow = new THREE.Sprite(new THREE.SpriteMaterial({
            map: createGlowTexture(),
            transparent: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        }));
        state.moonGlow.scale.set(7.2, 7.2, 1);
        state.moonGlow.position.copy(state.moonMesh.position);
        state.scene.add(state.moonGlow);

        state.scene.add(new THREE.AmbientLight(0x7f948d, 0.12));
        state.sunLight = new THREE.DirectionalLight(0xfff4cf, 5.2);
        state.sunLight.target = state.moonMesh;
        state.scene.add(state.sunLight);

        bindSceneControls();
        state.resizeObserver = new ResizeObserver(resizeScene);
        state.resizeObserver.observe(dom.skyView);
        resizeScene();
        updateCamera();
        state.renderer.setAnimationLoop(renderScene);
        hideSkyLoading();
    } catch (error) {
        console.error(error);
        if (dom.skyLoading) {
            dom.skyLoading.innerHTML = "<strong>3D 하늘을 표시할 수 없습니다</strong><span>그래픽 가속 설정을 확인해 주세요. 방향과 고도 정보는 아래에서 확인할 수 있습니다.</span>";
        }
        showToast("3D 그래픽을 시작하지 못했습니다. 지도와 숫자 정보는 계속 사용할 수 있습니다.", true);
    }
}


function resizeScene() {
    if (!state.renderer || !state.camera) return;
    const width = Math.max(1, dom.skyView.clientWidth);
    const height = Math.max(1, dom.skyView.clientHeight);
    state.renderer.setSize(width, height, false);
    state.camera.aspect = width / height;
    state.camera.updateProjectionMatrix();
}


function bindSceneControls() {
    const canvas = state.renderer.domElement;
    canvas.addEventListener("pointerdown", (event) => {
        state.pointerActive = true;
        state.pointerX = event.clientX;
        state.pointerY = event.clientY;
        state.sensorEnabled = false;
        canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", (event) => {
        if (!state.pointerActive) return;
        const deltaX = event.clientX - state.pointerX;
        const deltaY = event.clientY - state.pointerY;
        state.pointerX = event.clientX;
        state.pointerY = event.clientY;
        state.viewHeading = normalizeDegrees(state.viewHeading - deltaX * 0.2);
        state.viewPitch = clamp(state.viewPitch + deltaY * 0.16, -35, 88);
        updateCamera();
    });
    const stopPointer = () => { state.pointerActive = false; };
    canvas.addEventListener("pointerup", stopPointer);
    canvas.addEventListener("pointercancel", stopPointer);
    canvas.addEventListener("wheel", (event) => {
        event.preventDefault();
        state.camera.fov = clamp(state.camera.fov + event.deltaY * 0.025, 34, 78);
        state.camera.updateProjectionMatrix();
    }, { passive: false });
}


function updateCamera() {
    if (!state.camera) return;
    const lookAt = scenePosition(state.viewHeading, state.viewPitch, 10);
    state.camera.lookAt(lookAt);
    dom.viewDirection.textContent = `${directionForHeading(state.viewHeading)}쪽`;
    dom.viewHeading.textContent = `${Math.round(normalizeDegrees(state.viewHeading))}°`;
    updateRelativeGuide();
}


function focusViewOnMoon() {
    if (!state.activePosition) return;
    state.sensorEnabled = false;
    state.viewHeading = normalizeDegrees(state.activePosition.azimuth_deg);
    state.viewPitch = clamp(state.activePosition.altitude_deg, -25, 82);
    updateCamera();
}


function updateTrajectory(trajectory) {
    if (!state.scene || !trajectory?.length) return;
    if (state.trajectoryLine) {
        state.scene.remove(state.trajectoryLine);
        state.trajectoryLine.geometry.dispose();
        state.trajectoryLine.material.dispose();
    }
    const points = trajectory.map((item) => scenePosition(item.azimuth_deg, item.altitude_deg, 39.2));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
        color: 0x8af2c7,
        transparent: true,
        opacity: 0.42,
        depthWrite: false,
    });
    state.trajectoryLine = new THREE.Line(geometry, material);
    state.scene.add(state.trajectoryLine);
}


function updateMoonScene(position) {
    if (!state.moonMesh || !state.moonGlow) return;
    const moonPosition = scenePosition(position.azimuth_deg, position.altitude_deg, 39);
    state.moonMesh.position.copy(moonPosition);
    state.moonGlow.position.copy(moonPosition);
    state.moonMesh.material.opacity = position.above_horizon ? 1 : 0.5;
    state.moonGlow.material.opacity = position.above_horizon ? 0.7 : 0.18;

    const sunAltitude = position.sun_altitude_deg ?? state.data?.sun_position?.altitude_deg ?? 0;
    const sunAzimuth = position.sun_azimuth_deg ?? state.data?.sun_position?.azimuth_deg ?? 180;
    state.sunLight?.position.copy(scenePosition(sunAzimuth, sunAltitude, 120));
    state.sunLight?.target.updateMatrixWorld();
}


function updateRelativeGuide() {
    if (!state.activePosition) return;
    const horizontal = signedAngle(state.activePosition.azimuth_deg - state.viewHeading);
    const vertical = state.activePosition.altitude_deg - state.viewPitch;
    const horizontalText = horizontal >= 0 ? `오른쪽 ${Math.round(Math.abs(horizontal))}°` : `왼쪽 ${Math.round(Math.abs(horizontal))}°`;
    const verticalText = vertical >= 0 ? `위로 ${Math.round(Math.abs(vertical))}°` : `아래로 ${Math.round(Math.abs(vertical))}°`;
    const icon = dom.relativeGuide.querySelector(".guide-icon");
    const title = dom.relativeGuide.querySelector("strong");
    const detail = dom.relativeGuide.querySelector("p span");

    if (!state.activePosition.above_horizon) {
        icon.textContent = "↓";
        title.textContent = "현재 달은 지평선 아래에 있습니다";
        detail.textContent = `${state.activePosition.direction} 방향 · 고도 ${formatNumber(state.activePosition.altitude_deg)}°`;
    } else if (Math.abs(horizontal) < 4 && Math.abs(vertical) < 4) {
        icon.textContent = "◎";
        title.textContent = "화면 중앙이 달의 방향입니다";
        detail.textContent = "실제 하늘에서는 주변 건물과 구름을 함께 확인하세요";
    } else {
        icon.textContent = horizontal >= 0 ? "↗" : "↖";
        title.textContent = `${horizontalText}, ${verticalText}`;
        detail.textContent = "3D 화면을 움직이거나 ‘달 바라보기’를 눌러 보세요";
    }
}


function renderScene() {
    if (!state.renderer || !state.scene || !state.camera) return;
    state.renderer.render(state.scene, state.camera);
    updateMoonLabel();
}


function updateMoonLabel() {
    if (!state.moonMesh || !state.camera) return;
    const cameraDirection = new THREE.Vector3();
    state.camera.getWorldDirection(cameraDirection);
    const moonDirection = state.moonMesh.position.clone().sub(state.camera.position).normalize();
    const facingMoon = cameraDirection.dot(moonDirection) > 0.1;
    const projected = state.moonMesh.position.clone().project(state.camera);
    const onScreen = facingMoon && projected.z > -1 && projected.z < 1 && Math.abs(projected.x) < 1.05 && Math.abs(projected.y) < 1.05;
    dom.moonSceneLabel.hidden = !onScreen;
    if (!onScreen) return;
    dom.moonSceneLabel.style.left = `${(projected.x * 0.5 + 0.5) * dom.skyView.clientWidth}px`;
    dom.moonSceneLabel.style.top = `${(-projected.y * 0.5 + 0.5) * dom.skyView.clientHeight}px`;
}


async function enableDeviceOrientation() {
    if (!("DeviceOrientationEvent" in window)) {
        showToast("이 기기에서는 방향 센서를 사용할 수 없습니다. 3D 화면을 손으로 움직여 주세요.", true);
        return;
    }

    try {
        if (typeof window.DeviceOrientationEvent.requestPermission === "function") {
            const permission = await window.DeviceOrientationEvent.requestPermission();
            if (permission !== "granted") throw new Error("방향 센서 권한이 허용되지 않았습니다.");
        }
        state.sensorEnabled = true;
        state.sensorReceived = false;
        window.addEventListener("deviceorientationabsolute", handleDeviceOrientation, true);
        window.addEventListener("deviceorientation", handleDeviceOrientation, true);
        dom.orientationButton.textContent = "휴대폰 방향 연결 중";
        window.setTimeout(() => {
            if (!state.sensorReceived) showToast("방향 센서 값을 받지 못했습니다. 브라우저의 센서 권한을 확인해 주세요.", true);
        }, 1800);
    } catch (error) {
        showToast(error.message || "방향 센서를 연결하지 못했습니다.", true);
    }
}


function handleDeviceOrientation(event) {
    if (!state.sensorEnabled) return;
    let heading = null;
    if (Number.isFinite(event.webkitCompassHeading)) {
        heading = event.webkitCompassHeading;
    } else if (Number.isFinite(event.alpha) && (event.absolute || event.type === "deviceorientationabsolute")) {
        heading = 360 - event.alpha;
    }
    if (!Number.isFinite(heading)) return;

    const screenAngle = window.screen.orientation?.angle || window.orientation || 0;
    state.viewHeading = normalizeDegrees(heading + screenAngle);
    if (Number.isFinite(event.beta)) state.viewPitch = clamp(90 - event.beta, -25, 85);
    state.sensorReceived = true;
    dom.orientationButton.textContent = "휴대폰 방향 연결됨";
    updateCamera();
}


function bindInterface() {
    dom.observationForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        requestObservation({ moveMap: true, focusMoon: true, openPhoto: false });
    });
    dom.calculateButton?.addEventListener("click", () => {
        requestObservation({ moveMap: true, focusMoon: true, openPhoto: false });
    });
    dom.streetViewButton?.addEventListener("click", async () => {
        const completed = await requestObservation({ moveMap: true, focusMoon: true, openPhoto: false });
        if (completed) state.photoComposer?.open();
    });
    dom.nowButton?.addEventListener("click", useCurrentTime);
    dom.dateInput?.addEventListener("change", () => {
        requestObservation({ moveMap: true, focusMoon: true, openPhoto: false });
    });
    dom.timeSlider?.addEventListener("input", updateFromSlider);
    dom.playButton?.addEventListener("click", togglePlayback);
    dom.focusMoonButton?.addEventListener("click", focusViewOnMoon);
    dom.orientationButton?.addEventListener("click", enableDeviceOrientation);
    [dom.headerLocationButton, dom.mapLocationButton, dom.locationButton].filter(Boolean).forEach((button) => {
        button.addEventListener("click", () => locateUser());
    });
    dom.favoriteToggleButton?.addEventListener("click", toggleFavorites);
    dom.favoriteCloseButton?.addEventListener("click", closeFavorites);
    dom.favoriteForm?.addEventListener("submit", addFavorite);
    dom.favoriteList?.addEventListener("click", (event) => {
        const select = event.target.closest("[data-favorite-id]");
        const remove = event.target.closest("[data-delete-id]");
        if (remove) {
            deleteFavorite(remove.dataset.deleteId);
            return;
        }
        if (select) selectFavorite(select.dataset.favoriteId);
    });
}


async function initialize() {
    try {
        setDateTimeInputValue(toLocalInputValue(new Date()));
        if (dom.timezoneChip) {
            dom.timezoneChip.textContent = state.timezone;
            dom.timezoneChip.title = `기기 시간대: ${state.timezone}`;
        }
        bindInterface();
        initMap();
        requestObservation({ moveMap: true, focusMoon: true });
        try {
            state.photoComposer = new PhotoComposer({
                getPosition: () => state.activePosition,
                getPhase: () => state.data?.phase,
                getObserver: () => state.data?.observer,
                showToast,
                onOpen: () => {
                    if (state.playbackTimer) togglePlayback();
                },
                onRemotePhoto: (photo) => {
                    const previous = state.nearbyPhoto;
                    state.nearbyPhoto = photo;
                    const same = previous?.lat === photo?.lat && previous?.lon === photo?.lon && previous?.id === photo?.id;
                    if (!same && state.mapReady && state.activePosition) updateMap(state.activePosition, false);
                },
            });
        } catch (error) {
            console.error(error);
        }
        window.setTimeout(hideSkyLoading, 8000);
        await loadThreeLibrary();
        initThreeScene();
        if (state.activePosition) updateMoonScene(state.activePosition);
    } catch (error) {
        console.error(error);
        hideSkyLoading();
        if (dom.skyLoading) {
            dom.skyLoading.innerHTML = "<strong>3D 하늘을 표시할 수 없습니다</strong><span>지도에서 달 방향은 계속 확인할 수 있습니다.</span>";
            dom.skyLoading.classList.remove("is-hidden");
        }
    }
}


initialize();
