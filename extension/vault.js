// extension/vault.js - Embedded Context Vault & Storage Manager

export const DEFAULT_VAULT = {
  full_name: "John Alexander Doe",
  legal_name: "John Alexander Doe",
  first_name: "John",
  middle_name: "Alexander",
  last_name: "Doe",
  company: "Acme Corp",
  email: "john.doe@example.com",
  phone: "+1-555-0199",
  address: "123 Innovation Way, Tech Suite 400",
  city: "San Francisco",
  state: "CA",
  zip_code: "94105",
  country: "United States",
  username: "tomsmith",
  password: "SuperSecretPassword!",
  roll_number: "STU-2026-8891",
  student_id: "STU-9999",
  employee_id: "EMP-9042",
  groq_api_key: "",
  groq_vision_model: "qwen/qwen3.6-27b"
};

export const FIELD_ALIAS_MAP = {
  first_name: ["first_name", "firstname", "given_name", "fname"],
  middle_name: ["middle_name", "middle_initial", "middle", "mid_name", "mname"],
  last_name: ["last_name", "lastname", "surname", "family_name", "lname"],
  company: ["company", "organization", "company_name", "employer", "business", "org"],
  full_name: ["full_name", "legal_name", "name", "student_name", "user_name", "fullname"],
  email: ["email", "e_mail", "mail", "email_address", "contact_email"],
  phone: ["phone", "mobile", "contact", "cell", "telephone", "phone_number"],
  address: ["address", "street", "residence", "location", "address_line"],
  city: ["city", "town"],
  state: ["state", "province"],
  zip_code: ["zip", "zip_code", "postal", "postal_code", "zipcode"],
  country: ["country", "nation"],
  username: ["username", "user_id", "login_id", "login"],
  password: ["password", "pass", "secret", "pwd"],
  roll_number: ["roll_number", "roll_no", "student_id", "id_number"]
};

export async function getVault() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["user_vault"], (result) => {
      if (result && result.user_vault) {
        resolve({ ...DEFAULT_VAULT, ...result.user_vault });
      } else {
        chrome.storage.local.set({ user_vault: DEFAULT_VAULT });
        resolve({ ...DEFAULT_VAULT });
      }
    });
  });
}

export async function saveVault(data) {
  return new Promise((resolve) => {
    chrome.storage.local.get(["user_vault"], (result) => {
      const existing = result.user_vault || DEFAULT_VAULT;
      const updated = { ...existing, ...data };
      chrome.storage.local.set({ user_vault: updated }, () => {
        resolve(updated);
      });
    });
  });
}

export function resolveField(queryStr, vaultData) {
  if (!queryStr || !vaultData) return null;
  const clean = queryStr.trim().toLowerCase().replace(/[- #]/g, "_");

  // 1. Direct key match
  if (vaultData[clean] !== undefined && vaultData[clean] !== null && vaultData[clean] !== "") {
    return String(vaultData[clean]);
  }

  // 2. Alias match
  for (const [canonicalKey, aliases] of Object.entries(FIELD_ALIAS_MAP)) {
    for (const alias of aliases) {
      const aliasClean = alias.replace(/[- #]/g, "_");
      if (clean === aliasClean || clean.includes(aliasClean) || aliasClean.includes(clean)) {
        if (vaultData[canonicalKey]) {
          return String(vaultData[canonicalKey]);
        }
      }
    }
  }

  // 3. Fuzzy match against any vault keys
  for (const [key, val] of Object.entries(vaultData)) {
    if (key.includes("api_key") || key.includes("model")) continue;
    const keyClean = key.toLowerCase().replace(/[- #]/g, "_");
    if (keyClean.includes(clean) || clean.includes(keyClean)) {
      return String(val);
    }
  }

  return null;
}

export function getVaultContextString(vaultData) {
  const summary = [];
  for (const [k, v] of Object.entries(vaultData)) {
    if (k === "groq_api_key") continue;
    const valPreview = (k.includes("password") || k.includes("secret")) ? "******" : String(v);
    summary.append ? summary.append(`'${k}': '${valPreview}'`) : summary.push(`'${k}': '${valPreview}'`);
  }
  return "{ " + summary.join(", ") + " }";
}
