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
from browser.controller import BrowserController
from browser.perception import DOMPerception
from browser.actions import execute_action
from agent.reasoner import ReasonerAgent
from agent.memory import StepMemory

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
    disable_vision: bool = False,
    task_id: Optional[str] = None,
    step_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Dict[str, Any]:
    """
    Main entry point executing browser agent control loop.
    Supports real-time telemetry step callbacks for FastAPI WebSocket server.
    """
    check_api_key()

    active_task_id = task_id or str(uuid.uuid4())[:8]
    logs_dir = Path(__file__).resolve().parent / "logs"
    os.makedirs(logs_dir, exist_ok=True)

    mode_label = "Pure DOM (Ablation)" if disable_vision else "Hybrid DOM + Vision Fallback"
    print("\n" + "=" * 60)
    print(f"🤖 BROWSER AGENT INITIALIZED ({mode_label})")
    print(f"🎯 Goal: {goal}")
    print(f"🌐 Starting URL: {url}")
    print(f"⚙️  Max Steps: {max_steps} | Headless: {headless} | Vision Disabled: {disable_vision}")
    print("=" * 60 + "\n")

    controller = BrowserController(default_timeout_ms=20000)
    perception = DOMPerception()
    reasoner = ReasonerAgent()
    memory = StepMemory()

    final_status = "In progress"

    try:
        controller.start(headless=headless)
        controller.goto(url)

        for step in range(1, max_steps + 1):
            print(f"\n--- [STEP {step}/{max_steps}] ---")

            screenshot_name = f"step_{step}.png"
            screenshot_path = str(logs_dir / screenshot_name)
            page_state = perception.extract_state(controller.page, screenshot_path)

            print(f"📍 Page URL: {page_state['url']}")
            print(f"📄 Page Title: {page_state['title']}")
            print(f"📸 Screenshot saved: {screenshot_path}")

            history_summary = memory.get_summary()
            used_vision = False

            # Evaluate Vision Fallback triggers
            trigger_vision = not disable_vision and (
                memory.should_trigger_vision_fallback() or memory.is_looping()
            )

            if trigger_vision:
                print("👁️ Vision Fallback Triggered (2 consecutive action failures or loop guard). Analyzing screenshot...")
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
                    print("🧠 Thinking next action via DOM perception...")
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
            reasoning = action_decision.get("reasoning")

            print(f"💡 Reasoning: {reasoning}")
            print(f"⚡ Action Chosen: {action_type} (Selector: '{selector}', Text: '{action_decision.get('text')}') [Vision={used_vision}]")

            # Execute action via Playwright
            result = execute_action(controller, action_decision)

            if result.get("success"):
                print(f"📌 Action Output: SUCCESS - {result.get('message')}")
            else:
                print(f"📌 Action Output: FAILED - {result.get('message')}")

            # Record step entry in memory
            memory.record_step(
                step_num=step,
                action_taken=action_decision,
                result=result,
                screenshot_path=screenshot_path,
                page_state=page_state,
                used_vision_fallback=used_vision
            )

            # Trigger step callback for real-time WebSocket telemetry if provided
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
                        "x": action_decision.get("x"),
                        "y": action_decision.get("y"),
                        "reasoning": reasoning,
                        "success": result.get("success"),
                        "used_vision": used_vision,
                        "page_url": page_state.get("url"),
                        "page_title": page_state.get("title"),
                        "screenshot_base64": f"data:image/png;base64,{img_base64}" if img_base64 else ""
                    }
                    step_callback(frame_data)
                except Exception as cb_err:
                    logger.warning(f"Telemetry step_callback failed: {cb_err}")

            if action_type == "done":
                final_status = f"Completed successfully: {reasoning}"
                print(f"\n✅ TASK COMPLETED! Reason: {reasoning}")
                break

            if memory.is_looping() and not trigger_vision:
                print("\n⚠️ LOOP GUARD TRIGGERED! Action repeated 3 times with zero page progress. Agent is stuck.")
                if disable_vision:
                    final_status = f"Stuck: Action {action_type} on '{selector}' repeated 3 times with zero page progress."
                    print("🛑 Agent remains stuck (Pure DOM mode). Terminating task cleanly.")
                    break
                else:
                    print("🔄 Forcing Vision Fallback on next step to break loop...")

        else:
            final_status = f"Reached maximum steps limit ({max_steps})."
            print(f"\n⌛ MAX STEPS ({max_steps}) REACHED without declaring 'done'.")

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
        "mode": "dom" if disable_vision else "hybrid",
        "final_status": final_status,
        "total_steps": len(memory.history),
        "pure_dom_steps": len(memory.history) - memory.vision_fallback_count,
        "vision_fallback_steps": memory.vision_fallback_count,
        "vision_fallback_ratio": round(memory.vision_fallback_count / max(1, len(memory.history)), 2),
        "history": memory.history
    }

    summary_file = logs_dir / "run_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print("\n" + "=" * 60)
    print("📊 EXECUTION SUMMARY")
    print(f"Status: {final_status}")
    print(f"Total Steps Taken: {len(memory.history)}")
    print(f"Pure DOM Steps: {summary_data['pure_dom_steps']} | Vision Fallback Steps: {summary_data['vision_fallback_steps']}")
    print(f"Detailed Log Exported: {summary_file}")
    print("=" * 60 + "\n")

    return summary_data

def parse_args():
    parser = argparse.ArgumentParser(description="Browser Agent CLI Runner")
    parser.add_argument("--goal", type=str, required=True, help="Natural language objective for the agent")
    parser.add_argument("--url", type=str, required=True, help="Initial target web page URL")
    parser.add_argument("--max-steps", type=int, default=15, help="Maximum execution steps allowed (default: 15)")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    parser.add_argument("--no-vision", action="store_true", default=False, help="Disable Vision Fallback (Pure-DOM mode)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_agent(
        goal=args.goal,
        url=args.url,
        max_steps=args.max_steps,
        headless=args.headless,
        disable_vision=args.no_vision
    )
