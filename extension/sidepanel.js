document.addEventListener("DOMContentLoaded", () => {
    // Navigation Tabs
    const tabNavControl = document.getElementById("tabNavControl");
    const tabNavVault = document.getElementById("tabNavVault");
    const tabContentControl = document.getElementById("tabContentControl");
    const tabContentVault = document.getElementById("tabContentVault");

    // Form Elements
    const targetUrlInput = document.getElementById("targetUrl");
    const goalInput = document.getElementById("goal");
    const maxStepsInput = document.getElementById("maxSteps");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");

    const streamContainer = document.getElementById("streamContainer");
    const placeholderText = document.getElementById("placeholderText");
    const streamImg = document.getElementById("streamImg");
    const targetOverlayMarker = document.getElementById("targetOverlayMarker");
    const markerLabel = document.getElementById("markerLabel");
    const logContainer = document.getElementById("logContainer");

    // Vault Inputs
    const groqApiKeyInput = document.getElementById("groqApiKey");
    const groqModelInput = document.getElementById("groqModel");
    const saveVaultBtn = document.getElementById("saveVaultBtn");
    const saveStatusText = document.getElementById("saveStatusText");

    const vaultFieldIds = [
        "first_name", "middle_name", "last_name", "company", "full_name",
        "email", "phone", "address", "city", "state", "zip_code", "country",
        "username", "password"
    ];

    let port = null;
    let activeWidth = 1280;
    let activeHeight = 800;

    // Tab Switching Logic
    tabNavControl.addEventListener("click", () => {
        tabNavControl.classList.add("active");
        tabNavVault.classList.remove("active");
        tabContentControl.classList.add("active");
        tabContentVault.classList.remove("active");
    });

    tabNavVault.addEventListener("click", () => {
        tabNavVault.classList.add("active");
        tabNavControl.classList.remove("active");
        tabContentVault.classList.add("active");
        tabContentControl.classList.remove("active");
        loadVaultSettings();
    });

    // Auto-detect current active tab URL
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.query) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs && tabs[0] && tabs[0].url) {
                targetUrlInput.value = tabs[0].url;
            }
        });
    }

    // Connect runtime port to background.js
    function connectPort() {
        if (typeof chrome === "undefined" || !chrome.runtime) return;
        port = chrome.runtime.connect({ name: "agent_telemetry" });

        port.onMessage.addListener((message) => {
            if (message && message.event === "step_update") {
                renderFrame(message);
            }
        });

        port.onDisconnect.addListener(() => {
            console.warn("Background port disconnected. Reconnecting...");
            setTimeout(connectPort, 1000);
        });
    }

    connectPort();

    // Start Task
    startBtn.addEventListener("click", () => {
        const goal = goalInput.value.trim();
        const maxSteps = parseInt(maxStepsInput.value, 10) || 50;

        if (!goal) {
            alert("Please enter an objective goal.");
            return;
        }

        startBtn.style.display = "none";
        stopBtn.style.display = "block";
        logContainer.innerHTML = "";

        if (port) {
            port.postMessage({
                type: "START_AGENT",
                payload: { goal, maxSteps }
            });
        }
    });

    // Stop Task
    stopBtn.addEventListener("click", () => {
        if (port) {
            port.postMessage({ type: "STOP_AGENT" });
        }
        resetButtons();
    });

    function resetButtons() {
        startBtn.style.display = "block";
        stopBtn.style.display = "none";
    }

    // Render Telemetry Step Frame
    function renderFrame(frame) {
        if (!frame) return;

        // 1. Screenshot Stream
        if (frame.screenshot_base64) {
            placeholderText.style.display = "none";
            streamImg.style.display = "block";
            streamImg.src = frame.screenshot_base64.startsWith("data:") 
                ? frame.screenshot_base64 
                : `data:image/png;base64,${frame.screenshot_base64}`;
        }

        // 2. Crosshair Overlay Marker
        if (frame.x !== undefined && frame.x !== null && frame.y !== undefined && frame.y !== null) {
            targetOverlayMarker.style.display = "block";
            const rescaleX = (frame.x / activeWidth) * 100;
            const rescaleY = (frame.y / activeHeight) * 100;
            targetOverlayMarker.style.left = `${rescaleX}%`;
            targetOverlayMarker.style.top = `${rescaleY}%`;
            const actionText = (frame.action || "TARGET").toString().toUpperCase();
            markerLabel.textContent = `${actionText} (${frame.x}, ${frame.y})`;
        }

        // 3. Step Logs
        if (frame.step_num || frame.thought || frame.action) {
            if (logContainer.querySelector("div[style*='text-align:center']")) {
                logContainer.innerHTML = "";
            }
            const logItem = document.createElement("div");
            logItem.className = "log-item";
            
            const safeAction = (frame.action || "INFO").toString().toUpperCase();
            const safeMode = (frame.mode || "VISUAL").toString().toUpperCase();
            const safeThought = frame.thought || frame.reasoning || "Executing action...";

            logItem.innerHTML = `
                <div class="log-header">
                    <span>STEP ${frame.step_num || '-'}: ${safeAction}</span>
                    <span class="badge">${safeMode}</span>
                </div>
                <div style="color:var(--text-primary); font-size:11px;">💡 ${safeThought}</div>
            `;
            
            logContainer.prepend(logItem);
        }

        // 4. Reset on Done or Failed
        if (frame.action === "done" || frame.status === "completed" || frame.status === "failed") {
            resetButtons();
        }
    }

    // Vault Storage Functions
    function loadVaultSettings() {
        if (typeof chrome === "undefined" || !chrome.storage) return;
        chrome.storage.local.get(["user_vault"], (res) => {
            const vault = res.user_vault || {};
            groqApiKeyInput.value = vault.groq_api_key || "";
            groqModelInput.value = vault.groq_model || "llama-3.3-70b-versatile";

            for (const key of vaultFieldIds) {
                const el = document.getElementById(`v_${key}`);
                if (el) {
                    el.value = vault[key] || "";
                }
            }
        });
    }

    saveVaultBtn.addEventListener("click", () => {
        if (typeof chrome === "undefined" || !chrome.storage) return;
        
        chrome.storage.local.get(["user_vault"], (res) => {
            const existing = res.user_vault || {};
            const updated = {
                ...existing,
                groq_api_key: groqApiKeyInput.value.trim(),
                groq_model: groqModelInput.value.trim() || "llama-3.3-70b-versatile"
            };

            for (const key of vaultFieldIds) {
                const el = document.getElementById(`v_${key}`);
                if (el) {
                    updated[key] = el.value.trim();
                }
            }

            chrome.storage.local.set({ user_vault: updated }, () => {
                saveStatusText.style.display = "block";
                setTimeout(() => {
                    saveStatusText.style.display = "none";
                }, 2000);
            });
        });
    });

    loadVaultSettings();
});
