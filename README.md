# 🤖 Standalone AI Browser Agent & Form Auto-Filler (Chrome Extension V3)

> **100% Client-Side, Pure-DOM & Vision-Capable Autonomous AI Browser Agent powered by Groq (`llama-3.3-70b-versatile`). Zero Local Python Server or External Process Required!**

---

## 🌟 Overview

**Antigravity AI Browser Agent** is a lightweight, browser-native Chrome Extension (Manifest V3) that inspects web pages, extracts interactable form elements, and automatically fills forms in **1 unified step** using high-speed LLM reasoning via Groq.

Unlike traditional web agents that rely on heavy local Python servers, Playwright/Selenium drivers, or external backend microservices, this extension runs **entirely inside Google Chrome**. It securely maps user context stored in a local browser vault against detected form fields, executing instant batch inputs directly through Chrome's Native Scripting APIs (`chrome.scripting`).

---

## ✨ Key Features

- **⚡ 100% Standalone & Client-Side**: No Python backend, Node server, API proxy, or CLI daemon needed. Runs natively within the browser extension runtime.
- **🚀 High-Speed Pure-DOM Batch Auto-Filling**: Extracts all interactable inputs (`input`, `select`, `textarea`), queries Groq LLM (`llama-3.3-70b-versatile`) for field mapping, and fills all fields in 1 single step.
- **🔒 Encrypted Profile Context Vault**: Securely stores personal details (Name, Email, Phone, Address, Student/Employee IDs, Passwords, etc.) directly inside `chrome.storage.local`.
- **💻 Real-Time Telemetry & SidePanel UI**: Embedded Chrome SidePanel displays live execution logs, step-by-step decision telemetry, status badges, and action controls.
- **🔑 Direct Groq Integration**: Seamless integration with Groq's high-speed inference API with custom model selection.

---

## 🛠️ Installation & Setup Guide

### Step 1: Clone or Download Repository
Clone this repository to your local machine:
```bash
git clone https://github.com/ZainUlAbideen02/Al-Agent-Browser-Extension.git
cd Al-Agent-Browser-Extension
```
*(Alternatively, download and extract the ZIP file from GitHub).*

### Step 2: Open Extensions Page in Chrome
Navigate to `chrome://extensions` in your Google Chrome browser URL bar.

### Step 3: Enable Developer Mode
In the top-right corner of the Extensions page, toggle the **Developer mode** switch to **ON**.

### Step 4: Load Unpacked Extension
1. Click the **Load unpacked** button in the top-left area.
2. Select the `extension/` directory from the cloned repository.
3. The **Antigravity Visual Browser Agent** extension will instantly appear in your Chrome toolbar!

---

## ⚙️ Configuration (API Key & Profile Vault)

### 1. Acquire a Free Groq API Key
1. Visit [console.groq.com](https://console.groq.com) and log in or create a free account.
2. Navigate to **API Keys** and click **Create API Key**.
3. Copy your API Key (starts with `gsk_...`).

### 2. Configure the Extension SidePanel
1. Click the Extension icon in Chrome or click **Open Visual Agent Side Panel**.
2. Switch to the **🔑 Vault & Settings** tab inside the SidePanel.
3. Paste your **Groq API Key** (`gsk_...`) into the API Key field.
4. (Optional) Select or verify the Groq Model (default: `llama-3.3-70b-versatile`).
5. Fill in your user profile attributes:
   - **Personal Details**: First Name, Middle Name, Last Name, Full Name, Company.
   - **Contact Info**: Email, Phone Number.
   - **Address**: Street Address, City, State, Zip Code, Country.
   - **Credentials**: Username, Password.
6. Click **💾 Save Vault & Settings**. Your details are saved safely inside `chrome.storage.local`.

---

## 🚀 Usage Guide

1. **Open Target Page**: Navigate to any registration form, checkout page, job application, or data entry portal in Chrome.
2. **Launch SidePanel**: Click the extension action icon to expand the **Antigravity SidePanel**.
3. **Set Objective Goal**: Enter your goal in the goal text box (e.g., *"Fill out this registration form with my profile details"* or *"Auto-fill contact details and submit"*).
4. **Click ▶ Run Agent**:
   - The agent inspects all form inputs on the active tab.
   - Sends element attributes (labels, placeholders, names, IDs) to Groq.
   - Matches form fields with your local Profile Vault context.
   - Auto-fills all input fields, select dropdowns, and textareas in 1 unified batch step.
5. **View Real-Time Logs**: Watch live step-by-step telemetry logs in the SidePanel log feed.

---

## 📁 Architecture & File Overview

```
.
├── extension/             # Standalone Chrome Extension V3 Root
│   ├── manifest.json      # Extension V3 manifest definition & permissions
│   ├── background.js      # Service Worker managing port telemetry & execution pipeline
│   ├── reasoner.js        # Groq LLM API caller & field mapping engine
│   ├── executor.js        # Native DOM element inspector & batch auto-fill injector
│   ├── vault.js           # Vault storage manager & field alias resolver
│   ├── sidepanel.html     # Dual-tab UI layout (Control Center & Vault Settings)
│   ├── sidepanel.js       # SidePanel controller & telemetry renderer
│   └── icon.png           # Extension toolbar icon
├── .gitignore             # Workspace git ignore rules
├── LICENSE                # MIT License
└── README.md              # Project documentation
```

### Module Responsibilities:

- **`manifest.json`**: Configures Manifest V3 permissions (`scripting`, `storage`, `sidePanel`, `tabs`, `debugger`), host permissions (`https://api.groq.com/*`), background service worker, and sidepanel path.
- **`background.js`**: Background service worker handling telemetry ports (`agent_telemetry`), coordinating form extraction, invoking LLM reasoning, and triggering batch script injections.
- **`reasoner.js`**: Constructs system prompts, formats DOM element attributes alongside Vault context, queries Groq Chat Completions API (`llama-3.3-70b-versatile`), and resolves attribute values.
- **`executor.js`**: Injected into the active tab via `chrome.scripting.executeScript`. Extracts inputs (`input`, `select`, `textarea`), handles label association, scrolls elements into view, dispatches native input/change events, and submits forms if requested.
- **`vault.js`**: Embedded Context Vault manager using `chrome.storage.local`. Includes alias lookup dictionaries (`FIELD_ALIAS_MAP`) to match form fields against user profile attributes.
- **`sidepanel.html` & `sidepanel.js`**: Provides a modern, tabbed UI with real-time step execution feed, visual overlay markers, and Vault management.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
