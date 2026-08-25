import {
    loadNaverMaps,
    moonPovFromPosition,
    projectMoonOnStreetView,
} from "./naver-maps.js";

const DEG_TO_RAD = Math.PI / 180;
const STREET_VIEW_MOON_SCALE = 6;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const byId = (id) => document.getElementById(id);


export class PhotoComposer {
    constructor({ getPosition, getPhase, getObserver, showToast, onOpen, onClose, onRemotePhoto }) {
        this.getPosition = getPosition;
        this.getPhase = getPhase;
        this.getObserver = getObserver;
        this.showToast = showToast;
        this.onOpen = onOpen;
        this.onClose = onClose;
        this.onRemotePhoto = onRemotePhoto;
        this.lastFocused = null;
        this.hasOpened = false;
        this.renderFrame = null;
        this.moonTexture = null;
        this.moonTextureKey = "";
        this.autoRequestController = null;
        this.autoRequestSerial = 0;
        this.autoRequestCoordinateKey = "";
        this.lastObserverKey = "";
        this.naverClientId = this.readNaverClientId();
        this.streetView = null;
        this.streetViewObserverKey = "";
        this.streetViewListeners = [];
        this.streetViewResizeObserver = null;
        this.updatingStreetViewPov = false;
        this.streetViewStatusWaiter = null;
        this.loaded = false;
        this.moonTrackFrame = null;

        this.dom = {
            appShell: document.querySelector(".app-shell"),
            workspace: byId("photoWorkspace"),
            launch: byId("photoCompositeButton"),
            modal: byId("photoModal"),
            backdrop: byId("photoModalBackdrop"),
            close: byId("photoModalClose"),
            empty: byId("photoEmptyState"),
            emptyTitle: byId("photoEmptyTitle"),
            emptyDescription: byId("photoEmptyDescription"),
            previewStage: byId("photoPreviewStage"),
            streetViewShell: byId("photoStreetViewShell"),
            streetView: byId("photoStreetView"),
            streetViewMoon: byId("photoStreetViewMoon"),
            streetViewMoonCanvas: byId("photoStreetViewMoonCanvas"),
            previewTitle: byId("photoPreviewTitle"),
            observerMeta: byId("photoObserverMeta"),
            moonMeta: byId("photoMoonMeta"),
            timeMeta: byId("photoTimeMeta"),
            autoInfo: byId("photoAutoInfo"),
            autoTitle: byId("photoAutoTitle"),
            autoMeta: byId("photoAutoMeta"),
            centerMoonButton: byId("photoCenterMoonButton"),
            eveningButton: byId("photoEveningButton"),
            eveningToggle: byId("eveningViewToggle"),
            eveningResult: byId("photoEveningResult"),
            eveningImage: byId("photoEveningImage"),
            eveningCaption: byId("photoEveningCaption"),
            eveningProgress: byId("photoEveningProgress"),
            eveningProgressTitle: byId("photoEveningProgressTitle"),
            eveningProgressMeta: byId("photoEveningProgressMeta"),
            eveningSaveButton: byId("photoEveningSaveButton"),
            status: byId("photoProjectionStatus"),
        };
        this.eveningEnabled = this.readEveningEnabled();
        this.eveningBusy = false;
        this.eveningTimer = null;
        this.lookAtMoonTimers = [];

        this.bindEvents();
        this.sync();
    }

    readAppConfig() {
        const node = document.getElementById("appConfig");
        try {
            return JSON.parse(node?.textContent || "{}");
        } catch {
            return {};
        }
    }

    readNaverClientId() {
        return String(this.readAppConfig()?.naver_maps?.client_id || "");
    }

    readEveningEnabled() {
        return Boolean(this.readAppConfig()?.evening_scene?.enabled);
    }

    bindEvents() {
        this.dom.launch?.addEventListener("click", () => this.open());
        this.dom.close.addEventListener("click", () => this.close());
        this.dom.backdrop.addEventListener("click", () => this.close());
        this.dom.centerMoonButton.addEventListener("click", () => {
            this.lookAtMoon();
            this.showToast("거리뷰를 현재 달의 방향과 높이에 맞췄습니다.");
        });
        this.dom.eveningButton?.addEventListener("click", () => this.generateEveningScene());
        this.dom.eveningSaveButton?.addEventListener("click", () => this.saveEveningImage());
        this.dom.eveningToggle?.addEventListener("click", (event) => {
            const view = event.target?.dataset?.view;
            if (view) this.showEveningView(view === "evening");
        });
        document.addEventListener("keydown", (event) => this.handleDialogKeydown(event));
    }

    open() {
        if (!this.dom.modal.hidden) {
            this.sync();
            return;
        }
        const position = this.getPosition();
        if (!position) {
            this.showToast("달 위치 계산이 끝난 뒤 거리뷰를 열어 주세요.", true);
            return;
        }
        this.onOpen?.();
        this.lastFocused = document.activeElement;
        this.dom.modal.hidden = false;
        this.dom.appShell?.setAttribute("inert", "");
        document.body.classList.add("photo-modal-open");
        this.sync();
        if (this.loaded) this.startMoonTracking();
        window.requestAnimationFrame(() => this.dom.close.focus());
    }

    close() {
        if (this.dom.modal.hidden) return;
        this.dom.modal.hidden = true;
        this.dom.appShell?.removeAttribute("inert");
        document.body.classList.remove("photo-modal-open");
        this.stopMoonTracking();
        this.clearLookAtMoonTimers();
        this.onClose?.();
        const focusTarget = this.lastFocused?.isConnected ? this.lastFocused : document.getElementById("streetViewButton");
        focusTarget?.focus();
    }

    handleDialogKeydown(event) {
        if (this.dom.modal.hidden) return;
        if (event.key === "Escape") {
            event.preventDefault();
            this.close();
            return;
        }
        if (event.key !== "Tab") return;
        const focusable = [...this.dom.modal.querySelectorAll(
            'button:not([disabled]):not([tabindex="-1"]), input:not([disabled]):not([tabindex="-1"])',
        )].filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    coordinateKey(observer) {
        if (!observer || !Number.isFinite(Number(observer.lat)) || !Number.isFinite(Number(observer.lon))) return "";
        return `${Number(observer.lat).toFixed(5)},${Number(observer.lon).toFixed(5)}`;
    }

    setLoading(loading) {
        this.dom.empty?.classList.toggle("is-loading", Boolean(loading));
    }

    setStatus(type, title, detail) {
        const icon = this.dom.status.querySelector(":scope > span");
        const titleElement = this.dom.status.querySelector("strong");
        const detailElement = this.dom.status.querySelector("small");
        this.dom.status.className = "photo-projection-status";
        if (type === "warning") this.dom.status.classList.add("is-warning");
        if (type === "error") this.dom.status.classList.add("is-error");
        if (type === "success") this.dom.status.classList.add("is-success");
        icon.textContent = type === "error" ? "!" : type === "warning" ? "△" : type === "loading" ? "…" : "◎";
        titleElement.textContent = title;
        detailElement.textContent = detail;
    }

    showInfo(type, title, detail) {
        this.dom.autoInfo.hidden = false;
        this.dom.autoInfo.className = "photo-auto-info";
        if (type === "loading") this.dom.autoInfo.classList.add("is-loading");
        if (type === "error") this.dom.autoInfo.classList.add("is-error");
        if (type === "success") this.dom.autoInfo.classList.add("is-success");
        this.dom.autoTitle.textContent = title;
        this.dom.autoMeta.textContent = detail;
    }

    cancelLoad() {
        this.autoRequestController?.abort();
        this.autoRequestController = null;
        this.autoRequestCoordinateKey = "";
        this.autoRequestSerial += 1;
        this.setLoading(false);
    }

    hideStreetView() {
        this.stopMoonTracking();
        this.streetView?.setVisible(false);
        this.dom.streetViewShell.hidden = true;
        this.dom.streetViewMoon.hidden = true;
        this.loaded = false;
    }

    startMoonTracking() {
        if (this.moonTrackFrame) return;
        const tick = () => {
            this.moonTrackFrame = window.requestAnimationFrame(tick);
            if (this.dom.modal.hidden || !this.loaded || this.updatingStreetViewPov) return;
            this.updateStreetViewMoon();
        };
        this.moonTrackFrame = window.requestAnimationFrame(tick);
    }

    stopMoonTracking() {
        if (this.moonTrackFrame) window.cancelAnimationFrame(this.moonTrackFrame);
        this.moonTrackFrame = null;
    }

    async ensureStreetViewSize() {
        const node = this.dom.streetView;
        const read = () => ({ width: Math.round(node.clientWidth), height: Math.round(node.clientHeight) });
        const current = read();
        if (current.width >= 80 && current.height >= 80) return current;
        return new Promise((resolve) => {
            const observer = new ResizeObserver(() => {
                const size = read();
                if (size.width >= 80 && size.height >= 80) {
                    observer.disconnect();
                    resolve(size);
                }
            });
            observer.observe(node);
            window.setTimeout(() => {
                observer.disconnect();
                resolve(read());
            }, 800);
        });
    }

    resizeStreetView() {
        if (!this.streetView || this.dom.streetViewShell.hidden) return;
        const maps = window.naver?.maps;
        const width = Math.round(this.dom.streetView.clientWidth);
        const height = Math.round(this.dom.streetView.clientHeight);
        if (!maps || width < 80 || height < 80) return;
        const current = this.streetView.getSize?.();
        if (current && Math.abs(current.width - width) < 2 && Math.abs(current.height - height) < 2) return;
        this.streetView.setSize(new maps.Size(width, height));
        this.updateStreetViewMoon();
    }

    waitForStreetViewStatus(serial, observerKey, signal) {
        this.streetViewStatusWaiter?.cleanup();
        this.streetViewStatusWaiter = null;
        return new Promise((resolve, reject) => {
            const maps = window.naver?.maps;
            if (!maps || !this.streetView) {
                resolve("ERROR");
                return;
            }
            let settled = false;
            const finish = (status, error) => {
                if (settled) return;
                settled = true;
                window.clearTimeout(timer);
                maps.Event.removeListener(listener);
                signal?.removeEventListener("abort", onAbort);
                this.streetViewStatusWaiter = null;
                if (error) {
                    reject(error);
                    return;
                }
                if (serial !== this.autoRequestSerial || observerKey !== this.autoRequestCoordinateKey) {
                    reject(new DOMException("Aborted", "AbortError"));
                    return;
                }
                resolve(status);
            };
            const onAbort = () => finish(null, new DOMException("Aborted", "AbortError"));
            const listener = maps.Event.addListener(this.streetView, "pano_status", (status) => {
                finish(status === "OK" ? "OK" : "ERROR");
            });
            const timer = window.setTimeout(() => finish("ERROR"), 12000);
            signal?.addEventListener("abort", onAbort, { once: true });
            this.streetViewStatusWaiter = { cleanup: () => finish(null, new DOMException("Aborted", "AbortError")) };
            if (signal?.aborted) onAbort();
        });
    }

    bindStreetViewListeners() {
        const maps = window.naver?.maps;
        if (!maps || !this.streetView || this.streetViewListeners.length) return;
        this.streetViewListeners.push(
            maps.Event.addListener(this.streetView, "pov_changed", () => this.updateStreetViewMoon()),
            maps.Event.addListener(this.streetView, "pano_changed", () => {
                this.showLoadedInfo();
                this.scheduleLookAtMoon();
            }),
        );
        if (!this.streetViewResizeObserver) {
            this.streetViewResizeObserver = new ResizeObserver(() => this.resizeStreetView());
            this.streetViewResizeObserver.observe(this.dom.streetView);
        }
    }

    async loadStreetView({ force = false } = {}) {
        const observer = this.getObserver();
        const position = this.getPosition();
        const observerKey = this.coordinateKey(observer);
        if (!observerKey || !position) {
            this.showToast("위치와 달 계산이 끝난 뒤 거리뷰를 열 수 있습니다.", true);
            return;
        }
        if (!this.naverClientId) {
            this.showMissingKey();
            return;
        }
        if (!force && this.loaded && this.streetViewObserverKey === observerKey) {
            this.scheduleLookAtMoon();
            this.showLoadedInfo();
            this.startMoonTracking();
            return;
        }

        this.cancelLoad();
        const serial = this.autoRequestSerial;
        const controller = new AbortController();
        this.autoRequestController = controller;
        this.autoRequestCoordinateKey = observerKey;
        this.setLoading(true);
        this.showInfo("loading", "네이버 거리뷰를 불러오는 중입니다", "선택한 좌표에서 달 방향을 바라보는 거리뷰를 확인하고 있습니다.");
        this.setStatus("loading", "거리뷰를 불러오는 중입니다", "잠시만 기다려 주세요.");
        this.dom.empty.hidden = false;
        this.dom.emptyTitle.textContent = "이 위치의 거리뷰를 불러오는 중";
        this.dom.emptyDescription.textContent = "네이버 거리뷰를 달 방향으로 맞추고 있습니다.";
        this.dom.streetViewShell.hidden = true;

        try {
            await loadNaverMaps(this.naverClientId);
            if (serial !== this.autoRequestSerial) return;
            const maps = window.naver?.maps;
            if (!maps?.Panorama) throw new Error("네이버 거리뷰 모듈을 불러오지 못했습니다.");

            this.dom.streetViewShell.hidden = false;
            const size = await this.ensureStreetViewSize();
            if (serial !== this.autoRequestSerial) return;

            const latlng = new maps.LatLng(observer.lat, observer.lon);
            const pov = moonPovFromPosition(position, 70);
            const panoramaSize = new maps.Size(Math.max(size.width, 320), Math.max(size.height, 240));
            if (!this.streetView) {
                this.streetView = new maps.Panorama(this.dom.streetView, {
                    position: latlng,
                    pov,
                    size: panoramaSize,
                    visible: true,
                    logoControl: true,
                    zoomControl: true,
                    aroundControl: false,
                });
                this.bindStreetViewListeners();
            } else {
                this.streetView.setVisible(true);
                this.streetView.setSize(panoramaSize);
                this.streetView.setPosition(latlng);
                this.streetView.setPov(pov);
            }

            const status = await this.waitForStreetViewStatus(serial, observerKey, controller.signal);
            if (status !== "OK") {
                this.showNoCoverage();
                return;
            }

            this.loaded = true;
            this.streetViewObserverKey = observerKey;
            this.dom.empty.hidden = true;
            this.dom.streetViewShell.hidden = false;
            this.scheduleLookAtMoon();
            this.showLoadedInfo();
            this.startMoonTracking();
            this.onRemotePhoto?.(this.streetViewMarker(observer, position));
        } catch (error) {
            if (error.name === "AbortError" || serial !== this.autoRequestSerial) return;
            console.error(error);
            this.showLoadError(error.message);
        } finally {
            if (serial === this.autoRequestSerial) {
                this.autoRequestController = null;
                this.autoRequestCoordinateKey = "";
                this.setLoading(false);
            }
        }
    }

    showMissingKey() {
        this.hideStreetView();
        this.dom.empty.hidden = false;
        this.dom.emptyTitle.textContent = "네이버 지도 키가 없습니다";
        this.dom.emptyDescription.textContent = ".env 파일에 Client ID를 넣고 서버를 다시 실행해 주세요. 웹 서비스 URL에 localhost도 등록해야 합니다.";
        this.showInfo("error", "거리뷰를 켤 수 없습니다", "네이버 Maps Client ID가 서버에 없습니다.");
        this.setStatus("error", "네이버 지도 키가 필요합니다", "NCP 콘솔에서 웹 서비스 URL에 http://127.0.0.1:5000 을 등록했는지 확인해 주세요.");
    }

    showNoCoverage() {
        this.hideStreetView();
        this.dom.empty.hidden = false;
        this.dom.emptyTitle.textContent = "이 위치에는 거리뷰가 없습니다";
        this.dom.emptyDescription.textContent = "도로에서 조금 떨어진 좌표이거나, 네이버 거리뷰가 없는 지점입니다. 지도에서 가까운 길을 눌러 보세요.";
        this.showInfo("error", "거리뷰가 없는 지점입니다", "가까운 도로 위를 선택하면 달 방향을 볼 수 있습니다.");
        this.setStatus("error", "네이버 거리뷰가 없습니다", "도로 위 좌표를 선택해 주세요.");
        this.onRemotePhoto?.(null);
    }

    showLoadError(message) {
        this.hideStreetView();
        this.dom.empty.hidden = false;
        this.dom.emptyTitle.textContent = "거리뷰를 불러오지 못했습니다";
        this.dom.emptyDescription.textContent = "네이버 클라우드 콘솔에서 웹 서비스 URL에 http://127.0.0.1:5000 과 http://localhost:5000 이 등록됐는지 확인해 주세요.";
        this.showInfo("error", "거리뷰 연결에 실패했습니다", message || "잠시 후 다시 시도해 주세요.");
        this.setStatus("error", "거리뷰를 불러오지 못했습니다", "키와 웹 서비스 URL 등록을 확인해 주세요.");
        this.onRemotePhoto?.(null);
    }

    streetViewMarker(observer, position) {
        const location = this.streetView?.getLocation?.();
        const coord = location?.coord;
        return {
            id: "naver-streetview",
            observer_key: this.coordinateKey(observer),
            lat: typeof coord?.lat === "function" ? coord.lat() : observer.lat,
            lon: typeof coord?.lng === "function" ? coord.lng() : observer.lon,
            heading_deg: Number(position?.azimuth_deg) || 0,
            distance_m: 0,
        };
    }

    showLoadedInfo() {
        const location = this.streetView?.getLocation?.() || {};
        const title = location.title || location.address || "네이버 거리뷰";
        const captured = location.photodate || "촬영일 정보 없음";
        this.dom.previewTitle.textContent = title;
        this.showInfo("ok", title, `${captured} · © NAVER 거리뷰`);
        this.dom.streetView.setAttribute("aria-label", `네이버 거리뷰. ${title}`);
        this.updateStreetViewMoon();
    }

    clearLookAtMoonTimers() {
        this.lookAtMoonTimers?.forEach((id) => window.clearTimeout(id));
        this.lookAtMoonTimers = [];
    }

    scheduleLookAtMoon() {
        this.lookAtMoon();
        this.clearLookAtMoonTimers();
        [80, 250, 600, 1200].forEach((delay) => {
            this.lookAtMoonTimers.push(window.setTimeout(() => {
                if (!this.dom.modal.hidden && this.streetView) this.lookAtMoon();
            }, delay));
        });
    }

    lookAtMoon() {
        if (!this.streetView) return;
        const position = this.getPosition();
        if (!position) return;
        this.updatingStreetViewPov = true;
        this.streetView.setPov(moonPovFromPosition(position, this.streetView.getPov()?.fov || 70));
        this.updatingStreetViewPov = false;
        if (this.loaded) this.updateStreetViewMoon();
    }

    updateStreetViewMoon() {
        if (!this.loaded || !this.streetView || this.dom.streetViewShell.hidden) {
            this.dom.streetViewMoon.hidden = true;
            return;
        }
        const position = this.getPosition();
        const pov = this.streetView.getPov();
        if (!position || !pov) {
            this.setStatus("error", "달 위치 계산이 필요합니다", "위치와 시각을 먼저 계산해 주세요.");
            return;
        }
        const projection = projectMoonOnStreetView(
            position,
            pov,
            this.dom.streetView.clientWidth,
            this.dom.streetView.clientHeight,
        );
        const drawMoon = position.above_horizon && projection.canDraw;
        this.dom.streetViewMoon.hidden = !drawMoon;
        if (drawMoon) {
            const radius = Math.max(6, projection.radius * STREET_VIEW_MOON_SCALE);
            const canvas = this.dom.streetViewMoonCanvas;
            const size = Math.max(16, Math.round(radius * 2));
            canvas.width = size;
            canvas.height = size;
            const context = canvas.getContext("2d");
            context.clearRect(0, 0, size, size);
            this.drawMoon(context, { x: size / 2, y: size / 2, radius: size / 2 });
            this.dom.streetViewMoon.style.left = "0";
            this.dom.streetViewMoon.style.top = "0";
            this.dom.streetViewMoon.style.transform = `translate(${projection.x}px, ${projection.y}px) translate(-50%, -50%)`;
        }

        if (!position.above_horizon) {
            this.setStatus("warning", "달이 보이지 않는 시간입니다", "1시간씩 흐르게 하거나 월출 이후 시각을 선택해 주세요.");
            return;
        }
        if (projection.state === "outside") {
            this.setStatus("warning", "달이 현재 시야 밖에 있습니다", "화면을 돌리거나 '달 방향으로 맞추기'를 눌러 주세요.");
            return;
        }
        this.setStatus(
            "success",
            "거리뷰 하늘에 예상 달 위치를 표시했습니다",
            "화면을 돌리면 달은 하늘 방향에 남습니다. 건물·언덕에 가려지는지는 반영하지 않습니다.",
        );
    }

    drawMoon(context, projection) {
        const texture = this.getMoonTexture(this.getPhase());
        const size = projection.radius * 2;
        context.save();
        context.globalAlpha = 0.98;
        context.shadowColor = "rgba(255, 231, 168, 0.48)";
        context.shadowBlur = Math.max(2, projection.radius * 0.62);
        context.drawImage(texture, projection.x - projection.radius, projection.y - projection.radius, size, size);
        context.restore();
    }

    getMoonTexture(phase) {
        const angle = Number(phase?.angle_deg ?? 180);
        const cacheKey = `${Math.round(angle * 2) / 2}`;
        if (this.moonTexture && this.moonTextureKey === cacheKey) return this.moonTexture;

        const canvas = document.createElement("canvas");
        const size = 320;
        canvas.width = size;
        canvas.height = size;
        const context = canvas.getContext("2d");
        const imageData = context.createImageData(size, size);
        const data = imageData.data;
        const phaseAngle = angle * DEG_TO_RAD;
        const lightX = Math.sin(phaseAngle);
        const lightZ = -Math.cos(phaseAngle);
        const craters = [
            [-0.36, -0.27, 0.15, 0.23], [0.33, -0.38, 0.12, 0.18], [0.42, 0.16, 0.2, 0.24],
            [-0.12, 0.35, 0.17, 0.2], [-0.47, 0.43, 0.1, 0.17], [0.08, -0.05, 0.08, 0.14],
        ];

        for (let py = 0; py < size; py += 1) {
            for (let px = 0; px < size; px += 1) {
                const nx = (px + 0.5 - size / 2) / (size / 2);
                const ny = (py + 0.5 - size / 2) / (size / 2);
                const radiusSquared = nx * nx + ny * ny;
                const index = (py * size + px) * 4;
                if (radiusSquared > 1) {
                    data[index + 3] = 0;
                    continue;
                }
                const nz = Math.sqrt(Math.max(0, 1 - radiusSquared));
                const light = Math.max(0, nx * lightX + nz * lightZ);
                let albedo = 0.88 + 0.035 * Math.sin(nx * 24 + ny * 9) + 0.025 * Math.sin(ny * 33 - nx * 7);
                for (const [cx, cy, craterRadius, darkness] of craters) {
                    const distance = Math.hypot(nx - cx, ny - cy);
                    if (distance < craterRadius) {
                        const rim = distance / craterRadius;
                        albedo -= darkness * (1 - rim) + (rim > 0.78 ? -0.05 : 0);
                    }
                }
                const brightness = 0.026 + Math.pow(light, 0.72) * 0.974;
                const edgeAlpha = clamp((1 - Math.sqrt(radiusSquared)) * 42, 0, 1);
                data[index] = Math.round(244 * albedo * brightness);
                data[index + 1] = Math.round(238 * albedo * brightness);
                data[index + 2] = Math.round(211 * albedo * brightness);
                data[index + 3] = Math.round(255 * edgeAlpha);
            }
        }
        context.putImageData(imageData, 0, 0);
        this.moonTexture = canvas;
        this.moonTextureKey = cacheKey;
        return canvas;
    }

    scheduleRender() {
        if (this.renderFrame) return;
        this.renderFrame = window.requestAnimationFrame(() => {
            this.renderFrame = null;
            this.updateStreetViewMoon();
        });
    }

    sync() {
        const observer = this.getObserver();
        const position = this.getPosition();
        this.dom.observerMeta.textContent = observer
            ? `위도 ${Number(observer.lat).toFixed(4)} · 경도 ${Number(observer.lon).toFixed(4)}`
            : "위치 계산 전";
        this.dom.moonMeta.textContent = position
            ? `${position.direction} ${Number(position.azimuth_deg).toFixed(1)}° · 고도 ${Number(position.altitude_deg).toFixed(1)}°`
            : "방위각과 고도 계산 전";
        this.dom.timeMeta.textContent = position?.time ? this.timeFromIso(position.time) : "--:--";
        this.scheduleRender();

        const observerKey = this.coordinateKey(observer);
        if (this.autoRequestController && observerKey !== this.autoRequestCoordinateKey) this.cancelLoad();
        if (this.loaded && this.streetViewObserverKey === observerKey) {
            this.updateStreetViewMoon();
            if (!this.dom.modal.hidden) {
                this.lookAtMoon();
                this.onRemotePhoto?.(this.streetViewMarker(observer, position));
            }
        }
        if (!this.dom.modal.hidden && observerKey && observerKey !== this.lastObserverKey) {
            this.lastObserverKey = observerKey;
            this.loadStreetView();
        } else if (!this.dom.modal.hidden && observerKey && !this.loaded && !this.autoRequestController) {
            this.loadStreetView();
        }
    }

    timeFromIso(value) {
        const match = String(value || "").match(/T(\d{2}):(\d{2})/);
        return match ? `${match[1]}:${match[2]}` : "--:--";
    }

    showEveningView(showEvening) {
        const hasResult = Boolean(this.dom.eveningImage?.getAttribute("src"));
        if (showEvening && !hasResult) return;
        if (this.dom.streetViewShell) this.dom.streetViewShell.hidden = showEvening;
        if (this.dom.eveningResult) this.dom.eveningResult.hidden = !showEvening;
        this.dom.eveningToggle?.querySelectorAll("button").forEach((button) => {
            button.classList.toggle("is-active", button.dataset.view === (showEvening ? "evening" : "street"));
        });
        if (showEvening) this.stopMoonTracking();
        else if (this.loaded && !this.dom.modal.hidden) this.startMoonTracking();
    }

    canvasToJpeg(canvas, quality = 0.92) {
        const maxWidth = 1600;
        let { width, height } = canvas;
        if (!width || !height) return "";
        if (width > maxWidth) {
            height = Math.round((height * maxWidth) / width);
            width = maxWidth;
        }
        const out = document.createElement("canvas");
        out.width = width;
        out.height = height;
        const context = out.getContext("2d");
        context.drawImage(canvas, 0, 0, width, height);
        try {
            return out.toDataURL("image/jpeg", quality);
        } catch {
            throw new Error("화면을 이미지로 담을 수 없습니다. 거리뷰가 완전히 뜬 뒤 다시 시도해 주세요.");
        }
    }

    waitFrames(count = 2) {
        return new Promise((resolve) => {
            const tick = () => {
                if (count <= 1) {
                    resolve();
                    return;
                }
                count -= 1;
                window.requestAnimationFrame(tick);
            };
            window.requestAnimationFrame(tick);
        });
    }

    moonPlacement() {
        const position = this.getPosition();
        const pov = this.streetView?.getPov?.();
        const view = this.dom.streetView;
        const shell = this.dom.streetViewShell;
        const width = Math.max(1, view?.clientWidth || shell?.clientWidth || 1);
        const height = Math.max(1, view?.clientHeight || shell?.clientHeight || 1);
        if (!position || !pov) {
            return { width, height, in_view: false, x_percent: null, y_percent: null };
        }
        const projection = projectMoonOnStreetView(position, pov, width, height);
        return {
            width: projection.width,
            height: projection.height,
            in_view: Boolean(position.above_horizon && projection.canDraw),
            x_percent: (projection.x / projection.width) * 100,
            y_percent: (projection.y / projection.height) * 100,
        };
    }

    async captureVisibleStreetView() {
        const shell = this.dom.streetViewShell;
        const view = this.dom.streetView;
        if (!shell || shell.hidden || !view) throw new Error("거리뷰가 열린 뒤 다시 눌러 주세요.");
        if (!window.html2canvas) throw new Error("화면 캡처 모듈을 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요.");

        await this.waitFrames(3);
        const viewRect = view.getBoundingClientRect();
        const captured = await window.html2canvas(view, {
            backgroundColor: "#07110f",
            useCORS: true,
            allowTaint: false,
            logging: false,
            scale: Math.min(2, window.devicePixelRatio || 1),
        });
        const moon = this.dom.streetViewMoon;
        const moonCanvas = this.dom.streetViewMoonCanvas;
        if (moon && moonCanvas && !moon.hidden && viewRect.width > 0 && viewRect.height > 0) {
            const moonRect = moonCanvas.getBoundingClientRect();
            const scaleX = captured.width / viewRect.width;
            const scaleY = captured.height / viewRect.height;
            captured.getContext("2d").drawImage(
                moonCanvas,
                (moonRect.left - viewRect.left) * scaleX,
                (moonRect.top - viewRect.top) * scaleY,
                moonRect.width * scaleX,
                moonRect.height * scaleY,
            );
        }
        const dataUrl = this.canvasToJpeg(captured);
        if (!dataUrl || dataUrl.length < 800) throw new Error("거리뷰 화면을 담지 못했습니다.");
        return { image: dataUrl, width: captured.width, height: captured.height };
    }

    setEveningProgress(title, detail) {
        this.eveningProgressDetail = detail;
        const seconds = this.eveningStartedAt
            ? Math.max(0, Math.round((Date.now() - this.eveningStartedAt) / 1000))
            : 0;
        const timed = seconds > 0 ? `${seconds}초 경과 · ${detail}` : detail;
        if (this.dom.eveningProgressTitle) this.dom.eveningProgressTitle.textContent = title;
        if (this.dom.eveningProgressMeta) this.dom.eveningProgressMeta.textContent = timed;
        this.showInfo("loading", title, timed);
        this.setStatus("loading", title, timed);
    }

    setEveningLoading(loading) {
        this.eveningBusy = loading;
        if (this.dom.eveningButton) {
            this.dom.eveningButton.disabled = loading;
            this.dom.eveningButton.textContent = loading ? "밤 장면 만드는 중" : "밤 장면 만들기";
        }
        if (this.dom.eveningProgress) this.dom.eveningProgress.hidden = !loading;
        if (this.eveningTimer) {
            window.clearInterval(this.eveningTimer);
            this.eveningTimer = null;
        }
        if (!loading) {
            this.eveningStartedAt = 0;
            return;
        }
        this.eveningStartedAt = Date.now();
        this.setEveningProgress(
            "밤 장면을 만들고 있습니다",
            "화면을 담은 뒤 하늘을 밤으로 바꿉니다. 보통 20~60초 걸립니다.",
        );
        this.eveningTimer = window.setInterval(() => {
            if (!this.eveningBusy) return;
            this.setEveningProgress(
                this.dom.eveningProgressTitle?.textContent || "밤 장면을 만들고 있습니다",
                this.eveningProgressDetail || "보통 20~60초 걸립니다.",
            );
        }, 1000);
    }

    async saveEveningImage() {
        const source = this.dom.eveningImage?.getAttribute("src");
        if (!source) {
            this.showToast("먼저 밤 장면을 만들어 주세요.", true);
            return;
        }
        try {
            const response = await fetch(source);
            const blob = await response.blob();
            const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `밤장면-${stamp}.jpg`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(url), 1500);
            this.showToast("이미지를 저장했습니다.");
        } catch (error) {
            this.showToast("이미지를 저장하지 못했습니다. 길게 눌러 저장해 보세요.", true);
        }
    }

    async generateEveningScene() {
        if (this.eveningBusy) return;
        if (!this.eveningEnabled) {
            this.showToast("GEMINI_API_KEY를 .env에 넣고 서버를 다시 실행해 주세요.", true);
            return;
        }
        if (!this.loaded) {
            this.showToast("거리뷰가 열린 뒤 밤 장면을 만들 수 있습니다.", true);
            return;
        }
        const observer = this.getObserver();
        const position = this.getPosition();
        if (!observer || !position) {
            this.showToast("달 위치 계산이 끝난 뒤 다시 눌러 주세요.", true);
            return;
        }

        this.setEveningLoading(true);
        try {
            this.showEveningView(false);
            this.setEveningProgress("지금 화면을 담고 있습니다", "브라우저에 보이는 거리뷰 영역만 잘라 담습니다.");
            const screenshot = await this.captureVisibleStreetView();
            this.setEveningProgress("밤하늘을 그리고 있습니다", "실제 달 크기와 달빛으로 밤을 만듭니다. 보통 20~60초 걸립니다.");
            const location = this.streetView?.getLocation?.() || {};
            const pov = this.streetView?.getPov?.() || {};
            const moon = this.moonPlacement();
            const response = await fetch("/api/evening-scene", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    lat: observer.lat,
                    lon: observer.lon,
                    elevation: observer.elevation_m || 0,
                    datetime: String(position.time || "").slice(0, 16),
                    timezone: observer.timezone,
                    place_name: location.title || location.address || "",
                    view_heading_deg: pov.pan,
                    image: screenshot.image,
                    image_width: screenshot.width,
                    image_height: screenshot.height,
                    moon_x_percent: moon?.x_percent,
                    moon_y_percent: moon?.y_percent,
                    moon_in_view: moon?.in_view,
                    view_fov_deg: pov.fov,
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "밤 장면을 만들지 못했습니다.");

            this.setEveningProgress("완성한 이미지를 불러오는 중입니다", "잠시만 기다려 주세요.");
            this.dom.eveningImage.src = `data:${result.mime_type || "image/jpeg"};base64,${result.image}`;
            this.dom.eveningCaption.textContent = result.notice || "지금 보이는 화면을 바탕으로 만든 예상 밤 장면입니다.";
            try {
                if (this.dom.eveningImage.decode) await this.dom.eveningImage.decode();
            } catch {
                /* already loaded */
            }
            if (this.dom.eveningToggle) this.dom.eveningToggle.hidden = false;
            this.showEveningView(true);
            this.setEveningLoading(false);
            this.showInfo("success", "예상 밤 장면을 만들었습니다", "위 버튼으로 거리뷰와 비교하거나 이미지를 저장할 수 있습니다.");
            this.setStatus("success", "예상 밤 장면을 만들었습니다", "거리뷰와 비교하거나 이미지를 저장할 수 있습니다.");
            this.showToast("밤 장면이 완성되었습니다.");
        } catch (error) {
            this.setEveningLoading(false);
            this.showInfo("error", "밤 장면을 만들지 못했습니다", error.message);
            this.setStatus("error", "밤 장면을 만들지 못했습니다", error.message);
            this.showToast(error.message, true);
        }
    }
}
