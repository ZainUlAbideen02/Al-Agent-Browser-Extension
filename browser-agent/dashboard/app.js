// Antigravity Visual Agent Control Studio Application Logic

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements - Tab Navigation
    const tabs = document.querySelectorAll(".nav-tab");
    const tabContents = document.querySelectorAll(".tab-content");

    // DOM Elements - Live Telemetry
    const wsDot = document.getElementById("wsDot");
    const wsStatusText = document.getElementById("wsStatusText");
    const metricLatency = document.getElementById("metricLatency");
    const metricCoords = document.getElementById("metricCoords");
    const metricAction = document.getElementById("metricAction");
    const metricMode = document.getElementById("metricMode");
    const pageUrlMeta = document.getElementById("pageUrlMeta");

    // Viewport & Crosshair
    const viewportStage = document.getElementById("viewportStage");
    const stagePlaceholder = document.getElementById("stagePlaceholder");
    const liveScreenImg = document.getElementById("liveScreenImg");
    const targetCrosshair = document.getElementById("targetCrosshair");
    const coordTag = document.getElementById("coordTag");
    const feedList = document.getElementById("feedList");

    // Control Form
    const launchForm = document.getElementById("launchForm");
    const taskGoal = document.getElementById("taskGoal");
    const taskUrl = document.getElementById("taskUrl");
    const taskMode = document.getElementById("taskMode");
    const taskMaxSteps = document.getElementById("taskMaxSteps");
    const savePresetCheck = document.getElementById("savePresetCheck");
    const presetNameGroup = document.getElementById("presetNameGroup");
    const presetNameInput = document.getElementById("presetNameInput");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const clearLogsBtn = document.getElementById("clearLogsBtn");

    // Execution Card
    const execBadge = document.getElementById("execBadge");
    const execTaskId = document.getElementById("execTaskId");
    const execProgress = document.getElementById("execProgress");

    // Tasks & History
    const tasksGrid = document.getElementById("tasksGrid");
    const historyList = document.getElementById("historyList");
    const openNewTaskModalBtn = document.getElementById("openNewTaskModalBtn");
    const newTaskModal = document.getElementById("newTaskModal");
    const closeTaskModalBtn = document.getElementById("closeTaskModalBtn");
    const cancelModalBtn = document.getElementById("cancelModalBtn");
    const newTaskForm = document.getElementById("newTaskForm");

    // State Variables
    let socket = null;
    let activeTaskId = null;
    let currentStepCount = 0;
    let maxStepCount = 15;

    // --- 1. Tab Navigation Handler ---
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            tab.classList.add("active");
            const targetId = `tab-${tab.getAttribute("data-tab")}`;
            const targetContent = document.getElementById(targetId);
            if (targetContent) targetContent.classList.add("active");

            if (tab.getAttribute("data-tab") === "tasks") {
                loadTasks();
            } else if (tab.getAttribute("data-tab") === "history") {
                loadHistory();
            }
        });
    });

    // Checkbox toggle for preset name input
    savePresetCheck.addEventListener("change", () => {
        presetNameGroup.style.display = savePresetCheck.checked ? "block" : "none";
    });

    // --- 2. WebSocket Telemetry Connection ---
    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            wsDot.className = "ws-dot connected";
            wsStatusText.textContent = "Telemetry Live";
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleTelemetryEvent(data);
            } catch (err) {
                console.warn("Telemetry JSON parse error:", err);
            }
        };

        socket.onclose = () => {
            wsDot.className = "ws-dot disconnected";
            wsStatusText.textContent = "Disconnected";
            setTimeout(connectWebSocket, 3000);
        };

        socket.onerror = (err) => {
            console.error("WebSocket error:", err);
        };
    }

    // --- 3. Telemetry Event Handler & Crosshair Pinning ---
    function handleTelemetryEvent(data) {
        if (data.event === "step_update") {
            currentStepCount = data.step_num || currentStepCount;
            execProgress.textContent = `${currentStepCount} / ${maxStepCount}`;
            metricAction.textContent = data.action ? data.action.toUpperCase() : "Executing";

            if (data.page_url) pageUrlMeta.textContent = `URL: ${data.page_url}`;

            // Update Screenshot Image
            if (data.screenshot_base64) {
                stagePlaceholder.style.display = "none";
                liveScreenImg.style.display = "block";
                liveScreenImg.src = data.screenshot_base64.startsWith("data:") ? data.screenshot_base64 : `data:image/png;base64,${data.screenshot_base64}`;
            }

            // Update Crosshair Pin Overlay at (x, y) coordinates relative to 1280x800 viewport
            if (data.x !== null && data.x !== undefined && data.y !== null && data.y !== undefined) {
                targetCrosshair.style.display = "block";
                const posX = (data.x / 1280) * 100;
                const posY = (data.y / 800) * 100;
                targetCrosshair.style.left = `${posX}%`;
                targetCrosshair.style.top = `${posY}%`;
                coordTag.textContent = `(${data.x}, ${data.y})`;
                metricCoords.textContent = `(${data.x}, ${data.y})`;
            } else {
                targetCrosshair.style.display = "none";
                metricCoords.textContent = "N/A";
            }

            // Append reasoning step to feed
            addLogItem(data);
        } else if (data.event === "task_completed") {
            setTaskRunningState(false, "completed");
        } else if (data.event === "task_failed") {
            setTaskRunningState(false, "failed");
        }
    }

    function addLogItem(data) {
        if (feedList.querySelector(".feed-empty")) {
            feedList.innerHTML = "";
        }

        const item = document.createElement("div");
        item.className = `feed-item ${data.success === false ? 'failed' : ''}`;

        const coordsText = (data.x !== null && data.x !== undefined) ? `Coords: (${data.x}, ${data.y})` : "";
        const actionText = data.action ? data.action.toUpperCase() : "STEP";
        const valText = data.text ? ` -> "${data.text}"` : "";

        item.innerHTML = `
            <div class="feed-item-head">
                <span class="feed-step">STEP ${data.step_num}: ${actionText}${valText}</span>
                <span class="feed-coords">${coordsText}</span>
            </div>
            <div class="feed-reasoning">${data.thought || data.reasoning || "Executing step."}</div>
        `;

        feedList.insertBefore(item, feedList.firstChild);
    }

    clearLogsBtn.addEventListener("click", () => {
        feedList.innerHTML = '<div class="feed-empty">No telemetry events recorded yet.</div>';
    });

    // --- 4. Task Launch & Stop API Calls ---
    launchForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const goal = taskGoal.value.strip ? taskGoal.value.strip() : taskGoal.value.trim();
        const url = taskUrl.value.trim();
        const mode = taskMode.value;
        const maxSteps = parseInt(taskMaxSteps.value, 10);
        const saveAs = savePresetCheck.checked ? (presetNameInput.value.trim() || null) : null;

        if (!goal || !url) return;

        setTaskRunningState(true);
        maxStepCount = maxSteps;
        execProgress.textContent = `0 / ${maxSteps}`;
        feedList.innerHTML = '<div class="feed-empty">Waiting for initial telemetry step...</div>';

        try {
            const resp = await fetch("/api/agent/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    goal: goal,
                    url: url,
                    mode: mode,
                    max_steps: maxSteps,
                    save_as: saveAs
                })
            });

            const resData = await resp.json();
            if (resp.ok) {
                activeTaskId = resData.task_id;
                execTaskId.textContent = activeTaskId.slice(0, 8);
            } else {
                alert(`Error starting agent: ${resData.detail || "Unknown error"}`);
                setTaskRunningState(false, "idle");
            }
        } catch (err) {
            console.error("Start agent error:", err);
            alert(`Failed to start agent: ${err}`);
            setTaskRunningState(false, "idle");
        }
    });

    stopBtn.addEventListener("click", async () => {
        if (!activeTaskId) return;
        try {
            await fetch(`/api/agent/stop/${activeTaskId}`, { method: "POST" });
            setTaskRunningState(false, "cancelled");
        } catch (err) {
            console.error("Stop agent error:", err);
        }
    });

    function setTaskRunningState(isRunning, finalState = "running") {
        startBtn.disabled = isRunning;
        stopBtn.disabled = !isRunning;

        execBadge.className = `badge badge-${isRunning ? 'running' : (finalState === 'completed' ? 'success' : (finalState === 'failed' ? 'failed' : 'idle'))}`;
        execBadge.textContent = isRunning ? "Running" : finalState.toUpperCase();

        if (!isRunning) {
            targetCrosshair.style.display = "none";
        }
    }

    // --- 5. Saved Tasks Presets API ---
    async function loadTasks() {
        try {
            const resp = await fetch("/api/tasks");
            const tasks = await resp.json();
            renderTasksGrid(tasks);
        } catch (err) {
            console.error("Error loading tasks:", err);
        }
    }

    function renderTasksGrid(tasks) {
        tasksGrid.innerHTML = "";

        if (!tasks || tasks.length === 0) {
            tasksGrid.innerHTML = '<div class="feed-empty" style="grid-column: 1/-1;">No saved task presets found. Click "+ New Task Preset" to create one.</div>';
            return;
        }

        tasks.forEach(t => {
            const card = document.createElement("div");
            card.className = "task-card";
            card.innerHTML = `
                <div class="task-card-head">
                    <span class="task-card-title">${t.name}</span>
                    <span class="badge badge-info">${t.mode}</span>
                </div>
                <p class="task-card-goal">${t.goal}</p>
                <div class="task-card-meta">URL: ${t.url}</div>
                <div class="task-card-actions">
                    <button class="btn btn-terracotta run-preset-btn" data-goal="${t.goal.replace(/"/g, '&quot;')}" data-url="${t.url}" data-mode="${t.mode}">
                        ▶ Run Task
                    </button>
                    <button class="btn btn-ghost delete-preset-btn" data-name="${t.name}">🗑️</button>
                </div>
            `;
            tasksGrid.appendChild(card);
        });

        // Run Preset Handlers
        document.querySelectorAll(".run-preset-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const goal = btn.getAttribute("data-goal");
                const url = btn.getAttribute("data-url");
                const mode = btn.getAttribute("data-mode");

                taskGoal.value = goal;
                taskUrl.value = url;
                taskMode.value = mode;

                // Switch to Live Tab and trigger form submit
                document.querySelector('[data-tab="live"]').click();
                launchForm.dispatchEvent(new Event("submit"));
            });
        });

        // Delete Preset Handlers
        document.querySelectorAll(".delete-preset-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const name = btn.getAttribute("data-name");
                if (confirm(`Remove task preset '${name}'?`)) {
                    await fetch(`/api/tasks/${name}`, { method: "DELETE" });
                    loadTasks();
                }
            });
        });
    }

    // Modal Dialog Handlers
    openNewTaskModalBtn.addEventListener("click", () => newTaskModal.classList.add("active"));
    closeTaskModalBtn.addEventListener("click", () => newTaskModal.classList.remove("active"));
    cancelModalBtn.addEventListener("click", () => newTaskModal.classList.remove("active"));

    newTaskForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("modalTaskName").value.trim();
        const goal = document.getElementById("modalTaskGoal").value.trim();
        const url = document.getElementById("modalTaskUrl").value.trim();
        const mode = document.getElementById("modalTaskMode").value;

        if (!name || !goal || !url) return;

        try {
            await fetch("/api/tasks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, goal, url, mode })
            });
            newTaskModal.classList.remove("active");
            newTaskForm.reset();
            loadTasks();
        } catch (err) {
            console.error("Error creating preset:", err);
        }
    });

    // --- 6. Run History API ---
    async function loadHistory() {
        try {
            const resp = await fetch("/api/history");
            const history = await resp.json();
            renderHistoryList(history);
        } catch (err) {
            console.error("Error loading run history:", err);
        }
    }

    function renderHistoryList(history) {
        historyList.innerHTML = "";

        if (!history || history.length === 0) {
            historyList.innerHTML = '<div class="feed-empty">No past execution runs recorded yet.</div>';
            return;
        }

        history.forEach(item => {
            const row = document.createElement("div");
            row.className = "history-item";

            const selfAssess = item.self_assessment || {};
            const status = (selfAssess.completion_status || (item.final_status && item.final_status.includes("Completed") ? "FULLY_MET" : "FAILED")).toUpperCase();
            const badgeClass = status === "FULLY_MET" ? "badge-success" : (status === "PARTIALLY_MET" ? "badge-running" : "badge-failed");

            row.innerHTML = `
                <div class="history-item-info">
                    <span class="history-item-goal">🎯 Goal: ${item.goal}</span>
                    <span class="history-item-meta">URL: ${item.start_url} | Steps: ${item.total_steps || 0} | Mode: ${item.mode}</span>
                </div>
                <span class="badge ${badgeClass}">${status}</span>
            `;
            historyList.appendChild(row);
        });
    }

    document.getElementById("refreshHistoryBtn").addEventListener("click", loadHistory);

    // Initialize Telemetry WebSocket Connection
    connectWebSocket();
});
