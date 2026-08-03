# Browser Agent 🤖🌐 (Hybrid DOM + Vision Fallback via Groq API)

An autonomous AI browser automation agent that interacts with web pages using Playwright and Groq API.

The agent features a **hybrid architecture**: DOM perception is used as the primary decision-making source with `openai/gpt-oss-120b` for high speed and token efficiency. If element interaction or selector resolution fails twice consecutively (or when stuck), the agent automatically triggers **Vision Fallback**, sending a base64-encoded screenshot to Groq's multimodal vision model `qwen/qwen3.6-27b` to recover and recommend alternative actions.

---

## 🏗️ Project Architecture

```text
browser-agent/
├── agent/
│   ├── __init__.py
│   ├── base_agent.py       # LLM wrapper: Groq API client, dual model routing, base64 vision support
│   ├── reasoner.py         # ReasonerAgent: DOM decision + decide_with_vision() fallback (Pydantic validated)
│   └── memory.py           # StepMemory: history tracking, used_vision_fallback flags, progress loop guards
├── browser/
│   ├── __init__.py
│   ├── controller.py       # Playwright wrapper: navigation, click, type, scroll, 20s timeouts
│   ├── perception.py       # DOM perception: extracts ~30 interactive elements + captures step screenshot
│   └── actions.py          # Translates LLM JSON decision into Playwright execution with stale-element recovery
├── logs/                   # Step screenshots (step_N.png), run_summary.json & evaluation_results.json
├── config/
│   └── settings.py         # Configuration loader & GROQ_API_KEY management
├── evaluate.py             # Benchmark evaluation suite running 5 standardized web tasks
├── main.py                 # CLI entrypoint for running browser tasks
├── requirements.txt        # Python package dependencies (playwright, groq, pydantic, pillow, etc.)
├── .env.example            # Environment variables template
└── README.md               # Documentation & usage instructions
```

---

## ⚡ Groq Dual-Model Architecture

- **DOM Reasoning Model**: `openai/gpt-oss-120b`
  Used for fast, structured JSON decision-making over extracted interactive DOM elements (~30 elements).
- **Vision Fallback Model**: `qwen/qwen3.6-27b`
  Used when selector interaction fails twice in a row. Takes base64 PNG data URLs (`data:image/png;base64,...`) alongside step context to visually analyze page state.

---

## 🛠️ Installation & Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright Chromium browser**:
   ```bash
   playwright install chromium
   ```

3. **Get your Groq API Key**:
   Create a free account and generate an API key at [Console Groq](https://console.groq.com).

4. **Configure `.env`**:
   Copy `.env.example` to `.env` and set your key:
   ```env
   GROQ_API_KEY=gsk_your_groq_api_key_here
   ```

---

## 🚀 How to Run

### 1. Basic Agent CLI Task
```bash
python main.py --goal "Search for 'laptop' on Google and report the first result" --url "https://google.com"
```

#### CLI Flags:
- `--goal`: *(Required)* Task objective description.
- `--url`: *(Required)* Initial URL.
- `--max-steps`: *(Optional)* Maximum step count (default: `15`).
- `--headless`: *(Optional)* Run browser in background headless mode.

### 2. Running the Evaluation Benchmark Suite
To execute all 5 benchmark tasks and generate `logs/evaluation_results.json`:

```bash
python evaluate.py --max-steps 10 --headless
```

---

## 📊 Evaluation Harness Tasks
1. **Browse Category**: Select 'Travel' category link on `books.toscrape.com`.
2. **Extract Price**: Identify first product price on `books.toscrape.com`.
3. **Quote Extraction**: Extract first quote and author on `quotes.toscrape.com`.
4. **Wikipedia Heading**: Locate main title on `wikipedia.org`.
5. **Wikipedia Search**: Search for 'Artificial Intelligence' on `wikipedia.org`.
