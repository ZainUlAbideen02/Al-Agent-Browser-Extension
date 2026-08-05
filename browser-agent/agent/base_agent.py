import os
import time
import json
import base64
import logging
import re
from pathlib import Path
from typing import Any, Dict, Union, Optional
from groq import Groq
from config.settings import GROQ_API_KEY, DEFAULT_TEXT_MODEL, DEFAULT_VISION_MODEL, check_api_key

logger = logging.getLogger("browser_agent.agent.base")

class BaseAgent:
    """Base LLM wrapper managing Groq API calls with vision support and JSON retry logic."""

    def __init__(self, api_key: Optional[str] = None, text_model: Optional[str] = None, vision_model: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        if not self.api_key or self.api_key == "your_key_here":
            self.api_key = check_api_key()

        self.text_model = text_model or DEFAULT_TEXT_MODEL
        self.vision_model = vision_model or DEFAULT_VISION_MODEL
        
        self.client = Groq(api_key=self.api_key)

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
        max_retries: int = 3,
        image_path: Optional[str] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Call Groq API with system/user prompt, optional base64 image payload, and JSON retry logic.
        Includes rate limit exponential backoff replenishment.
        """
        is_vision = False
        encoded_image = None

        if image_path and Path(image_path).exists():
            try:
                with open(image_path, "rb") as img_file:
                    encoded_image = base64.b64encode(img_file.read()).decode("utf-8")
                is_vision = True
                logger.info(f"Encoded vision screenshot from {image_path} to base64.")
            except Exception as ie:
                logger.warning(f"Could not read image file {image_path}: {ie}")

        model_name = self.vision_model if is_vision else self.text_model
        last_error = None

        for attempt in range(1 + max_retries):
            try:
                current_user_msg = user_message
                if attempt > 0 and expect_json:
                    current_user_msg += (
                        f"\n\n[ATTENTION: Previous response failed to parse as valid JSON. "
                        f"Error: {last_error}. Please output ONLY raw valid JSON matching the schema.]"
                    )

                messages = [{"role": "system", "content": system_prompt}]

                if is_vision and encoded_image:
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": current_user_msg},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{encoded_image}"
                                }
                            }
                        ]
                    })
                else:
                    messages.append({"role": "user", "content": current_user_msg})

                logger.debug(f"Calling Groq API (Model={model_name}, Vision={is_vision}, Attempt {attempt + 1}/{1 + max_retries})...")

                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.1,
                }
                if expect_json and not is_vision:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.client.chat.completions.create(**kwargs)

                if not response.choices or not response.choices[0].message.content:
                    raise ValueError("Received empty response from Groq API.")

                response_text = response.choices[0].message.content.strip()

                if not expect_json:
                    return response_text

                cleaned_text = self._clean_json_text(response_text)
                parsed_json = json.loads(cleaned_text)

                if not isinstance(parsed_json, dict):
                    raise ValueError(f"Expected JSON object/dict, got {type(parsed_json).__name__}")

                return parsed_json

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Groq API call attempt {attempt + 1} failed: {e}")

                if "429" in last_error or "Rate limit" in last_error or "tokens" in last_error:
                    backoff_time = 6.0 * (attempt + 1)
                    logger.info(f"Groq API rate limit hit (429). Sleeping {backoff_time}s for rate limit bucket replenishment...")
                    time.sleep(backoff_time)

                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to obtain valid response from Groq API after {max_retries + 1} attempts. Last error: {last_error}"
                    ) from e

        raise RuntimeError("Groq API call failed unexpectedly.")
