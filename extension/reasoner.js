// extension/reasoner.js - Standalone In-Browser Vision LLM Reasoner

import { resolveField, getVaultContextString } from "./vault.js";

const SYSTEM_PROMPT_TEMPLATE = `You are an Autonomous Visual Browser Agent. You MUST respond ONLY with a raw, valid JSON object. Do NOT wrap the response in markdown, backticks, or extra prose.

USER PROFILE VAULT CONTEXT:
{vault_context}

CRITICAL INSTRUCTIONS:
1. Examine the screenshot for human intervention requirements first:
   - Set 'human_required' to true if page presents an account login form, CAPTCHA puzzle, 2FA code prompt, or checkout payment screen. Set 'requirement_type' to 'login', 'captcha', '2fa', or 'payment'.
2. If no human intervention is required, calculate center (x, y) coordinates for the next physical visual action:
   - Coordinates are [0..1279 X, 0..799 Y].
   - 'type': specify center (x, y) and 'text' value to type. Reference USER PROFILE VAULT CONTEXT.
   - 'batch_type': if multiple input fields are visible on the page (e.g. forms, registration, checkout, multi-field tests), specify action 'batch_type' and provide 'batch_inputs' array containing all field entries \`[{"x": center_x, "y": center_y, "text": "profile_vault_key_or_value"}, ...]\` to fill out ALL form fields across the page in a single step! Match all detected form fields against USER PROFILE VAULT CONTEXT (First Name, Middle Name, Last Name, Full Name, Company, Address, City, Country, Phone, Email, etc.) in a unified plan.
   - 'click': specify center (x, y).
   - 'select': specify center (x, y) and 'value'.
   - 'key': specify 'key' name ('Enter', 'Tab', 'Escape').
   - 'scroll': set 'direction' ('down' / 'up').
   - 'ask_human': choose if stuck or uncertain.
   - 'done': choose when user objective is complete.

JSON Schema format:
{
  "reasoning": "Reasoning visual analysis here",
  "human_required": false,
  "requirement_type": null,
  "action": "click",
  "x": 640,
  "y": 400,
  "text": null,
  "value": null,
  "key": null,
  "direction": null,
  "batch_inputs": null
}
`;

export async function decideVisualStep({ goal, url, title, screenshotBase64, historySummary, vaultData }) {
  const apiKey = vaultData.groq_api_key;
  if (!apiKey) {
    throw new Error("Groq API Key is missing. Please save your API key in the Extension Settings tab.");
  }

  const model = vaultData.groq_vision_model || "qwen/qwen3.6-27b";
  const vaultContextStr = getVaultContextString(vaultData);
  const systemPrompt = SYSTEM_PROMPT_TEMPLATE.replace("{vault_context}", vaultContextStr);

  const formattedScreenshot = screenshotBase64.startsWith("data:") 
    ? screenshotBase64 
    : `data:image/png;base64,${screenshotBase64}`;

  const userMessage = `User Goal: "${goal}"
Current Page URL: ${url || "N/A"}
Current Page Title: ${title || "N/A"}
Viewport Resolution: 1280x800

Execution History (Last steps):
${historySummary || "No previous steps."}

Analyze the screenshot and output strictly valid JSON with reasoning and target action decision.`;

  const payload = {
    model: model,
    messages: [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: [
          { type: "text", text: userMessage },
          { type: "image_url", image_url: { url: formattedScreenshot } }
        ]
      }
    ],
    temperature: 0.1,
    max_tokens: 1024,
    response_format: { type: "json_object" }
  };

  const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Groq API HTTP ${response.status}: ${errText}`);
  }

  const resJson = await response.json();
  let rawContent = resJson.choices?.[0]?.message?.content;
  if (!rawContent) {
    throw new Error("Groq API returned empty response.");
  }

  let decision;
  try {
    rawContent = rawContent.trim();
    if (rawContent.startsWith("```")) {
      rawContent = rawContent.replace(/^```(?:json)?\n?/, "").replace(/\n?```$/, "").trim();
    }
    decision = JSON.parse(rawContent);
  } catch (parseErr) {
    throw new Error(`Failed to parse LLM JSON response: ${rawContent}`);
  }

  // Resolve Vault Fields automatically
  if (decision.action === "type" && decision.text) {
    const resolved = resolveField(decision.text, vaultData);
    if (resolved) {
      decision.text = resolved;
    }
  } else if (decision.action === "batch_type" && Array.isArray(decision.batch_inputs)) {
    for (const item of decision.batch_inputs) {
      if (item && item.text) {
        const resolved = resolveField(item.text, vaultData);
        if (resolved) {
          item.text = resolved;
        }
      }
    }
  }

  return decision;
}
