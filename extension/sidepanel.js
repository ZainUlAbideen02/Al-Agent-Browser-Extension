document.addEventListener("DOMContentLoaded", () => {
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const targetUrlInput = document.getElementById("targetUrl");
    const goalInput = document.getElementById("goal");
    const resolutionSelect = document.getElementById("resolution");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");

    const placeholderText = document.getElementById("placeholderText");
    const streamImg = document.getElementById("streamImg");
    const logContainer = document.getElementById("logContainer");

    let ws = null;

    // Auto-detect current active tab URL in Chrome
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.query) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs && tabs[0] && tabs[0].url) {
                targetUrlInput.value = tabs[0].url;
            }
        });
    }

    function connectWebSocket() {
        ws = new WebSocket("ws://localhost:8000/ws/telemetry");

        ws.onopen = () => {
            statusDot.className = "status-dot connected";
            statusText.textContent = "Connected";
        };

        ws.onclose = () => {
            statusDot.className = "status-dot disconnected";
            statusText.textContent = "Disconnected";
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (e) => {
            console.error("Extension WebSocket error:", e);
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

    connectWebSocket();

    startBtn.addEventListener("click", async () => {
        const resParts = resolutionSelect.value.split("x");
        const w = parseInt(resParts[0], 10);
        const h = parseInt(resParts[1], 10);

        const targetUrl = targetUrlInput.value.trim() || "https://the-internet.herokuapp.com/login";

        const payload = {
            url: targetUrl,
            goal: goalInput.value.trim(),
            max_steps: parseInt(maxStepsInput.value, 10),
            width: w,
            height: h,
            mode: "hybrid"
        };

        startBtn.disabled = true;
        startBtn.textContent = "⏳ Running...";

        try {
            const response = await fetch("http://localhost:8000/api/agent/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            logContainer.innerHTML = "";

        } catch (err) {
            alert(`Could not trigger agent: ${err.message}. Make sure server.py is running on localhost:8000.`);
            startBtn.disabled = false;
            startBtn.textContent = "▶ Run Visual Agent";
        }
    });

    function renderFrame(frame) {
        if (!frame) return;

        if (frame.screenshot_base64) {
            placeholderText.style.display = "none";
            streamImg.style.display = "block";
            streamImg.src = frame.screenshot_base64;
        }

        if (logContainer.querySelector("div[style*='text-align:center']")) {
            logContainer.innerHTML = "";
        }

        const item = document.createElement("div");
        item.className = "log-item";

        const coordsStr = (frame.x !== null && frame.x !== undefined) ? ` (${frame.x}, ${frame.y})` : "";

        item.innerHTML = `
            <div class="log-item-header">
                <span>STEP ${frame.step_num}: ${frame.action.toUpperCase()}${coordsStr}</span>
                <span class="badge badge-vision">👁️ Visual</span>
            </div>
            <div style="color:var(--text-primary); font-size:11px;">💡 ${frame.thought || frame.reasoning || "Action executed"}</div>
        `;

        logContainer.prepend(item);

        if (frame.action === "done") {
            startBtn.disabled = false;
            startBtn.textContent = "▶ Run Visual Agent";
        }
    }
});
