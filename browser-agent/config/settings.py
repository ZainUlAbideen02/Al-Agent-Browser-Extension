import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger("browser_agent.config")

# Find project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root or parent workspace if present
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

def validate_config():
    """Verify that required configuration values are set."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.warning(
            "GEMINI_API_KEY is not set in environment or .env file. "
            "Please configure your key before making LLM calls."
        )
        return False
    return True
