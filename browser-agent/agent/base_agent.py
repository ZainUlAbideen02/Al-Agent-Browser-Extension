import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Union, Optional
from PIL import Image
import google.generativeai as genai
from config.settings import GEMINI_API_KEY, DEFAULT_MODEL, validate_config

logger = logging.getLogger("browser_agent.agent.base")

class BaseAgent:
    """Base LLM wrapper managing Google Gemini calls with vision support and JSON retry logic."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = model_name or DEFAULT_MODEL

        if not self.api_key:
            validate_config()
        else:
            genai.configure(api_key=self.api_key)

        self._model = genai.GenerativeModel(self.model_name)

    def _clean_json_text(self, text: str) -> str:
        """Extract raw JSON text, removing markdown code blocks if present."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text

    def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        expect_json: bool = True,
        max_retries: int = 2,
        image_path: Optional[str] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Call Gemini LLM with prompt, optional vision screenshot, and JSON parsing retry logic.

        Args:
            system_prompt: System context instructions for the model.
            user_message: Specific request / user prompt context.
            expect_json: Whether output is expected to be a valid JSON dict.
            max_retries: Maximum number of retries if JSON parsing fails.
            image_path: Optional path to PNG screenshot image for vision model analysis.

        Returns:
            Parsed JSON dict if expect_json=True, else response text string.
        """
        combined_text = f"{system_prompt}\n\nUser Request:\n{user_message}"
        last_error = None

        image_obj = None
        if image_path and Path(image_path).exists():
            try:
                image_obj = Image.open(image_path)
                logger.info(f"Loaded vision image from {image_path}")
            except Exception as ie:
                logger.warning(f"Could not load image file {image_path}: {ie}")

        for attempt in range(1 + max_retries):
            try:
                current_text = combined_text
                if attempt > 0 and expect_json:
                    current_text += (
                        f"\n\n[ATTENTION: Previous response failed to parse as valid JSON. "
                        f"Error: {last_error}. Please output ONLY raw valid JSON, no markdown extra text.]"
                    )

                logger.debug(f"Calling Gemini LLM (Vision={image_obj is not None}, attempt {attempt + 1}/{1 + max_retries})...")
                
                content_payload = [current_text]
                if image_obj:
                    content_payload.append(image_obj)

                response = self._model.generate_content(content_payload)
                
                if not response.text:
                    raise ValueError("Received empty response from Gemini API.")

                response_text = response.text.strip()

                if not expect_json:
                    return response_text

                cleaned_text = self._clean_json_text(response_text)
                parsed_json = json.loads(cleaned_text)

                if not isinstance(parsed_json, dict):
                    raise ValueError(f"Expected JSON object/dict, got {type(parsed_json).__name__}")

                return parsed_json

            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to obtain valid response from LLM after {max_retries + 1} attempts. Last error: {last_error}"
                    ) from e

        raise RuntimeError("LLM call failed unexpectedly.")
