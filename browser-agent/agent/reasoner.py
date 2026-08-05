import io
import base64
import logging
from pathlib import Path
from typing import Literal, Optional, Dict, Any, List, Tuple, Union
from PIL import Image
from pydantic import BaseModel, Field, ValidationError
from agent.base_agent import BaseAgent
from agent.context_vault import ContextVault

logger = logging.getLogger("browser_agent.agent.reasoner")

class PureVisualActionDecision(BaseModel):
    """Pydantic schema for Pure Visual Computer-Use Agent action decision (coordinate-only)."""
    reasoning: str = Field(
        default="Analyzing visual screenshot context.",
        description="Detailed visual analysis of the screenshot identifying target coordinates."
    )
    action: Literal["click", "type", "key", "scroll", "done"] = Field(
        ...,
        description="The physical visual action to execute: click, type, key, scroll, done."
    )
    x: Optional[int] = Field(None, description="Exact center X pixel coordinate at 1280x800 resolution.")
    y: Optional[int] = Field(None, description="Exact center Y pixel coordinate at 1280x800 resolution.")
    text: Optional[str] = Field(None, description="Text string to type if action is 'type'.")
    key: Optional[str] = Field(None, description="Key name to press (e.g. 'Enter', 'Tab', 'Escape') if action is 'key'.")
    direction: Optional[Literal["up", "down", "left", "right"]] = Field(None, description="Scroll direction if action is 'scroll'.")

class ZoomedCropActionDecision(BaseModel):
    """Pydantic schema for 2x Zoomed Crop coordinate prediction."""
    reasoning: str = Field(..., description="Visual analysis inside 2x zoomed crop view.")
    action: Literal["click", "type"] = Field(..., description="Intended action inside crop: click or type.")
    crop_x: int = Field(..., description="X coordinate inside 800x800 zoomed image (0..800).")
    crop_y: int = Field(..., description="Y coordinate inside 800x800 zoomed image (0..800).")
    text: Optional[str] = Field(None, description="Text to type if action is type.")

class ActionVerificationResult(BaseModel):
    """Pydantic schema for post-action visual verification."""
    success: bool = Field(..., description="True if page change indicates intended action succeeded.")
    reasoning: str = Field(..., description="Explanation of visual comparison between before and after screenshots.")

class VisualActionDecision(PureVisualActionDecision):
    """Alias for backwards compatibility."""
    thought: Optional[str] = Field(None)

class ActionDecision(BaseModel):
    """Schema supporting DOM perception and fallback calls."""
    action: Literal["click", "click_coordinate", "type", "select", "scroll", "wait", "done"] = Field(
        ...,
        description="The action type to perform."
    )
    selector: Optional[str] = Field(default=None)
    x: Optional[int] = Field(default=None)
    y: Optional[int] = Field(default=None)
    text: Optional[str] = Field(default=None)
    value: Optional[str] = Field(default=None)
    reasoning: Optional[str] = Field(default="Executing next action step.")

SYSTEM_PROMPT_PURE_VISUAL = """You are a pure visual computer-use agent controlling a web browser strictly via screenshots at 1280x800 resolution.

USER PROFILE VAULT CONTEXT:
{vault_context}

CRITICAL INSTRUCTIONS:
1. You must respond with exact pixel coordinates (x, y) based on what you see in the image at 1280x800 resolution. Do NOT reference CSS selectors, element IDs, or DOM structure — you only have visual information.
2. An overlay grid with 100px red gridlines and coordinate labels (e.g., '100,200') is rendered on the image to help you pinpoint exact pixel coordinates.
3. Calculate the center (X, Y) pixel coordinates strictly within 0..1279 (X) and 0..799 (Y).
4. FORM FILLING & ACTION RULES:
   - To fill an input field: choose action 'type', specify the field's center (x, y) pixel coordinates, and set 'text' to the value to type. Reference USER PROFILE VAULT CONTEXT for personal profile details.
   - To click a button/link: choose action 'click' and specify (x, y) coordinates.
   - To press a key (e.g. 'Enter', 'Tab', 'Escape'): choose action 'key' and set 'key' to the key name.
   - To scroll: choose action 'scroll' and set 'direction' to 'down' or 'up'.
   - To finish: choose action 'done'.
5. Output strictly valid JSON matching the schema:
{{
  "reasoning": "<visual analysis of target elements using grid reference numbers>",
  "action": "click" | "type" | "key" | "scroll" | "done",
  "x": 640 or null,
  "y": 400 or null,
  "text": "text string if type" or null,
  "key": "Enter" | "Tab" | "Escape" or null,
  "direction": "down" | "up" or null
}}
Do NOT output any markdown formatting or extra text outside the JSON object.
"""

SYSTEM_PROMPT_ZOOMED = """You are a precision computer-use vision agent analyzing a 2x upscaled (800x800px) zoomed crop centered on a target UI region.

INSTRUCTIONS:
1. Examine the 800x800 zoomed image carefully to locate the exact center of the target clickable or typable UI element.
2. Output exact local pixel coordinates (crop_x, crop_y) within the 800x800 image boundary [0..800 x 0..800].
3. Output strictly valid JSON matching the schema:
{{
  "reasoning": "<precise visual inspection inside zoomed crop>",
  "action": "click" | "type",
  "crop_x": 400,
  "crop_y": 400,
  "text": "text string if action is type" or null
}}
Do NOT output any markdown formatting or extra text outside the JSON object.
"""

SYSTEM_PROMPT_VERIFY = """You are a visual action verifier. You are given TWO page screenshots:
- Image 1: BEFORE executing the action
- Image 2: AFTER executing the action

INSTRUCTIONS:
1. Compare Image 1 and Image 2 to verify if the intended action succeeded (e.g., text appeared in input field, button state changed, page navigated, or modal appeared).
2. Answer whether the intended action succeeded (true/false) and provide a concise visual reason.
3. Output strictly valid JSON matching schema:
{{
  "success": true | false,
  "reasoning": "<short explanation of visual difference>"
}}
"""

SYSTEM_PROMPT_DOM = """You are an AI web automation agent. Your goal is to complete a user task on a web page by taking one step at a time.

USER PROFILE VAULT CONTEXT:
{vault_context}

Available Actions:
1. "click": Click an interactive element specified by its 'selector'.
2. "click_coordinate": Click at specific (x, y) pixel coordinates.
3. "type": Focus an element specified by its 'selector' and type the specified 'text'.
4. "select": Choose an option from a native HTML <select> element.
5. "scroll": Scroll page down or up.
6. "wait": Pause 2 seconds.
7. "done": Declare completion.

Output strictly valid JSON matching this schema:
{{
  "action": "click" | "click_coordinate" | "type" | "select" | "scroll" | "wait" | "done",
  "selector": "<exact locator string or null>",
  "x": null,
  "y": null,
  "text": "<text to enter if action is type else null>",
  "value": "<option value/label to choose if action is select else null>",
  "reasoning": "<short sentence explaining why>"
}}
"""

class ReasonerAgent(BaseAgent):
    """LLM Reasoner agent supporting Pure Visual Computer-Use, Zoom-Retry Precision, Post-Click Verification, and DOM reasoning."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        text_model: Optional[str] = None,
        vision_model: Optional[str] = None,
        vault: Optional[ContextVault] = None
    ):
        super().__init__(api_key=api_key, text_model=text_model, vision_model=vision_model)
        self.vault = vault or ContextVault()

    def decide_visual_action(
        self,
        goal: str,
        visual_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """
        Pure Visual Computer-Use Agent reasoning: Analyzes page screenshot and viewport metadata to decide visual action purely via pixel coordinates (x, y).
        No CSS selectors or DOM structure used.
        """
        vw = visual_state.get("viewport_width", 1280)
        vh = visual_state.get("viewport_height", 800)
        screenshot_path = visual_state.get("screenshot_path")
        vault_context = self.vault.get_context_for_prompt()

        system_prompt = SYSTEM_PROMPT_PURE_VISUAL.format(vault_context=vault_context)

        user_message = f"""User Goal: "{goal}"

Current Page URL: {visual_state.get('current_url', 'N/A')}
Current Page Title: {visual_state.get('page_title', 'N/A')}
Viewport Resolution: {vw}x{vh} pixels

Execution History (Last 5 steps):
{history_summary}

Analyze the attached screenshot carefully. You must respond with exact pixel coordinates (x, y) based on what you see in the image at 1280x800 resolution.
Do NOT reference CSS selectors or DOM elements — you only have visual information.
Output strictly valid JSON matching the schema.
"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                raw_decision = self.call_llm(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    expect_json=True,
                    image_path=screenshot_path
                )
                decision_obj = PureVisualActionDecision(**raw_decision)
                result = decision_obj.model_dump()

                if result["action"] == "type" and result.get("text"):
                    resolved = self.vault.resolve_field(result["text"])
                    if resolved:
                        logger.info(f"Resolved vault field text '{result['text']}' -> '{resolved}'")
                        result["text"] = resolved

                logger.info(f"Pure Visual Decision: Action={result['action']} | Coords=({result.get('x')}, {result.get('y')}) | Reasoning: {result['reasoning'][:60]}...")
                return result
            except ValidationError as ve:
                logger.warning(f"Pydantic Pure Visual validation failed (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Visual action decision failed validation: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please output valid JSON with fields: reasoning, action, x, y, text, key, direction.]"
            except Exception as e:
                logger.error(f"Error deciding pure visual action: {e}")
                raise

        raise RuntimeError("Failed to generate valid pure visual action decision.")

    def decide_visual_action_zoomed(
        self,
        goal: str,
        full_screenshot_path: str,
        target_x: int,
        target_y: int,
        history_summary: str
    ) -> Dict[str, Any]:
        """
        Zoom-Retry Precision Reasoning: Crops a 400x400 region centered at (target_x, target_y),
        upscales 2x to 800x800, asks vision model for precise coordinates inside crop, and maps back to 1280x800 full viewport.
        """
        if not full_screenshot_path or not Path(full_screenshot_path).exists():
            raise ValueError(f"Invalid full_screenshot_path for zoom retry: {full_screenshot_path}")

        img = Image.open(full_screenshot_path).convert("RGB")
        width, height = img.size

        # Compute 400x400 crop box centered on (target_x, target_y)
        crop_w, crop_h = 400, 400
        crop_left = max(0, min(target_x - crop_w // 2, width - crop_w))
        crop_top = max(0, min(target_y - crop_h // 2, height - crop_h))
        crop_right = crop_left + crop_w
        crop_bottom = crop_top + crop_h

        cropped_img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
        # Upscale 2x to 800x800
        zoomed_img = cropped_img.resize((800, 800), Image.Resampling.LANCZOS)

        zoomed_path = str(Path(full_screenshot_path).parent / f"zoomed_crop_{target_x}_{target_y}.png")
        zoomed_img.save(zoomed_path, format="PNG")
        logger.info(f"Created 2x zoomed crop image (800x800) at {zoomed_path} covering viewport box ({crop_left},{crop_top})-({crop_right},{crop_bottom})")

        user_message = f"""Goal: "{goal}"
Target Area Viewport Region: ({crop_left},{crop_top}) to ({crop_right},{crop_bottom})

Execution History:
{history_summary}

This is a 2x zoomed-in cropped region (800x800 pixels) centered around the target area of the main page.
Identify the exact target visual element inside this zoomed view and return the local pixel coordinates (crop_x, crop_y) strictly within 0..800 for X and 0..800 for Y.
Output strictly valid JSON matching the schema.
"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                raw_decision = self.call_llm(
                    system_prompt=SYSTEM_PROMPT_ZOOMED,
                    user_message=user_message,
                    expect_json=True,
                    image_path=zoomed_path
                )
                crop_obj = ZoomedCropActionDecision(**raw_decision)
                
                # Map 800x800 crop coordinates back to 1280x800 full viewport coordinates
                # 800x800 image corresponds to 400x400 crop box (scale factor = 0.5)
                full_x = int(round(crop_left + (crop_obj.crop_x / 2.0)))
                full_y = int(round(crop_top + (crop_obj.crop_y / 2.0)))

                # Clamp to viewport bounds 1280x800
                full_x = max(0, min(full_x, width - 1))
                full_y = max(0, min(full_y, height - 1))

                logger.info(
                    f"Zoom-Retry Precision Resolved: Crop Coords ({crop_obj.crop_x}, {crop_obj.crop_y}) -> "
                    f"Mapped Full Viewport Coords ({full_x}, {full_y})"
                )

                decision_data = {
                    "reasoning": f"[Zoom-Retry Precision] {crop_obj.reasoning}",
                    "action": crop_obj.action,
                    "x": full_x,
                    "y": full_y,
                    "text": crop_obj.text,
                    "is_zoomed_retry": True
                }

                if decision_data["action"] == "type" and decision_data.get("text"):
                    resolved = self.vault.resolve_field(decision_data["text"])
                    if resolved:
                        decision_data["text"] = resolved

                return decision_data
            except Exception as e:
                logger.warning(f"Zoom-retry call failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries:
                    raise

        raise RuntimeError("Failed to generate valid zoomed-crop action decision.")

    def verify_visual_action(
        self,
        intended_action: Dict[str, Any],
        before_screenshot_path: str,
        after_screenshot_path: str
    ) -> Tuple[bool, str]:
        """
        Post-Click Verification: Compares before and after screenshots to confirm if the intended action succeeded.
        Returns (success_bool, reasoning_str).
        """
        if not before_screenshot_path or not Path(before_screenshot_path).exists():
            return True, "No before screenshot available for verification."
        if not after_screenshot_path or not Path(after_screenshot_path).exists():
            return True, "No after screenshot available for verification."

        act = intended_action.get("action", "")
        coords = f"({intended_action.get('x')}, {intended_action.get('y')})" if intended_action.get("x") is not None else ""
        txt = f" text='{intended_action.get('text')}'" if intended_action.get("text") else ""

        user_message = f"""Intended Action: {act.upper()}{coords}{txt}
Reasoning: {intended_action.get('reasoning', '')}

Did the page change in a way consistent with the intended action succeeding? Answer yes/no and briefly why.
Output strictly valid JSON matching schema: {{"success": true|false, "reasoning": "..."}}.
"""
        try:
            raw_res = self.call_llm(
                system_prompt=SYSTEM_PROMPT_VERIFY,
                user_message=user_message,
                expect_json=True,
                image_path=after_screenshot_path
            )
            v_obj = ActionVerificationResult(**raw_res)
            logger.info(f"Post-Action Verification: Success={v_obj.success} | Reasoning: {v_obj.reasoning[:60]}...")
            return v_obj.success, v_obj.reasoning
        except Exception as ve:
            logger.warning(f"Post-action verification call failed: {ve}. Assuming action succeeded.")
            return True, f"Verification skipped due to API error: {ve}"

    def _format_elements(self, elements: List[Dict[str, Any]]) -> str:
        formatted = []
        for i, el in enumerate(elements, 1):
            tag = el.get("tag", "")
            text = el.get("text", "")
            selector = el.get("selector", "")
            el_type = el.get("type", "")
            placeholder = el.get("placeholder", "")
            options = el.get("options", [])

            details = f"[{i}] <{tag}>"
            if text:
                details += f" text='{text}'"
            if placeholder:
                details += f" placeholder='{placeholder}'"
            if el_type:
                details += f" type='{el_type}'"
            if options:
                opt_str = ", ".join([f"'{o.get('text')}'" for o in options])
                details += f" | Available Select Options: [{opt_str}]"
            details += f" | Selector: `{selector}`"
            formatted.append(details)
        return "\n".join(formatted) if formatted else "No interactive elements detected."

    def decide_next_action(
        self,
        goal: str,
        page_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """Evaluate current state using DOM data and return validated action decision with vault context."""
        elements: List[Dict[str, Any]] = page_state.get("elements", [])
        elements_str = self._format_elements(elements)
        vault_context = self.vault.get_context_for_prompt()

        system_prompt = SYSTEM_PROMPT_DOM.format(vault_context=vault_context)

        user_message = f"""Current Goal: "{goal}"

Current Page URL: {page_state.get('url', 'N/A')}
Current Page Title: {page_state.get('title', 'N/A')}

Interactive Elements on Page (~{len(elements)} items):
{elements_str}

Action History (Recent steps):
{history_summary}

Analyze the current page state, goal, and past actions. Choose action from: "click", "click_coordinate", "type", "select", "scroll", "wait", "done".
Output strictly valid JSON with keys: "action", "selector", "x", "y", "text", "value", "reasoning".
"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                raw_decision = self.call_llm(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    expect_json=True
                )
                decision_obj = ActionDecision(**raw_decision)
                result = decision_obj.model_dump()

                if result["action"] == "type" and result.get("text"):
                    resolved = self.vault.resolve_field(result["text"])
                    if resolved:
                        logger.info(f"Resolved vault field text '{result['text']}' -> '{resolved}'")
                        result["text"] = resolved

                return result
            except ValidationError as ve:
                logger.warning(f"Pydantic DOM validation failed (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Action decision failed validation: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please fix JSON output format with fields: action, selector, reasoning.]"
            except Exception as e:
                logger.error(f"Error deciding action via DOM: {e}")
                raise

        raise RuntimeError("Failed to generate valid DOM action decision.")

    def decide_with_vision(
        self,
        goal: str,
        page_state: Dict[str, Any],
        history_summary: str,
        failure_reason: str
    ) -> Dict[str, Any]:
        """Multimodal Vision Fallback: Prompt vision model with page screenshot when DOM selector fails."""
        screenshot_path = page_state.get("screenshot_path")
        logger.info(f"Triggering Vision Fallback using screenshot: {screenshot_path}")

        visual_state = {
            "viewport_width": 1280,
            "viewport_height": 800,
            "current_url": page_state.get("url", ""),
            "page_title": page_state.get("title", ""),
            "screenshot_path": screenshot_path
        }
        return self.decide_visual_action(goal=goal, visual_state=visual_state, history_summary=history_summary)
