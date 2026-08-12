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

class PureVisualStepDecision(BaseModel):
    """Unified single-call step decision combining human requirement detection and visual action selection."""
    reasoning: str = Field(
        default="Analyzing visual screenshot context.",
        description="Visual analysis of page elements and target coordinate calculation."
    )
    human_required: bool = Field(
        default=False,
        description="True if page requires human intervention (login form, CAPTCHA challenge, 2FA prompt, payment screen)."
    )
    requirement_type: Optional[Literal["login", "captcha", "2fa", "payment", "other"]] = Field(
        default=None,
        description="Type of human intervention if human_required is True."
    )
    action: Literal["click", "type", "batch_type", "select", "key", "scroll", "download", "ask_human", "done"] = Field(
        ...,
        description="The physical visual action to execute."
    )
    x: Optional[int] = Field(None, description="Center X coordinate at 1280x800 resolution.")
    y: Optional[int] = Field(None, description="Center Y coordinate at 1280x800 resolution.")
    selector: Optional[str] = Field(None)
    text: Optional[str] = Field(None)
    value: Optional[str] = Field(None)
    key: Optional[str] = Field(None)
    direction: Optional[Literal["up", "down", "left", "right"]] = Field(None)
    batch_inputs: Optional[List[Dict[str, Any]]] = Field(None, description="List of form input fields to batch fill in a single step e.g. [{'x': 100, 'y': 200, 'text': 'john.doe@example.com'}]")

class PureVisualActionDecision(PureVisualStepDecision):
    """Alias for backwards compatibility."""
    pass

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

class HumanRequiredDetection(BaseModel):
    """Pydantic schema for detecting human login, CAPTCHA, 2FA, or payment intervention requirements."""
    human_required: bool = Field(..., description="True if page requires human to log in, solve CAPTCHA, enter 2FA, or pay.")
    requirement_type: Optional[Literal["login", "captcha", "2fa", "payment", "other"]] = Field(
        None, description="Type of human intervention detected."
    )
    reasoning: str = Field(..., description="Explanation of why human intervention is required.")

class GoalSelfAssessment(BaseModel):
    """Pydantic schema for agent goal completion self-assessment."""
    completion_status: Literal["fully_met", "partially_met", "not_met"] = Field(
        ..., description="Self-assessment of user goal completion status."
    )
    accomplishment_summary: str = Field(..., description="Plain text summary of what was accomplished during the run.")
    detailed_explanation: str = Field(..., description="Detailed explanation supporting the completion status.")

class VisualActionDecision(PureVisualStepDecision):
    """Alias for backwards compatibility."""
    thought: Optional[str] = Field(None)

class ActionDecision(BaseModel):
    """Schema supporting DOM perception and fallback calls."""
    action: Literal["click", "click_coordinate", "type", "select", "key", "scroll", "download", "ask_human", "wait", "done"] = Field(
        ..., description="The action type to perform."
    )
    selector: Optional[str] = Field(default=None)
    x: Optional[int] = Field(default=None)
    y: Optional[int] = Field(default=None)
    text: Optional[str] = Field(default=None)
    value: Optional[str] = Field(default=None)
    key: Optional[str] = Field(default=None)
    reasoning: Optional[str] = Field(default="Executing next action step.")

SYSTEM_PROMPT_UNIFIED = """You are a pure visual computer-use agent controlling a web browser strictly via screenshots at 1280x800 resolution.

USER PROFILE VAULT CONTEXT:
{vault_context}

CRITICAL INSTRUCTIONS:
1. Examine the screenshot for human intervention requirements first:
   - Set 'human_required' to true if page presents an account login form, CAPTCHA puzzle, 2FA code prompt, or checkout payment screen. Set 'requirement_type' to 'login', 'captcha', '2fa', or 'payment'.
2. If no human intervention is required, calculate center (x, y) coordinates for the next physical visual action:
   - Overlay grid with 100px red lines & labels (e.g. '100,200') is rendered on the image to help calculate exact coordinates [0..1279 X, 0..799 Y].
   - 'type': specify center (x, y) and 'text' value to type. Reference USER PROFILE VAULT CONTEXT.
   - 'batch_type': if multiple input fields are visible on the page (e.g. forms, registration, checkout, multi-field tests), specify action 'batch_type' and provide 'batch_inputs' array containing all field entries `[{"x": center_x, "y": center_y, "text": "profile_vault_key_or_value"}, ...]` to fill out ALL form fields across the page in a single step! Match all detected form fields against USER PROFILE VAULT CONTEXT (First Name, Middle Name, Last Name, Full Name, Company, Address, City, Country, Phone, Email, etc.) in a unified plan.
   - 'click': specify center (x, y).
   - 'select': specify center (x, y) and 'value'.
   - 'key': specify 'key' name ('Enter', 'Tab', 'Escape').
   - 'scroll': set 'direction' ('down' / 'up').
   - 'download': specify center (x, y) of download link/button.
   - 'ask_human': choose if stuck or uncertain.
   - 'done': choose when user objective is complete.
3. Output strictly valid JSON matching schema:
{{
  "reasoning": "<visual analysis>",
  "human_required": true | false,
  "requirement_type": "login" | "captcha" | "2fa" | "payment" | null,
  "action": "click" | "type" | "batch_type" | "select" | "key" | "scroll" | "download" | "ask_human" | "done",
  "x": 640 or null,
  "y": 400 or null,
  "text": "string" or null,
  "value": "string" or null,
  "key": "Enter" or null,
  "direction": "down" or null,
  "batch_inputs": [{"x": 100, "y": 200, "text": "value"}] or null
}}
Do NOT output any markdown formatting or extra text outside the JSON object.
"""

SYSTEM_PROMPT_VISUAL = SYSTEM_PROMPT_UNIFIED

SYSTEM_PROMPT_HUMAN_DETECT = """You are a visual browser security and authentication detector. Examine the page screenshot to determine if a human user is required to intervene.

DETECTION CRITERIA:
- 'login': Page requires logging into a user account (e.g. Google, Amazon, Bank, OAuth, password prompt).
- 'captcha': Page presents a CAPTCHA challenge (reCAPTCHA, hCaptcha, Cloudflare turnstile, image puzzle).
- '2fa': Page requires an SMS code, authenticator app OTP, or security key prompt.
- 'payment': Page requests credit card, bank details, or checkout payment authorization.

Output strictly valid JSON matching schema:
{{
  "human_required": true | false,
  "requirement_type": "login" | "captcha" | "2fa" | "payment" | "other" | null,
  "reasoning": "<brief explanation of why human action is or is not required>"
}}
"""

SYSTEM_PROMPT_ASSESSMENT = """You are an objective AI quality auditor evaluating the execution trajectory of a browser automation agent.

User Goal: "{goal}"

Review the attached final screenshot and the execution history summary. Evaluate whether the agent successfully accomplished the user's objective.

Output strictly valid JSON matching schema:
{{
  "completion_status": "fully_met" | "partially_met" | "not_met",
  "accomplishment_summary": "<concise plain-text summary of what was accomplished>",
  "detailed_explanation": "<detailed visual and step-by-step evidence supporting the evaluation>"
}}
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
5. "key": Press a hardware key ('Enter', 'Tab', 'Escape').
6. "scroll": Scroll page down or up.
7. "download": Trigger a file download.
8. "ask_human": Proactively request human help if stuck.
9. "wait": Pause 2 seconds.
10. "done": Declare completion.

Output strictly valid JSON matching this schema:
{{
  "action": "click" | "click_coordinate" | "type" | "select" | "key" | "scroll" | "download" | "ask_human" | "wait" | "done",
  "selector": "<exact locator string or null>",
  "x": null,
  "y": null,
  "text": "<text to enter if action is type else null>",
  "value": "<option value/label to choose if action is select else null>",
  "key": "<key name if key action else null>",
  "reasoning": "<short sentence explaining why>"
}}
"""

class ReasonerAgent(BaseAgent):
    """LLM Reasoner agent supporting Pure Visual Computer-Use, Single-Call Unified Decision, Human Handoff Detection, Self-Assessment, and DOM reasoning."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        text_model: Optional[str] = None,
        vision_model: Optional[str] = None,
        vault: Optional[ContextVault] = None
    ):
        super().__init__(api_key=api_key, text_model=text_model, vision_model=vision_model)
        self.vault = vault or ContextVault()

    def _decide_step_dom_fallback(
        self,
        goal: str,
        visual_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """
        DOM-aware text-only fallback used when vision quota is exhausted.
        Uses page URL, title, and vault context to produce a valid coordinate action
        without requiring a screenshot. Coordinates are based on known page layouts.
        """
        vault_context = self.vault.get_context_for_prompt()
        current_url = visual_state.get("current_url", "N/A")
        page_title = visual_state.get("page_title", "N/A")
        vw = visual_state.get("viewport_width", 1280)
        vh = visual_state.get("viewport_height", 800)

        dom_system_prompt = f"""You are a browser automation agent. Vision is unavailable.
Use your knowledge of common web page layouts and the page URL/title to determine the next action.

USER PROFILE VAULT CONTEXT:
{vault_context}

Rules:
- For login pages: type username at approx (640, 330), type password at approx (640, 395), click Login/Submit at approx (640, 450).
- Use vault context for username/password values.
- Choose action=done only when goal is fully achieved based on history.
- Output ONLY valid JSON, no markdown.

JSON schema:
{{
  "reasoning": "<why this action>",
  "human_required": false,
  "requirement_type": null,
  "action": "click" | "type" | "key" | "scroll" | "done",
  "x": null,
  "y": null,
  "text": null,
  "value": null,
  "key": null,
  "direction": null
}}"""

        dom_user_message = (
            f"Goal: \"{goal}\"\n"
            f"Page URL: {current_url}\n"
            f"Page Title: {page_title}\n"
            f"Viewport: {vw}x{vh}\n"
            f"History:\n{history_summary}\n\n"
            "Vision model is unavailable (quota exhausted). "
            "Use page URL/title and vault context to decide the next best action. "
            "Output strictly valid JSON."
        )

        logger.warning("Vision unavailable - using DOM-aware text-only fallback for step decision.")
        raw = self.call_llm(
            system_prompt=dom_system_prompt,
            user_message=dom_user_message,
            expect_json=True,
            image_path=None
        )
        decision_obj = PureVisualStepDecision(**raw)
        result = decision_obj.model_dump()

        if result["action"] == "type" and result.get("text"):
            resolved = self.vault.resolve_field(result["text"])
            if resolved:
                logger.info(f"[DOM Fallback] Resolved vault field '{result['text']}' -> '{resolved}'")
                result["text"] = resolved

        logger.info(
            f"[DOM Fallback] Action={result['action']} | Coords=({result.get('x')}, {result.get('y')}) | "
            f"Reasoning: {result['reasoning'][:60]}..."
        )
        return result

    def decide_visual_step(
        self,
        goal: str,
        visual_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """
        OPTIMIZED SINGLE-CALL VISUAL DECISION:
        Combines human requirement detection (login/CAPTCHA) AND visual coordinate action selection in a SINGLE Groq API call.
        Halves per-step LLM latency.
        """
        vw = visual_state.get("viewport_width", 1280)
        vh = visual_state.get("viewport_height", 800)
        screenshot_path = visual_state.get("screenshot_path")
        vault_context = self.vault.get_context_for_prompt()

        system_prompt = SYSTEM_PROMPT_UNIFIED.format(vault_context=vault_context)

        user_message = f"""User Goal: "{goal}"

Current Page URL: {visual_state.get('current_url', 'N/A')}
Current Page Title: {visual_state.get('page_title', 'N/A')}
Viewport Resolution: {vw}x{vh} pixels

Execution History (Last 5 steps):
{history_summary}

Analyze the attached screenshot. First check if human login/CAPTCHA/2FA is required.
If not required, determine exact pixel coordinates (x, y) at 1280x800 resolution for the next physical visual action.
Output strictly valid JSON matching schema.
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
                decision_obj = PureVisualStepDecision(**raw_decision)
                result = decision_obj.model_dump()

                if result["action"] == "type" and result.get("text"):
                    resolved = self.vault.resolve_field(result["text"])
                    if resolved:
                        logger.info(f"Resolved vault field text '{result['text']}' -> '{resolved}'")
                        result["text"] = resolved
                elif result["action"] == "batch_type" and result.get("batch_inputs"):
                    for item in result["batch_inputs"]:
                        if isinstance(item, dict) and item.get("text"):
                            resolved = self.vault.resolve_field(item["text"])
                            if resolved:
                                logger.info(f"Resolved batch vault field text '{item['text']}' -> '{resolved}'")
                                item["text"] = resolved

                logger.info(
                    f"Unified Visual Step Decision: HumanReq={result.get('human_required')} | "
                    f"Action={result['action']} | Coords=({result.get('x')}, {result.get('y')}) | "
                    f"Reasoning: {result['reasoning'][:60]}..."
                )
                return result
            except ValidationError as ve:
                logger.warning(f"Pydantic Unified Visual validation failed (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    logger.warning("All visual attempts failed validation - trying DOM-aware fallback...")
                    try:
                        return self._decide_step_dom_fallback(goal, visual_state, history_summary)
                    except Exception as dom_err:
                        logger.error(f"DOM fallback also failed: {dom_err}")
                        raise RuntimeError(f"Unified visual step decision failed validation: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Output valid JSON with fields: reasoning, human_required, action, x, y, text, key.]"
            except Exception as e:
                error_str = str(e)
                logger.error(f"Error in unified visual step decision: {error_str}")
                if ("rate_limit" in error_str.lower() or "429" in error_str or
                        "limit reached" in error_str.lower() or "quota" in error_str.lower()):
                    logger.warning("Vision quota exhausted - trying DOM-aware fallback...")
                    try:
                        return self._decide_step_dom_fallback(goal, visual_state, history_summary)
                    except Exception as dom_err:
                        logger.error(f"DOM fallback also failed: {dom_err}")
                raise

        raise RuntimeError("Failed to generate valid unified visual step decision.")

    def detect_human_required(self, visual_state: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Legacy separate detection wrapper calling decide_visual_step."""
        step_res = self.decide_visual_step(
            goal="Check human requirement",
            visual_state=visual_state,
            history_summary=""
        )
        return step_res.get("human_required", False), step_res.get("requirement_type") or "login", step_res.get("reasoning", "")

    def decide_visual_action(
        self,
        goal: str,
        visual_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """Legacy separate action decision wrapper calling decide_visual_step."""
        return self.decide_visual_step(goal=goal, visual_state=visual_state, history_summary=history_summary)

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
                
                full_x = int(round(crop_left + (crop_obj.crop_x / 2.0)))
                full_y = int(round(crop_top + (crop_obj.crop_y / 2.0)))

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

    def assess_goal_completion(
        self,
        goal: str,
        history_summary: str,
        visual_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Performs self-assessment of user goal completion status (fully_met, partially_met, not_met).
        Returns dictionary with completion_status, accomplishment_summary, and detailed_explanation.
        """
        screenshot_path = visual_state.get("screenshot_path")
        system_prompt = SYSTEM_PROMPT_ASSESSMENT.format(goal=goal)

        user_msg = f"""User Objective Goal: "{goal}"
Final Page URL: {visual_state.get('current_url', 'N/A')}
Final Page Title: {visual_state.get('page_title', 'N/A')}

Full Trajectory Execution History:
{history_summary}

Analyze the final visual screenshot and step history. Output strictly valid JSON matching schema:
{{"completion_status": "fully_met"|"partially_met"|"not_met", "accomplishment_summary": "...", "detailed_explanation": "..."}}
"""
        try:
            raw_res = self.call_llm(
                system_prompt=system_prompt,
                user_message=user_msg,
                expect_json=True,
                image_path=screenshot_path
            )
            assessment = GoalSelfAssessment(**raw_res)
            logger.info(f"Goal Self-Assessment: Status={assessment.completion_status} | Summary: {assessment.accomplishment_summary[:80]}...")
            return assessment.model_dump()
        except Exception as e:
            logger.warning(f"Goal self-assessment call failed: {e}. Utilizing graceful fallback assessment.")
            return {
                "completion_status": "unknown",
                "accomplishment_summary": "Assessment unavailable.",
                "detailed_explanation": f"Assessment unavailable - API returned empty response: {e}"
            }

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

Analyze the current page state, goal, and past actions. Choose action from: "click", "click_coordinate", "type", "select", "key", "scroll", "download", "ask_human", "wait", "done".
Output strictly valid JSON with keys: "action", "selector", "x", "y", "text", "value", "key", "reasoning".
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
        return self.decide_visual_step(goal=goal, visual_state=visual_state, history_summary=history_summary)
