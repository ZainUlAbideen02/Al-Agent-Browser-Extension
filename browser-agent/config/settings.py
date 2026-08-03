import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger("browser_agent.config")

# Find project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEFAULT_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.1-8b-instant")
DEFAULT_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

def check_api_key() -> str:
    """Verify that GROQ_API_KEY is configured or raise a clear error."""
    if not GROQ_API_KEY or GROQ_API_KEY == "your_key_here":
        raise ValueError(
            "GROQ_API_KEY is not configured! Please add your Groq API key to "
            "the .env file (e.g. GROQ_API_KEY=gsk_...) or set the GROQ_API_KEY environment variable. "
            "Get a key at https://console.groq.com"
        )
    return GROQ_API_KEY

def validate_config() -> bool:
    """Helper validation check returning bool."""
    try:
        check_api_key()
        return True
    except ValueError as e:
        logger.error(str(e))
        return False
