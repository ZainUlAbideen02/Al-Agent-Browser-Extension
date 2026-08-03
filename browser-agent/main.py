import os
import sys
import json
import argparse
import logging
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config.settings import validate_config
from browser.controller import BrowserController
from browser.perception import get_page_state
from browser.actions import execute_action
from agent.reasoner import ReasonerAgent
from agent.memory import StepMemory

logger = logging.getLogger("browser_agent.main")

def setup_logging():
    """Configure system logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Browser Agent - AI Browser Automation with Vision Fallback & Safety Guards."
    )
    parser.add_argument(
        "--goal",
        type=str,
        required=True,
        help="Task goal description for the agent."
    )
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="Starting URL to navigate to."
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum number of steps allowed (default: 15)."
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (default: False / headed mode)."
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        default=False,
        help="Disable Vision Fallback (Pure DOM ablation mode)."
    )
    return parser.parse_args()

def run_agent(
    goal: str,
    url: str,
    max_steps: int = 15,
    headless: bool = False,
    disable_vision: bool = False
) -> dict:
    """
    Run browser agent task loop and return execution summary data.
    """
    setup_logging()

    mode_str = "Pure DOM (Ablation)" if disable_vision else "Hybrid DOM + Vision Fallback"
    print("\n" + "=" * 60)
    print(f"🤖 BROWSER AGENT INITIALIZED ({mode_str})")
    print(f"🎯 Goal: {goal}")
    print(f"🌐 Starting URL: {url}")
    print(f"⚙️  Max Steps: {max_steps} | Headless: {headless} | Vision Disabled: {disable_vision}")
    print("=" * 60 + "\n")

    if not validate_config():
        print("⚠️ Warning: GROQ_API_KEY is not configured in .env or environment.\n")

    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    controller = BrowserController()
    memory = StepMemory()
    reasoner = ReasonerAgent()

    status_summary = "Incomplete"
    consecutive_failures = 0

    try:
        controller.start(headless=headless)
        controller.goto(url)

        for step in range(1, max_steps + 1):
            print(f"\n--- [STEP {step}/{max_steps}] ---")
            
            # 1. Perception
            page_state = get_page_state(controller, step_num=step, log_dir=logs_dir)
            print(f"📍 Page URL: {page_state['url']}")
            print(f"📄 Page Title: {page_state['title']}")
            print(f"📸 Screenshot saved: {page_state['screenshot_path']}")

            history_summary = memory.format_history(max_steps=5)
            used_vision = False

            # 2. Reasoner (Switch to Vision Fallback if 2+ consecutive failures occurred AND vision is enabled)
            if consecutive_failures >= 2 and not disable_vision:
                print("👁️ Vision Fallback Triggered (2 consecutive action failures on selector). Analyzing screenshot...")
                used_vision = True
                failure_msg = f"Action execution failed {consecutive_failures} times in a row."
                try:
                    action_dict = reasoner.decide_with_vision(
                        goal=goal,
                        page_state=page_state,
                        history_summary=history_summary,
                        failure_reason=failure_msg
                    )
                except Exception as ve:
                    print(f"⚠️ Vision Fallback call failed ({ve}). Falling back to DOM decision...")
                    action_dict = reasoner.decide_next_action(goal, page_state, history_summary)
            else:
                if consecutive_failures >= 2 and disable_vision:
                    print("⚠️ Vision Fallback bypassed (Pure DOM Ablation Mode enabled).")
                print("🧠 Thinking next action via DOM perception...")
                action_dict = reasoner.decide_next_action(goal, page_state, history_summary)

            action_type = action_dict.get("action")
            reasoning = action_dict.get("reasoning", "")
            selector = action_dict.get("selector")
            text = action_dict.get("text")

            print(f"💡 Reasoning: {reasoning}")
            print(f"⚡ Action Chosen: {action_type} (Selector: '{selector}', Text: '{text}') [Vision={used_vision}]")

            # Check if complete
            if action_type == "done":
                print(f"\n✅ TASK COMPLETED! Reason: {reasoning}")
                status_summary = f"Completed successfully: {reasoning}"
                memory.add_step(
                    step, action_dict, {"success": True, "message": "Done"},
                    page_state['screenshot_path'], used_vision_fallback=used_vision,
                    page_url=page_state['url'], page_title=page_state['title']
                )
                break

            # 3. Action Execution
            result = execute_action(controller, action_dict)
            success = result.get("success", False)
            print(f"📌 Action Output: {'SUCCESS' if success else 'FAILED'} - {result.get('message')}")

            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(f"Action failed! Consecutive failure count: {consecutive_failures}")

            # 4. Memory Recording
            memory.add_step(
                step_num=step,
                action_taken=action_dict,
                result=result,
                screenshot_path=page_state['screenshot_path'],
                used_vision_fallback=used_vision,
                page_url=page_state['url'],
                page_title=page_state['title']
            )

            # 5. Strengthened Loop Detection & Progress Check
            loop_check = memory.is_looping(repeat_threshold=3)
            if loop_check["is_looping"]:
                print(f"\n⚠️ LOOP GUARD TRIGGERED! {loop_check['reason']}")
                if not used_vision and not disable_vision:
                    print("🔄 Forcing Vision Fallback on next step to break loop...")
                    consecutive_failures = 2  # Force vision on next iteration
                else:
                    print("🛑 Agent remains stuck even after Vision / Pure DOM. Terminating task cleanly with 'stuck' status.")
                    status_summary = f"Stuck: {loop_check['reason']}"
                    break

        else:
            print(f"\n⌛ MAX STEPS ({max_steps}) REACHED without declaring 'done'.")
            status_summary = f"Reached maximum steps limit ({max_steps})."

    except Exception as e:
        print(f"\n❌ Error during agent execution: {e}")
        status_summary = f"Failed with exception: {e}"

    finally:
        controller.close()

    # Final Log & Summary
    stats = memory.get_summary_stats()
    summary_data = {
        "goal": goal,
        "start_url": url,
        "mode": "pure_dom" if disable_vision else "hybrid",
        "final_status": status_summary,
        "total_steps": stats["total_steps"],
        "pure_dom_steps": stats["pure_dom_steps"],
        "vision_fallback_steps": stats["vision_fallback_steps"],
        "vision_fallback_ratio": stats["vision_fallback_ratio"],
        "history": memory.history
    }

    summary_file = os.path.join(logs_dir, "run_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print("\n" + "=" * 60)
    print("📊 EXECUTION SUMMARY")
    print(f"Status: {status_summary}")
    print(f"Total Steps Taken: {stats['total_steps']}")
    print(f"Pure DOM Steps: {stats['pure_dom_steps']} | Vision Fallback Steps: {stats['vision_fallback_steps']}")
    print(f"Detailed Log Exported: {summary_file}")
    print("=" * 60 + "\n")

    return summary_data

def main():
    args = parse_args()
    run_agent(
        goal=args.goal,
        url=args.url,
        max_steps=args.max_steps,
        headless=args.headless,
        disable_vision=args.no_vision
    )

if __name__ == "__main__":
    main()
