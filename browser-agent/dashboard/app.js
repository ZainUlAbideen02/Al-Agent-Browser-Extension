document.addEventListener("DOMContentLoaded", () => {
    const wsStatus = document.getElementById("wsStatus");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");

    const agentForm = document.getElementById("agentForm");
    const targetUrlInput = document.getElementById("targetUrl");
    const goalInput = document.getElementById("goal");
    const resolutionSelect = document.getElementById("resolution");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");

    const taskIdVal = document.getElementById("taskIdVal");
    const taskStateBadge = document.getElementById("taskStateBadge");
    const stepsVal = document.getElementById("stepsVal");
    const coordsVal = document.getElementById("coordsVal");

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
            coordsVal.textContent = "None";

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

    // Position Coordinate Overlay Marker on Screenshot
    function updateCoordinateOverlay(x, y) {
        if (x === null || x === undefined || y === null || y === undefined) {
            targetOverlayMarker.style.display = "none";
            return;
        }

        coordsVal.textContent = `(${x}, ${y})`;
        markerLabel.textContent = `(${x}, ${y})`;

        // Calculate scaled position relative to rendered screenshot image element
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

        stepCounter = frame.step_num || (stepCounter + 1);
        stepsVal.textContent = `${stepCounter} Steps`;

        if (frame.page_url) {
            previewPageUrl.textContent = `URL: ${frame.page_url}`;
        }

        if (frame.screenshot_base64) {
            previewPlaceholder.style.display = "none";
            livePreviewImg.style.display = "block";
            livePreviewImg.src = frame.screenshot_base64;
            // Update marker overlay position after image loads
            setTimeout(() => {
                updateCoordinateOverlay(frame.x, frame.y);
            }, 100);
        }

        // Remove empty feed message
        const emptyMsg = logFeed.querySelector(".empty-feed-msg");
        if (emptyMsg) {
            emptyMsg.remove();
        }

        // Render Log Card
        const card = document.createElement("div");
        card.className = "log-card";

        const coordsStr = (frame.x !== null && frame.x !== undefined) ? ` (${frame.x}, ${frame.y})` : "";
        const selectorStr = frame.selector ? ` | Locator: ${frame.selector}` : "";

        card.innerHTML = `
            <div class="log-card-header">
                <span class="log-step-title">STEP ${frame.step_num}: ${frame.action.toUpperCase()}${coordsStr}</span>
                <span class="badge badge-vision">👁️ Visual Agent</span>
            </div>
            <div class="log-reasoning">💡 ${frame.thought || frame.reasoning || "Executing physical visual action..."}</div>
            <div class="log-meta-row">
                <span>Status: ${frame.success ? "✅ Success" : "❌ Failed"}</span>
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
