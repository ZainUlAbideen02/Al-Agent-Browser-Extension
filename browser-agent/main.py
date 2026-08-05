import os
import sys
import json
import time
import uuid
import shutil
import logging
import argparse
import traceback
import base64
from pathlib import Path
from datetime import datetime
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
from agent.task_store import get_saved_tasks, add_task, remove_task, get_task, list_tasks

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
    Optimized entry point executing browser agent control loop for ANY user goal on ANY website,
    with merged single-call LLM reasoning, fast-path verification skipping, human-handoff,
    session state persistence, top-level crash dumper, and goal self-assessment.
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
    consecutive_high_confidence_successes = 0

    try:
        controller.start(headless=headless, session_file=active_session)
        controller.goto(url)

        for step in range(1, max_steps + 1):
            step_start_time = time.perf_counter()
            print(f"\n--- [STEP {step}/{max_steps}] ---")

            screenshot_name = f"step_{step}.png"
            screenshot_path = str(logs_dir / screenshot_name)

            history_summary = memory.get_summary()
            used_vision = False

            if active_mode == "visual":
                t0_percept = time.perf_counter()
                visual_state = capture_visual_state(
                    controller,
                    screenshot_path=screenshot_path,
                    grid_overlay=grid_overlay
                )
                t_percept = time.perf_counter() - t0_percept

                print(f"📍 Page URL: {visual_state['current_url']}")
                print(f"📄 Page Title: {visual_state['page_title']}")
                print(f"📸 Visual Screenshot saved: {screenshot_path}")

                t0_llm = time.perf_counter()

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
                        logger.warning(f"Zoom-retry call failed: {ze}. Falling back to unified visual decision...")
                        action_decision = reasoner.decide_visual_step(
                            goal=goal,
                            visual_state=visual_state,
                            history_summary=history_summary
                        )
                        used_vision = True
                else:
                    print("🧠 Deciding visual action & security checks in SINGLE unified Groq API call...")
                    action_decision = reasoner.decide_visual_step(
                        goal=goal,
                        visual_state=visual_state,
                        history_summary=history_summary
                    )
                    used_vision = True

                t_llm = time.perf_counter() - t0_llm

                # Handle Human Handoff Detection if flag set in unified response
                if action_decision.get("human_required"):
                    req_type = action_decision.get("requirement_type") or "login"
                    req_reason = action_decision.get("reasoning", "Human intervention required.")
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

                page_state = visual_state

            elif active_mode == "dom":
                t0_percept = time.perf_counter()
                page_state = perception.extract_state(controller.page, screenshot_path)
                t_percept = time.perf_counter() - t0_percept

                print(f"📍 Page URL: {page_state['url']}")
                print(f"📄 Page Title: {page_state['title']}")
                print(f"📸 Screenshot saved: {screenshot_path}")

                t0_llm = time.perf_counter()
                print("🧠 Thinking next action via DOM perception...")
                action_decision = reasoner.decide_next_action(
                    goal=goal,
                    page_state=page_state,
                    history_summary=history_summary
                )
                t_llm = time.perf_counter() - t0_llm

            else: # hybrid mode
                t0_percept = time.perf_counter()
                page_state = perception.extract_state(controller.page, screenshot_path)
                t_percept = time.perf_counter() - t0_percept

                print(f"📍 Page URL: {page_state['url']}")
                print(f"📄 Page Title: {page_state['title']}")

                t0_llm = time.perf_counter()
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
                t_llm = time.perf_counter() - t0_llm

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
            t0_act = time.perf_counter()
            success, message, low_conf = execute_visual_action(controller, action_decision)
            t_act = time.perf_counter() - t0_act

            # FAST PATH FOR SIMPLE REPEATED ACTIONS
            use_fast_path = (consecutive_high_confidence_successes >= 2)
            if use_fast_path and active_mode == "visual" and action_type in ("click", "type"):
                print("⚡ FAST PATH ACTIVE: Skipping post-action visual verification (Saved 1 LLM round-trip)!")
                verified_ok = True
                v_reason = "Verification skipped via Fast Path Optimization."
            elif active_mode == "visual" and action_type in ("click", "type") and success:
                time.sleep(0.3)
                after_screenshot_name = f"step_{step}_after.png"
                after_screenshot_path = str(logs_dir / after_screenshot_name)
                controller.screenshot(after_screenshot_path)

                print("🔍 Performing Post-Action Visual Verification...")
                verified_ok, v_reason = reasoner.verify_visual_action(
                    intended_action=action_decision,
                    before_screenshot_path=screenshot_path,
                    after_screenshot_path=after_screenshot_path
                )
            else:
                verified_ok = True
                v_reason = "Verification not required for action type."

            if not verified_ok:
                print(f"❌ Post-Action Verification FAILED: {v_reason}")
                success = False
                message = f"Post-Action Verification Failed: {v_reason}"
                consecutive_high_confidence_successes = 0
            elif success and not low_conf:
                consecutive_high_confidence_successes += 1
            else:
                consecutive_high_confidence_successes = 0

            result = {
                "success": success,
                "message": message,
                "low_confidence_prediction": low_conf
            }

            step_duration = time.perf_counter() - step_start_time
            print(f"⏱️ Step {step} Latency: {step_duration:.2f}s (Percept: {t_percept:.2f}s | LLM: {t_llm:.2f}s | Action: {t_act:.2f}s)")

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
                time.sleep(0.5)

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
        crash_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_dir = logs_dir / f"crash_{crash_timestamp}"
        os.makedirs(crash_dir, exist_ok=True)

        tb_str = traceback.format_exc()
        logger.error(f"Top-level execution exception caught: {e}\n{tb_str}")
        final_status = f"Failed with crash: {e}"

        recent_screenshots = list(logs_dir.glob("step_*.png"))[-3:]
        saved_crash_shots = []
        for shot in recent_screenshots:
            dest = crash_dir / shot.name
            shutil.copy(shot, dest)
            saved_crash_shots.append(str(dest))

        crash_dump_data = {
            "task_id": active_task_id,
            "goal": goal,
            "url": url,
            "timestamp": crash_timestamp,
            "exception": str(e),
            "traceback": tb_str,
            "total_steps_executed": len(memory.history),
            "copied_screenshots": saved_crash_shots,
            "history": memory.history
        }

        crash_file = crash_dir / "crash_dump.json"
        with open(crash_file, "w", encoding="utf-8") as f:
            json.dump(crash_dump_data, f, indent=2)

        print("\n" + "💥" * 35)
        print(f"💥 TOP-LEVEL AGENT CRASH CAUGHT & DUMPED TO DISK!")
        print(f"💥 Crash Directory: {crash_dir}")
        print(f"💥 Exception: {e}")
        print(f"💥 Crash Dump Log: {crash_file}")
        print("💥" * 35 + "\n")

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

    # --- RESULT SUMMARY NOTIFICATION BLOCK ---
    if "Failed" in final_status or final_status.startswith("Stuck"):
        assess_status = "FAILED"
        accomplishment = final_status
    elif self_assessment:
        assess_status = self_assessment.get("completion_status", "COMPLETED").upper()
        accomplishment = self_assessment.get("accomplishment_summary", final_status)
    else:
        assess_status = "COMPLETED"
        accomplishment = final_status

    print("\n" + "🔔" * 35)
    print(f"🔔 TASK EXECUTION RESULT SUMMARY")
    print(f"Goal: {goal}")
    print(f"Status: {assess_status} ({final_status})")
    print(f"Accomplishment: {accomplishment}")
    print("🔔" * 35 + "\n")

    return summary_data

def parse_args():
    parser = argparse.ArgumentParser(description="Optimized Personal Assistant Browser Agent CLI")
    parser.add_argument("--goal", type=str, default=None, help="Free-text user goal description")
    parser.add_argument("--url", type=str, default=None, help="Initial target web page URL")
    parser.add_argument("--run", type=str, default=None, help="Run a saved task preset by name from config/saved_tasks.json")
    parser.add_argument("--list", action="store_true", default=False, help="List all saved task presets")
    parser.add_argument("--add", type=str, default=None, help="Add a new saved task preset by name")
    parser.add_argument("--remove", type=str, default=None, help="Remove a saved task preset by name")
    parser.add_argument("--mode", type=str, choices=["visual", "dom", "hybrid"], default="visual", help="Agent operational mode")
    parser.add_argument("--session", type=str, default=None, help="Explicit path to session storage json file")
    parser.add_argument("--max-steps", type=int, default=15, help="Maximum execution steps allowed (default: 15)")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    parser.add_argument("--no-grid", action="store_true", default=False, help="Disable 100px coordinate grid overlay")
    parser.add_argument("--no-vision", action="store_true", default=False, help="Disable Vision (Pure-DOM mode)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    # 1. Handle --list
    if args.list:
        tasks = list_tasks()
        print("\n" + "=" * 70)
        print("📋 SAVED TASK PRESETS")
        print("=" * 70)
        for t in tasks:
            print(f"  • {t['name']:<15} | Goal: {t['goal']}")
            print(f"    URL: {t['url']} | Mode: {t['mode']}")
        print("=" * 70 + "\n")
        sys.exit(0)

    # 2. Handle --remove
    if args.remove:
        if remove_task(args.remove):
            print(f"✅ Removed task preset '{args.remove}'.")
        else:
            print(f"❌ Task preset '{args.remove}' not found.")
        sys.exit(0)

    # 3. Handle --add
    if args.add:
        goal_val = args.goal or input("Enter Natural Language Goal: ").strip()
        url_val = args.url or input("Enter Target URL: ").strip()
        mode_val = args.mode or "visual"
        add_task(name=args.add, goal=goal_val, url=url_val, mode=mode_val)
        print(f"✅ Saved task preset '{args.add}' successfully!")
        sys.exit(0)

    active_goal = args.goal
    active_url = args.url
    active_mode = args.mode

    # 4. Handle --run <task_name>
    if args.run:
        preset = get_task(args.run)
        if preset:
            active_goal = preset.get("goal")
            active_url = preset.get("url")
            active_mode = preset.get("mode", active_mode)
            logger.info(f"Running saved task preset '{args.run}': Goal='{active_goal}', URL='{active_url}'")
        else:
            print(f"❌ Error: Task preset '{args.run}' not found.")
            sys.exit(1)

    if not active_goal or not active_url:
        print("❌ Error: Both --goal and --url (or --run <task_name>) are required.")
        print("💡 Use 'python run.py' for interactive menu, or 'python main.py --list' to see saved tasks.")
        sys.exit(1)

    run_agent(
        goal=active_goal,
        url=active_url,
        max_steps=args.max_steps,
        headless=args.headless,
        mode="dom" if args.no_vision else active_mode,
        session_file=args.session,
        grid_overlay=not args.no_grid
    )
