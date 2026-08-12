// extension/background.js - Standalone Agent Event Loop Service Worker

import { getVault } from "./vault.js";
import { decideVisualStep } from "./reasoner.js";
import { executeTabAction } from "./executor.js";

// Enable panel opening when extension icon is clicked
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("Error setting sidePanel behavior:", error));

chrome.runtime.onInstalled.addListener(() => {
  console.log("Antigravity Standalone Visual Agent Extension Installed.");
});

let activePort = null;
let isTaskRunning = false;
let shouldStopTask = false;

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "agent_telemetry") {
    activePort = port;
    console.log("Telemetry port connected from SidePanel.");

    port.onMessage.addListener(async (msg) => {
      if (msg.type === "START_AGENT") {
        if (isTaskRunning) return;
        runAgentLoop(msg.payload);
      } else if (msg.type === "STOP_AGENT") {
        shouldStopTask = true;
      }
    });

    port.onDisconnect.addListener(() => {
      console.log("Telemetry port disconnected.");
      activePort = null;
    });
  }
});

function broadcastTelemetry(frame) {
  if (activePort) {
    try {
      activePort.postMessage({
        event: "step_update",
        task_id: frame.task_id || "standalone_task",
        step_num: frame.step_num || 1,
        action: frame.action || "step",
        mode: frame.mode || "visual",
        thought: frame.thought || frame.reasoning || "Processing visual context...",
        x: frame.x !== undefined ? frame.x : null,
        y: frame.y !== undefined ? frame.y : null,
        screenshot_base64: frame.screenshot_base64 || "",
        status: frame.status || "running"
      });
    } catch (e) {
      console.warn("Failed to post telemetry frame to port:", e);
    }
  }
}

async function runAgentLoop(config) {
  const { goal, maxSteps = 50 } = config;
  isTaskRunning = true;
  shouldStopTask = false;
  const history = [];

  try {
    const vaultData = await getVault();
    if (!vaultData.groq_api_key) {
      broadcastTelemetry({
        step_num: 0,
        action: "failed",
        status: "failed",
        thought: "Groq API key missing! Please save your Groq API key in Extension Settings."
      });
      isTaskRunning = false;
      return;
    }

    // Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      throw new Error("No active browser tab detected.");
    }

    for (let step = 1; step <= maxSteps; step++) {
      if (shouldStopTask) {
        broadcastTelemetry({
          step_num: step,
          action: "cancelled",
          status: "failed",
          thought: "Task execution stopped by user."
        });
        break;
      }

      console.log(`--- Standalone Agent Step ${step}/${maxSteps} ---`);

      // 1. Capture visible tab screenshot
      const screenshotUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });

      // 2. Format history summary
      const historySummary = history.map(h => `Step ${h.step}: ${h.action} -> ${h.thought}`).slice(-5).join("\n");

      // 3. Query LLM Vision Reasoner
      let decision;
      try {
        decision = await decideVisualStep({
          goal,
          url: tab.url,
          title: tab.title,
          screenshotBase64: screenshotUrl,
          historySummary,
          vaultData
        });
      } catch (err) {
        console.error("LLM reasoning error:", err);
        broadcastTelemetry({
          step_num: step,
          action: "failed",
          status: "failed",
          thought: `Reasoning Error: ${err.message}`,
          screenshot_base64: screenshotUrl
        });
        break;
      }

      // 4. Send real-time telemetry to sidepanel UI
      broadcastTelemetry({
        step_num: step,
        action: decision.action,
        mode: "VISUAL",
        thought: decision.reasoning,
        x: decision.x,
        y: decision.y,
        screenshot_base64: screenshotUrl,
        status: decision.action === "done" ? "completed" : "running"
      });

      // 5. Execute action on DOM
      if (decision.action !== "done" && decision.action !== "ask_human") {
        try {
          await executeTabAction(tab.id, decision);
        } catch (execErr) {
          console.warn("Action execution warning:", execErr);
        }
      }

      // Record step in history
      history.push({ step, action: decision.action, thought: decision.reasoning });

      if (decision.action === "done") {
        console.log("Goal marked complete by agent!");
        broadcastTelemetry({
          step_num: step,
          action: "done",
          status: "completed",
          thought: `Goal Completed: ${decision.reasoning}`,
          screenshot_base64: screenshotUrl
        });
        break;
      }

      if (step === maxSteps) {
        broadcastTelemetry({
          step_num: step,
          action: "done",
          status: "completed",
          thought: `Reached maximum step limit (${maxSteps}).`,
          screenshot_base64: screenshotUrl
        });
      }

      // Wait between steps
      await new Promise((r) => setTimeout(r, 1500));
    }
  } catch (globalErr) {
    console.error("Global agent loop exception:", globalErr);
    broadcastTelemetry({
      step_num: 0,
      action: "failed",
      status: "failed",
      thought: `Error: ${globalErr.message}`
    });
  } finally {
    isTaskRunning = false;
  }
}
