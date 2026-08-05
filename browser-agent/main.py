import os
import sys
import json
import time
import uuid
import logging
import argparse
import base64
from pathlib import Path
from typing import Dict, Any, Optional, Callable

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure UTF-8 output encoding on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config.settings import check_api_key, validate_config
from browser.controller import BrowserController, extract_domain
from browser.perception import DOMPerception, capture_visual_state
from browser.actions import execute_visual_action, execute_action
from agent.reasoner import ReasonerAgent
from agent.memory import StepMemory
from agent.context_vault import ContextVault

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("browser_agent.main")

def run_agent(
    goal: str,
    url: str,
    max_steps: int = 15,
    headless: bool = False,
    mode: str = "visual",
    session_file: Optional[str] = None,
    disable_vision: bool = False,
    grid_overlay: bool = True,
    task_id: Optional[str] = None,
    vault: Optional[ContextVault] = None,
    step_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Dict[str, Any]:
    """
    Generalized entry point executing browser agent control loop for ANY user goal on ANY website,
    with human-handoff for login/CAPTCHA steps, session state persistence, and self-assessment.
    """
    check_api_key()

    active_mode = mode.lower()
    if disable_vision:
        active_mode = "dom"

    active_task_id = task_id or str(uuid.uuid4())[:8]
    logs_dir = Path(__file__).resolve().parent / "logs"
    os.makedirs(logs_dir, exist_ok=True)

    controller = BrowserController(width=1280, height=800, default_timeout_ms=20000)

    # Session Auto-Detection & Resolution
    active_session = session_file
    if not active_session:
        active_session = controller.get_session_path_for_url(url)

    mode_label = {
        "visual": f"Pure Visual Computer-Use Agent (1280x800, Grid={grid_overlay})",
        "dom": "Pure DOM Perception Agent",
        "hybrid": "Hybrid DOM + Vision Fallback Agent"
    }.get(active_mode, f"Mode: {active_mode}")

    print("\n" + "=" * 70)
    print(f"🤖 BROWSER AGENT INITIALIZED [{mode_label}]")
    print(f"🎯 Goal: {goal}")
    print(f"🌐 Starting URL: {url}")
    print(f"🔑 Session State: {active_session or 'None (Fresh Session)'}")
    print(f"⚙️  Max Steps: {max_steps} | Headless: {headless} | Mode: {active_mode}")
    print("=" * 70 + "\n")

    context_vault = vault or ContextVault()
    perception = DOMPerception()
    reasoner = ReasonerAgent(vault=context_vault)
    memory = StepMemory()

    final_status = "In progress"
    self_assessment = None

    try:
        controller.start(headless=headless, session_file=active_session)
        controller.goto(url)

        for step in range(1, max_steps + 1):
            print(f"\n--- [STEP {step}/{max_steps}] ---")

            screenshot_name = f"step_{step}.png"
            screenshot_path = str(logs_dir / screenshot_name)

            history_summary = memory.get_summary()
            used_vision = False

            if active_mode == "visual":
                visual_state = capture_visual_state(
                    controller,
                    screenshot_path=screenshot_path,
                    grid_overlay=grid_overlay
                )

                print(f"📍 Page URL: {visual_state['current_url']}")
                print(f"📄 Page Title: {visual_state['page_title']}")
                print(f"📸 Visual Screenshot saved: {screenshot_path}")

                # --- HUMAN HANDOFF DETECTION (Login / CAPTCHA / 2FA / Payment) ---
                human_req, req_type, req_reason = reasoner.detect_human_required(visual_state)
                if human_req:
                    print("\n" + "⏸" * 35)
                    print(f"⏸ HUMAN ACTION NEEDED: [{req_type.upper()}] DETECTED!")
                    print(f"⏸ Reason: {req_reason}")
                    print("⏸ Please complete this action directly in the browser window.")
                    print("⏸ Press ENTER here in the terminal once done to resume agent execution...")
                    print("⏸" * 35 + "\n")

                    controller.ensure_headed_mode()
                    if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                        try:
                            input(">> Press ENTER to continue after completing human action... ")
                        except (EOFError, KeyboardInterrupt):
                            time.sleep(1.0)
                    else:
                        logger.info("Non-interactive environment detected. Skipping terminal input() wait.")

                    # Persist session state after manual login/CAPTCHA resolution
                    saved_sess = controller.save_session(url)
                    print(f"💾 Session state saved to {saved_sess}")

                    # Re-capture updated visual state after human intervention
                    visual_state = capture_visual_state(
                        controller,
                        screenshot_path=screenshot_path,
                        grid_overlay=grid_overlay
                    )

                # Check if zoom-retry recovery should trigger due to prior failure or loop
                if memory.should_trigger_zoom_retry() and memory.history:
                    last_entry = memory.history[-1]
                    last_x = last_entry.get("x") or 640
                    last_y = last_entry.get("y") or 400
                    print(f"🔍 TRIGGERING 2X ZOOM-RETRY RECOVERY centered on ({last_x}, {last_y})...")
                    try:
                        action_decision = reasoner.decide_visual_action_zoomed(
                            goal=goal,
                            full_screenshot_path=screenshot_path,
                            target_x=last_x,
                            target_y=last_y,
                            history_summary=history_summary
                        )
                        memory.record_zoom_retry_attempt()
                        used_vision = True
                    except Exception as ze:
                        logger.warning(f"Zoom-retry call failed: {ze}. Falling back to standard visual decision...")
                        action_decision = reasoner.decide_visual_action(
                            goal=goal,
                            visual_state=visual_state,
                            history_summary=history_summary
                        )
                        used_vision = True
                else:
                    print("🧠 Deciding pure visual action via Multimodal Vision Model (qwen3.6-27b)...")
                    action_decision = reasoner.decide_visual_action(
                        goal=goal,
                        visual_state=visual_state,
                        history_summary=history_summary
                    )
                    used_vision = True

                page_state = visual_state

            elif active_mode == "dom":
                page_state = perception.extract_state(controller.page, screenshot_path)
                print(f"📍 Page URL: {page_state['url']}")
                print(f"📄 Page Title: {page_state['title']}")
                print(f"📸 Screenshot saved: {screenshot_path}")

                print("🧠 Thinking next action via DOM perception...")
                action_decision = reasoner.decide_next_action(
                    goal=goal,
                    page_state=page_state,
                    history_summary=history_summary
                )

            else: # hybrid mode
                page_state = perception.extract_state(controller.page, screenshot_path)
                print(f"📍 Page URL: {page_state['url']}")
                print(f"📄 Page Title: {page_state['title']}")

                trigger_vision = memory.should_trigger_vision_fallback() or memory.is_looping()
                if trigger_vision:
                    print("👁️ Vision Fallback Triggered. Analyzing visual screenshot...")
                    try:
                        action_decision = reasoner.decide_with_vision(
                            goal=goal,
                            page_state=page_state,
                            history_summary=history_summary,
                            failure_reason="DOM selector failed or stuck in loop"
                        )
                        used_vision = True
                    except Exception as ve:
                        logger.warning(f"Vision Fallback call failed ({ve}). Falling back to DOM decision...")
                        action_decision = reasoner.decide_next_action(
                            goal=goal,
                            page_state=page_state,
                            history_summary=history_summary
                        )
                else:
                    print("🧠 Thinking next action via DOM perception...")
                    action_decision = reasoner.decide_next_action(
                        goal=goal,
                        page_state=page_state,
                        history_summary=history_summary
                    )

            action_type = action_decision.get("action")
            selector = action_decision.get("selector")
            reasoning = action_decision.get("reasoning", action_decision.get("thought", ""))
            x_coord = action_decision.get("x")
            y_coord = action_decision.get("y")

            print(f"💡 Reasoning: {reasoning}")

            # Handle proactive agent request for human help ('ask_human')
            if action_type == "ask_human":
                print("\n" + "⏸" * 35)
                print(f"⏸ AGENT PROACTIVELY REQUESTED HUMAN HELP!")
                print(f"⏸ Request: {reasoning}")
                print("⏸ Please complete the requested operation directly in the browser.")
                print("⏸ Press ENTER here in terminal once finished to resume agent execution...")
                print("⏸" * 35 + "\n")

                controller.ensure_headed_mode()
                if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                    try:
                        input(">> Press ENTER to continue after providing human help... ")
                    except (EOFError, KeyboardInterrupt):
                        time.sleep(1.0)
                else:
                    logger.info("Non-interactive environment detected. Skipping terminal input() wait.")

                controller.save_session(url)
                print(f"💾 Session state updated.")
                continue

            coords_str = f" Coords=({x_coord}, {y_coord})" if x_coord is not None and y_coord is not None else ""
            sel_str = f" Selector='{selector}'" if selector else ""
            print(f"⚡ Action Chosen: {action_type}{coords_str}{sel_str} (Text: '{action_decision.get('text')}') [Vision={used_vision}]")

            # Execute physical action via Playwright
            success, message, low_conf = execute_visual_action(controller, action_decision)

            # Perform post-action verification for click/type actions in visual mode
            if active_mode == "visual" and action_type in ("click", "type") and success:
                time.sleep(0.5)
                after_screenshot_name = f"step_{step}_after.png"
                after_screenshot_path = str(logs_dir / after_screenshot_name)
                controller.screenshot(after_screenshot_path)

                print("🔍 Performing Post-Action Visual Verification...")
                verified_ok, v_reason = reasoner.verify_visual_action(
                    intended_action=action_decision,
                    before_screenshot_path=screenshot_path,
                    after_screenshot_path=after_screenshot_path
                )

                if not verified_ok:
                    print(f"❌ Post-Action Verification FAILED: {v_reason}")
                    success = False
                    message = f"Post-Action Verification Failed: {v_reason}"
                else:
                    print(f"✅ Post-Action Verification PASSED: {v_reason}")

            result = {
                "success": success,
                "message": message,
                "low_confidence_prediction": low_conf
            }

            if success:
                print(f"📌 Action Output: SUCCESS - {message}")
            else:
                print(f"📌 Action Output: FAILED - {message}")

            # Record step entry in memory
            memory.record_step(
                step_num=step,
                action_taken=action_decision,
                result=result,
                screenshot_path=screenshot_path,
                page_state=page_state,
                used_vision_fallback=used_vision
            )

            # Telemetry step callback for real-time WebSocket dashboard
            if step_callback:
                try:
                    img_base64 = ""
                    if Path(screenshot_path).exists():
                        with open(screenshot_path, "rb") as f:
                            img_base64 = base64.b64encode(f.read()).decode("utf-8")

                    frame_data = {
                        "task_id": active_task_id,
                        "step_num": step,
                        "action": action_type,
                        "selector": selector,
                        "x": x_coord,
                        "y": y_coord,
                        "text": action_decision.get("text"),
                        "key": action_decision.get("key"),
                        "thought": reasoning,
                        "reasoning": reasoning,
                        "success": success,
                        "used_vision": used_vision,
                        "low_confidence_prediction": low_conf,
                        "page_url": page_state.get("current_url") or page_state.get("url"),
                        "page_title": page_state.get("page_title") or page_state.get("title"),
                        "screenshot_base64": f"data:image/png;base64,{img_base64}" if img_base64 else ""
                    }
                    step_callback(frame_data)
                except Exception as cb_err:
                    logger.warning(f"Telemetry step_callback failed: {cb_err}")

            if action_type == "done":
                final_status = f"Completed: {reasoning}"
                print(f"\n✅ TASK DECLARED DONE BY AGENT! Reason: {reasoning}")
                break

            if active_mode == "visual":
                time.sleep(1.0)

            if memory.is_visually_stuck():
                print("\n⚠️ LOOP GUARD TRIGGERED! Agent remains visually stuck after zoom-retry attempts.")
                final_status = f"Stuck: Action {action_type} repeated with zero page progress after zoom-retry."
                break

        else:
            final_status = f"Reached maximum steps limit ({max_steps})."
            print(f"\n⌛ MAX STEPS ({max_steps}) REACHED without declaring 'done'.")

        # --- GOAL SELF-ASSESSMENT STEP ---
        print("\n🔍 Conducting Agent Goal Completion Self-Assessment...")
        final_visual_state = capture_visual_state(controller, screenshot_path=str(logs_dir / "final_state.png"))
        self_assessment = reasoner.assess_goal_completion(
            goal=goal,
            history_summary=memory.get_summary(),
            visual_state=final_visual_state
        )

    except Exception as e:
        logger.error(f"Fatal error during execution loop: {e}")
        final_status = f"Failed with exception: {e}"
        print(f"\n❌ Execution Error: {e}")

    finally:
        controller.close()

    summary_data = {
        "task_id": active_task_id,
        "goal": goal,
        "start_url": url,
        "mode": active_mode,
        "final_status": final_status,
        "total_steps": len(memory.history),
        "session_saved": controller.get_session_path_for_url(url),
        "self_assessment": self_assessment,
        "history": memory.history
    }

    summary_file = logs_dir / "run_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print("\n" + "=" * 70)
    print("📊 EXECUTION SUMMARY & SELF-ASSESSMENT")
    print(f"Status: {final_status}")
    print(f"Total Steps Taken: {len(memory.history)}")
    print(f"Mode: {active_mode}")

    if self_assessment:
        print("\n" + "-" * 50)
        print("📝 AGENT SELF-ASSESSMENT REPORT")
        print(f"Completion Status: {self_assessment.get('completion_status', 'N/A').upper()}")
        print(f"Accomplishment: {self_assessment.get('accomplishment_summary')}")
        print(f"Explanation: {self_assessment.get('detailed_explanation')}")
        print("-" * 50)

    print(f"Detailed Log Exported: {summary_file}")
    print("=" * 70 + "\n")

    return summary_data

def parse_args():
    parser = argparse.ArgumentParser(description="Generalized Computer-Use Browser Agent CLI")
    parser.add_argument("--goal", type=str, required=True, help="Any free-text user goal or task description")
    parser.add_argument("--url", type=str, required=True, help="Initial target web page URL")
    parser.add_argument("--mode", type=str, choices=["visual", "dom", "hybrid"], default="visual", help="Agent operational mode")
    parser.add_argument("--session", type=str, default=None, help="Explicit path to session storage json file")
    parser.add_argument("--max-steps", type=int, default=15, help="Maximum execution steps allowed (default: 15)")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    parser.add_argument("--no-grid", action="store_true", default=False, help="Disable 100px coordinate grid overlay")
    parser.add_argument("--no-vision", action="store_true", default=False, help="Disable Vision (Pure-DOM mode)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_agent(
        goal=args.goal,
        url=args.url,
        max_steps=args.max_steps,
        headless=args.headless,
        mode="dom" if args.no_vision else args.mode,
        session_file=args.session,
        grid_overlay=not args.no_grid
    )
