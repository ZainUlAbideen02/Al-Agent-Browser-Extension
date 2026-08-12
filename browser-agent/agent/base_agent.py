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
    """Base LLM wrapper managing Groq API calls with vision support, empty response logging, and JSON retry logic."""

    def __init__(self, api_key: Optional[str] = None, text_model: Optional[str] = None, vision_model: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        if not self.api_key or self.api_key == "your_key_here":
            self.api_key = check_api_key()

        self.text_model = text_model or DEFAULT_TEXT_MODEL
        self.vision_model = vision_model or DEFAULT_VISION_MODEL

        # Ordered fallback chain of vision-capable models to try before text-only degradation.
        # Only qwen/qwen3.6-27b supports vision on this Groq account (confirmed via models.list()).
        # Text-only fallback is used when vision quota is exhausted or unavailable.
        self.vision_fallback_chain = [
            self.vision_model,
            # No additional vision models available on this account — falls through to text-only
        ]
        self._current_vision_model_idx = 0

        self.client = Groq(api_key=self.api_key)

    def _clean_json_text(self, text: str) -> str:
        """Extract raw JSON text, removing markdown code blocks if present."""
        if not text:
            return ""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text

    def _log_debug_api_response(self, response: Any, error_msg: str) -> None:
        """Log raw API response object details to logs/api_debug.log when empty/error responses occur."""
        try:
            debug_path = Path(__file__).resolve().parent.parent / "logs" / "api_debug.log"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- API DEBUG [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
                f.write(f"Error Context: {error_msg}\n")
                if hasattr(response, "model_dump_json"):
                    f.write(f"Response Object: {response.model_dump_json(indent=2)}\n")
                else:
                    f.write(f"Response Object: {str(response)}\n")
        except Exception as log_err:
            logger.warning(f"Could not write to api_debug.log: {log_err}")

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
        Includes rate limit exponential backoff replenishment and empty-content safeguards.
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
                        f"\n\n[ATTENTION: Previous response failed. "
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

                if not response or not response.choices:
                    self._log_debug_api_response(response, "No choices returned in API response")
                    raise ValueError("Groq API returned empty response with no choices.")

                raw_msg_content = response.choices[0].message.content
                if raw_msg_content is None or not str(raw_msg_content).strip():
                    self._log_debug_api_response(response, f"Empty/whitespace content returned. finish_reason={response.choices[0].finish_reason}")
                    raise ValueError(f"Groq API returned empty response content (finish_reason={response.choices[0].finish_reason}).")

                response_text = str(raw_msg_content).strip()

                if not expect_json:
                    return response_text

                cleaned_text = self._clean_json_text(response_text)
                if not cleaned_text:
                    self._log_debug_api_response(response, "Cleaned JSON text is empty")
                    raise ValueError("Cleaned response text is empty.")

                parsed_json = json.loads(cleaned_text)

                if not isinstance(parsed_json, dict):
                    raise ValueError(f"Expected JSON object/dict, got {type(parsed_json).__name__}")

                return parsed_json

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Groq API call attempt {attempt + 1} failed: {e}")

                # Catch rate-limits AND model-not-found (404) — both trigger chain traversal
                should_chain = (
                    is_vision and (
                        "rate_limit" in str(e).lower()
                        or "429" in str(e)
                        or "limit reached" in str(e).lower()
                        or "model_not_found" in str(e).lower()
                        or "404" in str(e)
                        or "does not exist" in str(e).lower()
                    )
                )
                if should_chain:
                    # Try next vision model in the fallback chain before dropping to text-only
                    self._current_vision_model_idx += 1
                    if self._current_vision_model_idx < len(self.vision_fallback_chain):
                        next_vision = self.vision_fallback_chain[self._current_vision_model_idx]
                        logger.warning(f"Vision model {model_name} rate limited. Trying next vision model: {next_vision}")
                        model_name = next_vision
                        continue
                    else:
                        # All vision models exhausted — fall back to text-only as last resort
                        logger.warning(f"All vision models exhausted. Falling back to text model {self.text_model} (no image)...")
                        is_vision = False
                        model_name = self.text_model
                        encoded_image = None
                        self._current_vision_model_idx = 0  # reset for next call
                        continue

                backoff_time = 4.0 * (attempt + 1)
                logger.info(f"Sleeping {backoff_time}s before retry (attempt {attempt + 1}/{max_retries + 1})...")
                time.sleep(backoff_time)

                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to obtain valid response from Groq API after {max_retries + 1} attempts. Last error: {last_error}"
                    ) from e

        raise RuntimeError("Groq API call failed unexpectedly.")
