// extension/background.js - Lightweight Pure-DOM Form Auto-Filler Service Worker

import { getVault } from "./vault.js";
import { decideDomStep } from "./reasoner.js";
import { extractFormInputs, fillFormBatch } from "./executor.js";

// Enable side panel on extension action click
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("Error setting sidePanel behavior:", error));

chrome.runtime.onInstalled.addListener(() => {
  console.log("Antigravity Pure-DOM Auto-Filler Extension Installed.");
});

let activePort = null;
let isTaskRunning = false;

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "agent_telemetry") {
    activePort = port;
    console.log("Telemetry port connected from SidePanel.");

    port.onMessage.addListener(async (msg) => {
      if (msg.type === "START_AGENT") {
        if (isTaskRunning) return;
        runDomAutoFiller(msg.payload);
      } else if (msg.type === "STOP_AGENT") {
        isTaskRunning = false;
      }
    });

    port.onDisconnect.addListener(() => {
      activePort = null;
    });
  }
});

function broadcastTelemetry(frame) {
  if (activePort) {
    try {
      activePort.postMessage({
        event: "step_update",
        task_id: frame.task_id || "dom_autofill_task",
        step_num: frame.step_num || 1,
        action: frame.action || "batch_type",
        mode: "PURE_DOM",
        thought: frame.thought || frame.reasoning || "Extracting page form fields...",
        x: null,
        y: null,
        screenshot_base64: "",
        status: frame.status || "running"
      });
    } catch (e) {
      console.warn("Failed to post telemetry frame to port:", e);
    }
  }
}

async function runDomAutoFiller(config) {
  const { goal } = config;
  isTaskRunning = true;

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

    // 1. Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      throw new Error("No active tab detected.");
    }

    broadcastTelemetry({
      step_num: 1,
      action: "inspect",
      status: "running",
      thought: `Inspecting form fields on tab: ${tab.title || tab.url}`
    });

    // 2. Extract DOM form inputs
    const inputs = await extractFormInputs(tab.id);
    if (!inputs || inputs.length === 0) {
      broadcastTelemetry({
        step_num: 1,
        action: "done",
        status: "completed",
        thought: "No interactable form inputs (input, select, textarea) detected on this page."
      });
      isTaskRunning = false;
      return;
    }

    broadcastTelemetry({
      step_num: 1,
      action: "reasoning",
      status: "running",
      thought: `Detected ${inputs.length} form input fields. Matching attributes with Vault using text LLM...`
    });

    // 3. Query Groq text LLM for field mapping
    const decision = await decideDomStep({
      goal,
      url: tab.url,
      title: tab.title,
      inputs,
      vaultData
    });

    const fills = decision.fills || [];
    const shouldSubmit = Boolean(decision.submit);

    broadcastTelemetry({
      step_num: 1,
      action: "batch_type",
      status: "running",
      thought: decision.thought || `Mapped ${fills.length} form fields. Executing batch auto-fill in 1 unified step...`
    });

    // 4. Batch fill DOM elements in 1 step
    const result = await fillFormBatch(tab.id, fills, shouldSubmit);

    // 5. Broadcast complete
    broadcastTelemetry({
      step_num: 1,
      action: "done",
      status: "completed",
      thought: `✅ Successfully auto-filled ${result.count} form fields in 1 step!${shouldSubmit ? " Form submitted." : ""}`
    });
  } catch (err) {
    console.error("DOM Auto-Filler exception:", err);
    broadcastTelemetry({
      step_num: 1,
      action: "failed",
      status: "failed",
      thought: `Error: ${err.message}`
    });
  } finally {
    isTaskRunning = false;
  }
}
