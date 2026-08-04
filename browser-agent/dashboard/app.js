document.addEventListener("DOMContentLoaded", () => {
    const wsStatus = document.getElementById("wsStatus");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");

    const templateSelect = document.getElementById("templateSelect");
    const agentForm = document.getElementById("agentForm");
    const targetUrlInput = document.getElementById("targetUrl");
    const goalInput = document.getElementById("goal");
    const resolutionSelect = document.getElementById("resolution");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");

    const activeModelPill = document.getElementById("activeModelPill");
    const latencyVal = document.getElementById("latencyVal");
    const metricCoordsVal = document.getElementById("metricCoordsVal");
    const successRateVal = document.getElementById("successRateVal");
    const streamFpsVal = document.getElementById("streamFpsVal");

    const taskIdVal = document.getElementById("taskIdVal");
    const taskStateBadge = document.getElementById("taskStateBadge");
    const stepsVal = document.getElementById("stepsVal");

    const previewContainer = document.getElementById("previewContainer");
    const previewPlaceholder = document.getElementById("previewPlaceholder");
    const livePreviewImg = document.getElementById("livePreviewImg");
    const previewPageUrl = document.getElementById("previewPageUrl");
    const targetOverlayMarker = document.getElementById("targetOverlayMarker");
    const markerLabel = document.getElementById("markerLabel");

    const logFeed = document.getElementById("logFeed");
    const clearLogsBtn = document.getElementById("clearLogsBtn");

    let ws = null;
    let currentTaskId = null;
    let stepCounter = 0;
    let activeWidth = 1280;
    let activeHeight = 800;

    let successfulSteps = 0;
    let totalStepsRecorded = 0;
    let lastStepTimestamp = null;

    let frameCount = 0;
    let lastFpsReset = Date.now();

    // Template Selector presets
    templateSelect.addEventListener("change", () => {
        const val = templateSelect.value;
        if (val === "login") {
            targetUrlInput.value = "https://the-internet.herokuapp.com/login";
            goalInput.value = "Type 'tomsmith' into Username field, 'SuperSecretPassword!' into Password field, and click Login button";
        } else if (val === "canvas") {
            targetUrlInput.value = "file:///c:/Users/zain/OneDrive/Desktop/Al Agent Browser Extension/browser-agent/tests/canvas_test.html";
            goalInput.value = "Click the canvas button visually labeled 'CLICK ME TO WIN - TARGET'";
        } else if (val === "books") {
            targetUrlInput.value = "https://books.toscrape.com";
            goalInput.value = "Navigate to Travel category and select the first book";
        }
    });

    // Connect to WebSocket Server
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsHost = window.location.host || "localhost:8000";
        const wsUrl = `${wsProtocol}//${wsHost}/ws/telemetry`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            statusDot.className = "status-dot connected";
            statusText.textContent = "Connected";
            console.log("WebSocket connected to visual telemetry server.");
        };

        ws.onclose = () => {
            statusDot.className = "status-dot disconnected";
            statusText.textContent = "Disconnected";
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (err) => {
            console.error("WebSocket error:", err);
        };

        ws.onmessage = (event) => {
            try {
                const frame = JSON.parse(event.data);
                handleTelemetryFrame(frame);
            } catch (e) {
                console.error("Failed to parse telemetry frame:", e);
            }
        };
    }

    connectWebSocket();

    // Stream FPS Counter Loop
    setInterval(() => {
        const now = Date.now();
        const elapsedSec = (now - lastFpsReset) / 1000.0;
        const fps = Math.round(frameCount / elapsedSec);
        streamFpsVal.textContent = `${fps} FPS`;
        frameCount = 0;
        lastFpsReset = now;
    }, 1000);

    // Form submission handler
    agentForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const resParts = resolutionSelect.value.split("x");
        activeWidth = parseInt(resParts[0], 10);
        activeHeight = parseInt(resParts[1], 10);

        const payload = {
            url: targetUrlInput.value.trim(),
            goal: goalInput.value.trim(),
            max_steps: parseInt(maxStepsInput.value, 10),
            width: activeWidth,
            height: activeHeight,
            mode: "hybrid"
        };

        startBtn.disabled = true;
        stopBtn.disabled = false;
        startBtn.innerHTML = "<span>⏳ Running...</span>";

        successfulSteps = 0;
        totalStepsRecorded = 0;
        lastStepTimestamp = Date.now();

        try {
            const apiHost = window.location.origin.includes("http") ? window.location.origin : "http://localhost:8000";
            const response = await fetch(`${apiHost}/api/agent/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }

            const data = await response.json();
            currentTaskId = data.task_id;
            stepCounter = 0;

            taskIdVal.textContent = currentTaskId;
            taskStateBadge.className = "badge badge-info";
            taskStateBadge.textContent = "Running";
            stepsVal.textContent = `0 / ${payload.max_steps}`;

            metricCoordsVal.textContent = "(0, 0)";
            latencyVal.textContent = "0.0s";
            successRateVal.textContent = "100%";

            logFeed.innerHTML = "";

        } catch (err) {
            alert(`Error launching agent: ${err.message}`);
            startBtn.disabled = false;
            stopBtn.disabled = true;
            startBtn.innerHTML = "<span>▶ Launch Task</span>";
        }
    });

    // Stop task handler
    stopBtn.addEventListener("click", async () => {
        if (!currentTaskId) return;

        try {
            const apiHost = window.location.origin.includes("http") ? window.location.origin : "http://localhost:8000";
            await fetch(`${apiHost}/api/agent/stop/${currentTaskId}`, { method: "POST" });
            taskStateBadge.className = "badge badge-warning";
            taskStateBadge.textContent = "Cancelled";
        } catch (err) {
            console.error("Error stopping task:", err);
        } finally {
            startBtn.disabled = false;
            stopBtn.disabled = true;
            startBtn.innerHTML = "<span>▶ Launch Task</span>";
        }
    });

    // Clear logs handler
    clearLogsBtn.addEventListener("click", () => {
        logFeed.innerHTML = '<div class="empty-feed-msg">No step telemetry events recorded yet.</div>';
    });

    // Position Crosshair Target Overlay on Screenshot
    function updateCoordinateOverlay(x, y) {
        if (x === null || x === undefined || y === null || y === undefined) {
            targetOverlayMarker.style.display = "none";
            metricCoordsVal.textContent = "None";
            return;
        }

        metricCoordsVal.textContent = `(${x}, ${y})`;
        markerLabel.textContent = `(${x}, ${y})`;

        const imgRect = livePreviewImg.getBoundingClientRect();
        const containerRect = previewContainer.getBoundingClientRect();

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

    // Telemetry frame handler
    function handleTelemetryFrame(frame) {
        if (!frame) return;

        frameCount++;
        const now = Date.now();
        if (lastStepTimestamp) {
            const deltaSec = ((now - lastStepTimestamp) / 1000.0).toFixed(1);
            latencyVal.textContent = `${deltaSec}s`;
        }
        lastStepTimestamp = now;

        stepCounter = frame.step_num || (stepCounter + 1);
        stepsVal.textContent = `${stepCounter} Steps`;

        totalStepsRecorded++;
        if (frame.success !== false) {
            successfulSteps++;
        }
        const ratePct = Math.round((successfulSteps / totalStepsRecorded) * 100);
        successRateVal.textContent = `${ratePct}%`;

        if (frame.page_url) {
            previewPageUrl.textContent = `URL: ${frame.page_url}`;
        }

        if (frame.used_vision) {
            activeModelPill.textContent = "qwen3.6-27b";
        } else {
            activeModelPill.textContent = "llama-3.1-8b";
        }

        if (frame.screenshot_base64) {
            previewPlaceholder.style.display = "none";
            livePreviewImg.style.display = "block";
            livePreviewImg.src = frame.screenshot_base64;
            setTimeout(() => {
                updateCoordinateOverlay(frame.x, frame.y);
            }, 80);
        }

        const emptyMsg = logFeed.querySelector(".empty-feed-msg");
        if (emptyMsg) {
            emptyMsg.remove();
        }

        const card = document.createElement("div");
        card.className = "log-card";

        const coordsStr = (frame.x !== null && frame.x !== undefined) ? ` (${frame.x}, ${frame.y})` : "";
        const selectorStr = frame.selector ? ` | Locator: ${frame.selector}` : "";

        card.innerHTML = `
            <div class="log-card-header">
                <span class="log-step-title">STEP ${frame.step_num}: ${frame.action.toUpperCase()}${coordsStr}</span>
                <span class="badge badge-vision">👁️ Pure Visual</span>
            </div>
            <div class="log-reasoning">💡 ${frame.thought || frame.reasoning || "Executing physical visual action..."}</div>
            <div class="log-meta-row">
                <span>Status: ${frame.success !== false ? "✅ Success" : "❌ Failed"}</span>
                <span>${selectorStr}</span>
            </div>
        `;

        logFeed.prepend(card);

        if (frame.action === "done") {
            taskStateBadge.className = "badge badge-success";
            taskStateBadge.textContent = "Completed";
            startBtn.disabled = false;
            stopBtn.disabled = true;
            startBtn.innerHTML = "<span>▶ Launch Task</span>";
        }
    }
});
