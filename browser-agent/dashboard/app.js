document.addEventListener("DOMContentLoaded", () => {
    const wsStatus = document.getElementById("wsStatus");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");

    const agentForm = document.getElementById("agentForm");
    const targetUrlInput = document.getElementById("targetUrl");
    const goalInput = document.getElementById("goal");
    const modeSelect = document.getElementById("mode");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");

    const taskIdVal = document.getElementById("taskIdVal");
    const taskStateBadge = document.getElementById("taskStateBadge");
    const stepsVal = document.getElementById("stepsVal");
    const visionCountVal = document.getElementById("visionCountVal");

    const previewPlaceholder = document.getElementById("previewPlaceholder");
    const livePreviewImg = document.getElementById("livePreviewImg");
    const previewPageUrl = document.getElementById("previewPageUrl");
    const visionModeBadge = document.getElementById("visionModeBadge");

    const logFeed = document.getElementById("logFeed");
    const clearLogsBtn = document.getElementById("clearLogsBtn");

    let ws = null;
    let currentTaskId = null;
    let stepCounter = 0;
    let visionFallbackCounter = 0;

    // Connect to WebSocket Server
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsHost = window.location.host || "localhost:8000";
        const wsUrl = `${wsProtocol}//${wsHost}/ws/telemetry`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            statusDot.className = "status-dot connected";
            statusText.textContent = "Connected";
            console.log("WebSocket connected to telemetry server.");
        };

        ws.onclose = () => {
            statusDot.className = "status-dot disconnected";
            statusText.textContent = "Disconnected";
            console.log("WebSocket disconnected. Retrying in 3s...");
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

        const payload = {
            url: targetUrlInput.value.trim(),
            goal: goalInput.value.trim(),
            mode: modeSelect.value,
            max_steps: parseInt(maxStepsInput.value, 10)
        };

        startBtn.disabled = true;
        startBtn.innerHTML = "<span>⏳ Launching Agent...</span>";

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
            visionFallbackCounter = 0;

            taskIdVal.textContent = currentTaskId;
            taskStateBadge.className = "badge badge-info";
            taskStateBadge.textContent = "Running";
            stepsVal.textContent = `0 / ${payload.max_steps}`;
            visionCountVal.textContent = "0";

            logFeed.innerHTML = "";

        } catch (err) {
            alert(`Error starting agent: ${err.message}`);
        } finally {
            startBtn.disabled = false;
            startBtn.innerHTML = "<span>▶ Start Autonomous Agent</span>";
        }
    });

    // Clear logs handler
    clearLogsBtn.addEventListener("click", () => {
        logFeed.innerHTML = '<div class="empty-feed-msg">No step telemetry events recorded yet.</div>';
    });

    // Telemetry frame handler
    function handleTelemetryFrame(frame) {
        if (!frame) return;

        stepCounter = frame.step_num || (stepCounter + 1);
        if (frame.used_vision) {
            visionFallbackCounter++;
            visionModeBadge.style.display = "inline-block";
        } else {
            visionModeBadge.style.display = "none";
        }

        stepsVal.textContent = `${stepCounter} Steps`;
        visionCountVal.textContent = visionFallbackCounter;

        if (frame.page_url) {
            previewPageUrl.textContent = `URL: ${frame.page_url}`;
        }

        if (frame.screenshot_base64) {
            previewPlaceholder.style.display = "none";
            livePreviewImg.style.display = "block";
            livePreviewImg.src = frame.screenshot_base64;
        }

        // Remove empty feed message
        const emptyMsg = logFeed.querySelector(".empty-feed-msg");
        if (emptyMsg) {
            emptyMsg.remove();
        }

        // Render Log Card
        const card = document.createElement("div");
        card.className = "log-card";

        const badgeClass = frame.used_vision ? "badge-vision" : "badge-info";
        const badgeText = frame.used_vision ? "👁️ Vision Fallback" : "🧠 Pure DOM";

        const coordsStr = (frame.x !== null && frame.x !== undefined) ? ` (${frame.x}, ${frame.y})` : "";
        const selectorStr = frame.selector ? ` | Locator: ${frame.selector}` : "";

        card.innerHTML = `
            <div class="log-card-header">
                <span class="log-step-title">STEP ${frame.step_num}: ${frame.action.toUpperCase()}${coordsStr}</span>
                <span class="badge ${badgeClass}">${badgeText}</span>
            </div>
            <div class="log-reasoning">💡 ${frame.reasoning || "Executing step action..."}</div>
            <div class="log-meta-row">
                <span>Status: ${frame.success ? "✅ Success" : "❌ Failed"}</span>
                <span>${selectorStr}</span>
            </div>
        `;

        logFeed.prepend(card);

        if (frame.action === "done") {
            taskStateBadge.className = "badge badge-success";
            taskStateBadge.textContent = "Completed";
        }
    }
});
