import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# UTF-8 stdout encoding for Windows compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from main import run_agent

BENCHMARK_TASKS = [
    {
        "id": "task_1",
        "name": "Browse Category on BooksToScrape",
        "goal": "Click on the 'Travel' category link and report the first book title listed.",
        "url": "https://books.toscrape.com/",
        "success_criteria": "Successfully navigated to Travel category and identified a book."
    },
    {
        "id": "task_2",
        "name": "Extract Book Price",
        "goal": "Find and report the price of the first book shown on the homepage.",
        "url": "https://books.toscrape.com/",
        "success_criteria": "Identified the price of the first book item."
    },
    {
        "id": "task_3",
        "name": "Find Quote on QuotesToScrape",
        "goal": "Find and report the first quote text and author name on the homepage.",
        "url": "https://quotes.toscrape.com/",
        "success_criteria": "Located first quote and author."
    },
    {
        "id": "task_4",
        "name": "Extract Wikipedia Main Heading",
        "goal": "Identify and report the main title heading on Wikipedia's homepage.",
        "url": "https://www.wikipedia.org/",
        "success_criteria": "Found main title heading."
    },
    {
        "id": "task_5",
        "name": "Search Wikipedia Topic",
        "goal": "Search for 'Artificial Intelligence' using the search box and navigate to the article.",
        "url": "https://www.wikipedia.org/",
        "success_criteria": "Navigated to Artificial Intelligence Wikipedia article."
    }
]

def parse_args():
    parser = argparse.ArgumentParser(description="Browser Agent Benchmark Evaluation Suite")
    parser.add_argument("--max-steps", type=int, default=10, help="Max steps per task (default: 10)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless (default: True)")
    return parser.parse_args()

def main():
    args = parse_args()
    print("\n" + "=" * 70)
    print("🏆 BROWSER AGENT EVALUATION HARNESS")
    print(f"Running {len(BENCHMARK_TASKS)} Benchmark Tasks | Max Steps: {args.max_steps} | Headless: {args.headless}")
    print("=" * 70 + "\n")

    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    results = []
    start_time_all = time.time()

    for idx, task in enumerate(BENCHMARK_TASKS, 1):
        print(f"\n" + "#" * 70)
        print(f"RUNNING EVALUATION TASK [{idx}/{len(BENCHMARK_TASKS)}]: {task['name']}")
        print(f"Goal: {task['goal']}")
        print(f"URL: {task['url']}")
        print("#" * 70 + "\n")

        task_start_time = time.time()
        try:
            summary = run_agent(
                goal=task["goal"],
                url=task["url"],
                max_steps=args.max_steps,
                headless=args.headless
            )
            elapsed = round(time.time() - task_start_time, 2)
            
            status = summary.get("final_status", "Unknown")
            is_success = "Completed successfully" in status

            task_result = {
                "task_id": task["id"],
                "name": task["name"],
                "goal": task["goal"],
                "url": task["url"],
                "success_criteria": task["success_criteria"],
                "passed": is_success,
                "status": status,
                "elapsed_seconds": elapsed,
                "total_steps": summary.get("total_steps", 0),
                "pure_dom_steps": summary.get("pure_dom_steps", 0),
                "vision_fallback_steps": summary.get("vision_fallback_steps", 0)
            }
        except Exception as e:
            elapsed = round(time.time() - task_start_time, 2)
            task_result = {
                "task_id": task["id"],
                "name": task["name"],
                "goal": task["goal"],
                "url": task["url"],
                "success_criteria": task["success_criteria"],
                "passed": False,
                "status": f"Execution exception: {e}",
                "elapsed_seconds": elapsed,
                "total_steps": 0,
                "pure_dom_steps": 0,
                "vision_fallback_steps": 0
            }

        results.append(task_result)

    total_time = round(time.time() - start_time_all, 2)
    passed_count = sum(1 for r in results if r["passed"])
    total_vision_steps = sum(r["vision_fallback_steps"] for r in results)

    eval_summary = {
        "benchmark_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": len(BENCHMARK_TASKS),
        "passed_tasks": passed_count,
        "success_rate": f"{(passed_count / len(BENCHMARK_TASKS)) * 100:.1f}%",
        "total_benchmark_seconds": total_time,
        "total_vision_fallback_steps": total_vision_steps,
        "task_results": results
    }

    eval_file = os.path.join(logs_dir, "evaluation_results.json")
    with open(eval_file, "w", encoding="utf-8") as f:
        json.dump(eval_summary, f, indent=2)

    print("\n" + "=" * 70)
    print("📈 EVALUATION BENCHMARK SUMMARY REPORT")
    print("=" * 70)
    print(f"Tasks Completed: {passed_count}/{len(BENCHMARK_TASKS)} (Success Rate: {eval_summary['success_rate']})")
    print(f"Total Time: {total_time}s | Total Vision Fallbacks: {total_vision_steps}")
    print(f"Detailed Results Saved: {eval_file}\n")

    for r in results:
        mark = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"{mark} | {r['name']} ({r['total_steps']} steps, Vision={r['vision_fallback_steps']}, {r['elapsed_seconds']}s)")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
