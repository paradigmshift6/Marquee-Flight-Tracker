/**
 * LED Matrix Simulator
 *
 * Fetches the rendered 64x64 PNG from /api/frame every second,
 * reads each pixel, and draws it as a rounded LED dot on a larger canvas.
 */
(function () {
    "use strict";

    // ── Configuration ───────────────────────────────────
    let PIXEL_SIZE = 8;       // screen pixels per LED pixel
    const PIXEL_GAP = 1;      // gap between LED dots
    const PIXEL_RADIUS = 1.5; // corner radius for rounded LED dots
    const DIM_BRIGHTNESS = 18; // "off" LED dim glow (0-255)
    const REFRESH_MS = 1000;   // poll interval

    let matrixW = 64;
    let matrixH = 64;
    let running = true;

    // ── DOM refs ────────────────────────────────────────
    const ledCanvas = document.getElementById("led-canvas");
    const srcCanvas = document.getElementById("source-canvas");
    const statusEl = document.getElementById("status");
    const infoEl = document.getElementById("info");
    const dotEl = document.querySelector(".dot");

    const ctx = ledCanvas.getContext("2d");
    const srcCtx = srcCanvas.getContext("2d");

    // ── Fetch matrix config ─────────────────────────────
    async function fetchConfig() {
        try {
            const resp = await fetch("/api/frame/config");
            if (resp.ok) {
                const cfg = await resp.json();
                matrixW = cfg.width || 64;
                matrixH = cfg.height || 64;
            }
        } catch (e) {
            // use defaults
        }
        resizeCanvas();
    }

    // ── Canvas sizing ───────────────────────────────────
    function resizeCanvas() {
        const canvasW = matrixW * PIXEL_SIZE;
        const canvasH = matrixH * PIXEL_SIZE;
        ledCanvas.width = canvasW;
        ledCanvas.height = canvasH;
        srcCanvas.width = matrixW;
        srcCanvas.height = matrixH;
        infoEl.textContent = `${matrixW}×${matrixH} • ${PIXEL_SIZE}x zoom`;
    }

    // ── Draw one frame ──────────────────────────────────
    function drawFrame(imageData) {
        const data = imageData.data;  // Uint8ClampedArray [r,g,b,a, ...]

        // Clear to dark background
        ctx.fillStyle = "#0a0a0a";
        ctx.fillRect(0, 0, ledCanvas.width, ledCanvas.height);

        for (let y = 0; y < matrixH; y++) {
            for (let x = 0; x < matrixW; x++) {
                const idx = (y * matrixW + x) * 4;
                let r = data[idx];
                let g = data[idx + 1];
                let b = data[idx + 2];

                // If pixel is basically black, draw a dim "off" dot
                const brightness = Math.max(r, g, b);
                if (brightness < 5) {
                    r = DIM_BRIGHTNESS;
                    g = DIM_BRIGHTNESS;
                    b = DIM_BRIGHTNESS;
                }

                const px = x * PIXEL_SIZE + PIXEL_GAP;
                const py = y * PIXEL_SIZE + PIXEL_GAP;
                const size = PIXEL_SIZE - PIXEL_GAP * 2;

                ctx.fillStyle = `rgb(${r},${g},${b})`;
                ctx.beginPath();
                ctx.roundRect(px, py, size, size, PIXEL_RADIUS);
                ctx.fill();
            }
        }
    }

    // ── Fetch loop ──────────────────────────────────────
    let frameCount = 0;
    let lastFps = 0;
    let fpsTimer = Date.now();

    async function fetchFrame() {
        if (!running) return;

        try {
            const resp = await fetch("/api/frame?" + Date.now());
            if (!resp.ok) {
                setError("frame " + resp.status);
                return;
            }

            const blob = await resp.blob();
            const bmp = await createImageBitmap(blob);

            // Draw to hidden source canvas to read pixel data
            srcCtx.clearRect(0, 0, matrixW, matrixH);
            srcCtx.drawImage(bmp, 0, 0, matrixW, matrixH);
            const imageData = srcCtx.getImageData(0, 0, matrixW, matrixH);

            drawFrame(imageData);

            frameCount++;
            const now = Date.now();
            if (now - fpsTimer >= 2000) {
                lastFps = Math.round(frameCount / ((now - fpsTimer) / 1000) * 10) / 10;
                infoEl.textContent = `${matrixW}×${matrixH} • ${PIXEL_SIZE}x • ${lastFps} fps`;
                frameCount = 0;
                fpsTimer = now;
            }

            setOk();
        } catch (e) {
            setError(e.message || "fetch error");
        }
    }

    function setOk() {
        statusEl.textContent = "live";
        dotEl.classList.remove("error");
    }

    function setError(msg) {
        statusEl.textContent = msg;
        dotEl.classList.add("error");
    }

    // ── Zoom controls ───────────────────────────────────
    document.getElementById("btn-zoom-in").addEventListener("click", () => {
        PIXEL_SIZE = Math.min(PIXEL_SIZE + 2, 20);
        resizeCanvas();
    });

    document.getElementById("btn-zoom-out").addEventListener("click", () => {
        PIXEL_SIZE = Math.max(PIXEL_SIZE - 2, 4);
        resizeCanvas();
    });

    // ── Mock data injection ─────────────────────────────
    document.getElementById("btn-mock").addEventListener("click", async () => {
        try {
            const resp = await fetch("/api/mock", { method: "POST" });
            if (resp.ok) {
                statusEl.textContent = "mock injected";
            }
        } catch (e) {
            // Mock endpoint may not exist — that's fine
            statusEl.textContent = "mock N/A";
        }
    });

    // ── Init ────────────────────────────────────────────
    fetchConfig().then(() => {
        setInterval(fetchFrame, REFRESH_MS);
        fetchFrame();
    });
})();
