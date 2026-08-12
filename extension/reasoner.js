// extension/reasoner.js - Lightweight Pure-DOM LLM Reasoner

import { resolveField, getVaultContextString } from "./vault.js";

const DOM_SYSTEM_PROMPT = `You are an Autonomous Lightweight Pure-DOM Form Auto-Filler Agent. You MUST respond ONLY with a raw, valid JSON object. Do NOT wrap the response in markdown, backticks, or extra prose.

USER PROFILE VAULT CONTEXT:
{vault_context}

CRITICAL INSTRUCTIONS:
1. Review the list of detected interactable form inputs from the webpage.
2. Match each form input field (using label, placeholder, id, or name hints) against the USER PROFILE VAULT CONTEXT.
3. Construct a mapping array 'fills' containing entries \`{"index": input_index, "vault_key": "attribute_name", "value": "attribute_value"}\`.
4. If the user's objective requests submitting the form, set 'submit' to true. Otherwise set 'submit' to false.

JSON Schema format:
{
  "thought": "Reasoning explanation of detected fields and vault attribute mapping...",
  "fills": [
    { "index": 0, "vault_key": "first_name", "value": "John" },
    { "index": 1, "vault_key": "last_name", "value": "Doe" }
  ],
  "submit": false,
  "action": "done"
}
`;

export async function decideDomStep({ goal, url, title, inputs, vaultData }) {
  const apiKey = vaultData.groq_api_key;
  if (!apiKey) {
    throw new Error("Groq API Key is missing. Please save your API key in Extension Settings tab.");
  }

  const model = vaultData.groq_model || "llama-3.3-70b-versatile";
  const vaultContextStr = getVaultContextString(vaultData);
  const systemPrompt = DOM_SYSTEM_PROMPT.replace("{vault_context}", vaultContextStr);

  const inputsJsonStr = JSON.stringify(inputs, null, 2);

  const userMessage = `User Goal: "${goal}"
Page URL: ${url || "N/A"}
Page Title: ${title || "N/A"}

Detected Web Form Inputs (${inputs.length} fields):
${inputsJsonStr}

Analyze the form inputs against the USER PROFILE VAULT CONTEXT and output strictly valid JSON matching the schema.`;

  const payload = {
    model: model,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage }
    ],
    temperature: 0.1,
    max_tokens: 2048,
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

  // Resolve Vault Values for all items in fills
  if (Array.isArray(decision.fills)) {
    for (const item of decision.fills) {
      if (item && (item.vault_key || item.value)) {
        const queryKey = item.vault_key || item.value;
        const resolved = resolveField(queryKey, vaultData);
        if (resolved) {
          item.value = resolved;
        }
      }
    }
  }

  return decision;
}
