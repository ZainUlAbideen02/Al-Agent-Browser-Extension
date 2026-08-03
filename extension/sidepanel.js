document.addEventListener("DOMContentLoaded", () => {
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const goalInput = document.getElementById("goal");
    const modeSelect = document.getElementById("mode");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");

    const placeholderText = document.getElementById("placeholderText");
    const streamImg = document.getElementById("streamImg");
    const visionBadge = document.getElementById("visionBadge");
    const logContainer = document.getElementById("logContainer");

    let ws = null;

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
        // Query current active tab URL
        chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
            const activeTab = tabs[0];
            const url = activeTab ? activeTab.url : "https://books.toscrape.com/";

            const payload = {
                url: url,
                goal: goalInput.value.trim(),
                mode: modeSelect.value,
                max_steps: parseInt(maxStepsInput.value, 10)
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
            } finally {
                startBtn.disabled = false;
                startBtn.textContent = "▶ Run Agent on Active Tab";
            }
        });
    });

    function renderFrame(frame) {
        if (!frame) return;

        if (frame.used_vision) {
            visionBadge.style.display = "inline-block";
        } else {
            visionBadge.style.display = "none";
        }

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

        const badgeClass = frame.used_vision ? "badge-vision" : "badge-dom";
        const badgeText = frame.used_vision ? "👁️ Vision" : "🧠 DOM";

        item.innerHTML = `
            <div class="log-item-header">
                <span>STEP ${frame.step_num}: ${frame.action.toUpperCase()}</span>
                <span class="badge ${badgeClass}">${badgeText}</span>
            </div>
            <div style="color:var(--text-primary); font-size:11px;">💡 ${frame.reasoning || "Action executed"}</div>
        `;

        logContainer.prepend(item);
    }
});
