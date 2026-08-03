# Browser Agent 🤖🌐

An autonomous AI browser automation agent that interacts with web pages using Playwright and Google Gemini.

The agent uses a **hybrid approach**: DOM data is used as the primary decision-making source (structured interactive elements prompt context), combined with visual screenshots saved at every step for audit logging, inspection, and debugging.

---

## 🏗️ Project Architecture

```text
browser-agent/
├── agent/
│   ├── __init__.py
│   ├── base_agent.py       # LLM wrapper: call_llm(), JSON retry logic, Gemini SDK integration
│   ├── reasoner.py         # ReasonerAgent: decisions given goal + page state + history (Pydantic validated)
│   └── memory.py           # StepMemory: history tracking & loop detection (3+ repetitive actions)
├── browser/
│   ├── __init__.py
│   ├── controller.py       # Playwright wrapper: navigate, click, type, scroll, screenshot
│   ├── perception.py       # DOM perception: extracts ~30 interactive elements + captures step screenshot
│   └── actions.py          # Translates LLM JSON decision into Playwright execution commands
├── logs/                   # Step screenshots (step_N.png) & final summary JSON (run_summary.json)
├── config/
│   └── settings.py         # Configuration loader & GEMINI_API_KEY management
├── main.py                 # CLI entrypoint for running tasks
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment variables template
└── README.md               # Documentation & usage instructions
```

---

## ⚡ Installation & Setup

1. **Clone / Navigate to project directory**:
   ```bash
   cd browser-agent
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright Chromium browser binary**:
   ```bash
   playwright install chromium
   ```

4. **Configure your Gemini API Key**:
   Copy `.env.example` to `.env` and set your API key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```env
   GEMINI_API_KEY=your_google_gemini_api_key
   ```

---

## 🚀 How to Run

### Basic Usage (Headed Mode - Visible Browser)
By default, the agent runs in **headed mode** so you can watch the browser in real time:

```bash
python main.py --goal "Search for 'laptop' on Google and report the first result" --url "https://google.com"
```

### Options & Flags
- `--goal`: *(Required)* High-level instruction or objective for the AI agent.
- `--url`: *(Required)* Initial target web URL to load.
- `--max-steps`: *(Optional)* Maximum number of step iterations before stopping (default: `15`).
- `--headless`: *(Optional)* Run browser in background headless mode (no visible GUI window).

#### Example running in headless mode:
```bash
python main.py --goal "Look up news on Wikipedia" --url "https://wikipedia.org" --max-steps 10 --headless
```

---

## 💡 Hybrid DOM + Screenshot Approach vs. Pure-Vision Agents

### Why Hybrid DOM + Screenshots?
1. **Token Efficiency & Speed**: 
   Passing full high-resolution image frames to Multimodal Vision Models for every step can be token-heavy, slow, and expensive. Extracting a trimmed list of ~30 visible, interactive DOM elements (buttons, text inputs, links) provides immediate precise selectors directly to the LLM without high vision overhead.
2. **Exact Element Selectors**:
   Pure-vision agents rely on predicting (x, y) coordinates or bounding box overlays, which can misfire on dynamic, responsive, or scrolling layouts. DOM perception yields direct HTML attributes, IDs, and Playwright text locators.
3. **Full Audit & Debugging Logs**:
   While the decision engine runs on structured DOM elements, capturing a screenshot at every step (`logs/step_N.png`) provides complete visual audit logging, error troubleshooting, and step-by-step playback.
