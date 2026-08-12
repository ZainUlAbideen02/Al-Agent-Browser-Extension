document.addEventListener("DOMContentLoaded", () => {
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const targetUrlInput = document.getElementById("targetUrl");
    const goalInput = document.getElementById("goal");
    const resolutionSelect = document.getElementById("resolution");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");

    const streamContainer = document.getElementById("streamContainer");
    const placeholderText = document.getElementById("placeholderText");
    const streamImg = document.getElementById("streamImg");
    const targetOverlayMarker = document.getElementById("targetOverlayMarker");
    const markerLabel = document.getElementById("markerLabel");
    const logContainer = document.getElementById("logContainer");

    let ws = null;
    let activeWidth = 1280;
    let activeHeight = 800;
    let wsEndpoints = ["ws://localhost:8000/ws/telemetry", "ws://127.0.0.1:8000/ws/telemetry"];
    let currentEndpointIndex = 0;
    let reconnectTimeout = null;

    // Auto-detect current active tab URL in Chrome Extension environment
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.query) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs && tabs[0] && tabs[0].url) {
                targetUrlInput.value = tabs[0].url;
            }
        });
    }

    function setStatus(connected, message) {
        if (connected) {
            statusDot.className = "status-dot connected";
            statusDot.style.background = "#22c55e";
            statusText.textContent = message || "Connected";
        } else {
            statusDot.className = "status-dot disconnected";
            statusDot.style.background = "#ef4444";
            statusText.textContent = message || "Disconnected";
        }
    }

    function connectWebSocket() {
        if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
            return;
        }

        const endpoint = wsEndpoints[currentEndpointIndex];
        try {
            ws = new WebSocket(endpoint);
        } catch (err) {
            console.warn(`WebSocket creation failed for ${endpoint}:`, err);
            setStatus(false, "Disconnected");
            switchEndpointAndRetry();
            return;
        }

        ws.onopen = () => {
            console.log(`WebSocket connected to ${endpoint}`);
            setStatus(true, "Connected");
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
                reconnectTimeout = null;
            }
        };

        ws.onclose = () => {
            setStatus(false, "Disconnected");
            switchEndpointAndRetry();
        };

        ws.onerror = (e) => {
            console.warn(`WebSocket connection error on ${endpoint}:`, e);
            setStatus(false, "Disconnected");
        };

        ws.onmessage = (event) => {
            try {
                const frame = JSON.parse(event.data);
                renderFrame(frame);
            } catch (err) {
                console.error("Error parsing telemetry frame:", err);
            }
        };
    }

    function switchEndpointAndRetry() {
        if (reconnectTimeout) return;
        currentEndpointIndex = (currentEndpointIndex + 1) % wsEndpoints.length;
        reconnectTimeout = setTimeout(() => {
            reconnectTimeout = null;
            connectWebSocket();
        }, 3000);
    }

    connectWebSocket();

    startBtn.addEventListener("click", async () => {
        const resParts = resolutionSelect.value.split("x");
        activeWidth = parseInt(resParts[0], 10);
        activeHeight = parseInt(resParts[1], 10);

        const targetUrl = targetUrlInput.value.trim() || "https://the-internet.herokuapp.com/login";

        const payload = {
            url: targetUrl,
            goal: goalInput.value.trim(),
            max_steps: parseInt(maxStepsInput.value, 10),
            width: activeWidth,
            height: activeHeight,
            mode: "hybrid"
        };

        startBtn.disabled = true;
        startBtn.textContent = "⏳ Running...";

        try {
            const apiEndpoints = ["http://localhost:8000/api/agent/start", "http://127.0.0.1:8000/api/agent/start"];
            let response = null;
            let lastErr = null;

            for (const ep of apiEndpoints) {
                try {
                    response = await fetch(ep, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });
                    if (response && response.ok) break;
                } catch (e) {
                    lastErr = e;
                }
            }

            if (!response || !response.ok) throw new Error(lastErr ? lastErr.message : `HTTP ${response ? response.status : 'error'}`);
            logContainer.innerHTML = "";

        } catch (err) {
            alert(`Could not trigger agent: ${err.message}. Make sure server.py is running on localhost:8000.`);
            startBtn.disabled = false;
            startBtn.textContent = "▶ Run Visual Agent";
        }
    });

    function updateCoordinateOverlay(x, y) {
        if (x === null || x === undefined || y === null || y === undefined) {
            targetOverlayMarker.style.display = "none";
            return;
        }

        markerLabel.textContent = `(${x}, ${y})`;

        const imgRect = streamImg.getBoundingClientRect();
        const containerRect = streamContainer.getBoundingClientRect();

        const scaleX = imgRect.width / activeWidth;
        const scaleY = imgRect.height / activeHeight;

        const imgLeftRelativeToContainer = imgRect.left - containerRect.left;
        const imgTopRelativeToContainer = imgRect.top - containerRect.top;

        const posX = imgLeftRelativeToContainer + (x * scaleX);
        const posY = imgTopRelativeToContainer + (y * scaleY);

        targetOverlayMarker.style.left = `${posX}px`;
        targetOverlayMarker.style.top = `${posY}px`;
        targetOverlayMarker.style.display = "block";
    }

    function renderFrame(frame) {
        if (!frame) return;

        // 1. Handle live screenshot stream
        if (frame.screenshot_base64) {
            if (placeholderText) placeholderText.style.display = "none";
            if (streamImg) {
                streamImg.style.display = "block";
                streamImg.src = frame.screenshot_base64.startsWith("data:") 
                    ? frame.screenshot_base64 
                    : `data:image/png;base64,${frame.screenshot_base64}`;
            }
        }

        // 2. Handle crosshair coordinate marker
        if (frame.x !== undefined && frame.x !== null && frame.y !== undefined && frame.y !== null) {
            if (targetOverlayMarker) {
                targetOverlayMarker.style.display = "flex";
                // Map relative coordinates if resolution metadata is present
                const rescaleX = (frame.x / activeWidth) * 100;
                const rescaleY = (frame.y / activeHeight) * 100;
                targetOverlayMarker.style.left = `${rescaleX}%`;
                targetOverlayMarker.style.top = `${rescaleY}%`;
            }
            if (markerLabel) {
                const actionText = (frame.action || "TARGET").toString().toUpperCase();
                markerLabel.textContent = `${actionText} (${frame.x}, ${frame.y})`;
            }
        }

        // 3. Handle step logging (Safe Null-Check on .toUpperCase())
        if (frame.step_num || frame.thought || frame.action) {
            if (logContainer.querySelector("div[style*='text-align:center']")) {
                logContainer.innerHTML = "";
            }
            const logItem = document.createElement("div");
            logItem.className = "log-item";
            
            // SAFE .toUpperCase() EVALUATION:
            const safeAction = (frame.action || "INFO").toString().toUpperCase();
            const safeMode = (frame.mode || "VISUAL").toString().toUpperCase();
            const safeThought = frame.thought || frame.message || frame.reasoning || "Executing action...";

            logItem.innerHTML = `
                <div class="log-item-header">
                    <span>STEP ${frame.step_num || '-'}: ${safeAction}</span>
                    <span class="badge badge-vision">${safeMode}</span>
                </div>
                <div style="color:var(--text-primary); font-size:11px;">💡 ${safeThought}</div>
            `;
            
            if (logContainer) {
                logContainer.prepend(logItem);
            }
        }

        // 4. Reset Start Button on Task Done / Failed
        if (frame.action === "done" || frame.status === "completed" || frame.status === "failed") {
            if (startBtn) {
                startBtn.disabled = false;
                startBtn.textContent = "▶ Run Visual Agent";
            }
        }
    }
});
