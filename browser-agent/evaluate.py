import os
import sys
import json
import time
import argparse
import statistics
import logging
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# UTF-8 stdout encoding for Windows compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from main import run_agent

PROJECT_ROOT = Path(__file__).resolve().parent
CANVAS_TEST_PATH = PROJECT_ROOT / "tests" / "canvas_test.html"
CANVAS_TEST_URL = f"file:///{str(CANVAS_TEST_PATH).replace('\\', '/')}"

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
    },
    {
        "id": "task_6",
        "name": "Modal Overlay / Cookie Banner (Entry Ad)",
        "goal": "Dismiss or close the modal popup advertisement window by clicking the 'Close' modal button.",
        "url": "https://the-internet.herokuapp.com/entry_ad",
        "success_criteria": "Closed the modal overlay window successfully."
    },
    {
        "id": "task_7",
        "name": "Dropdown Select Interaction",
        "goal": "Select 'Option 2' from the dropdown select element on the page.",
        "url": "https://the-internet.herokuapp.com/dropdown",
        "success_criteria": "Selected Option 2 in the dropdown element."
    },
    {
        "id": "task_8",
        "name": "Dynamic Loading / Lazy DOM Element",
        "goal": "Click the 'Start' button, wait for the loading indicator to complete, and confirm the hidden text 'Hello World!' appeared.",
        "url": "https://the-internet.herokuapp.com/dynamic_loading/1",
        "success_criteria": "Clicked Start, waited for dynamic load, and extracted text."
    },
    {
        "id": "task_9",
        "name": "Challenging DOM & Duplicate Elements",
        "goal": "Find and click the first blue action button (the top button in the container) and report its text label.",
        "url": "https://the-internet.herokuapp.com/challenging_dom",
        "success_criteria": "Clicked the first blue button in challenging DOM container."
    },
    {
        "id": "task_10",
        "name": "Non-DOM Canvas UI Visual Disambiguation",
        "goal": "Find and click the canvas button visually labeled 'CLICK ME TO WIN - TARGET'",
        "url": CANVAS_TEST_URL,
        "success_criteria": "Visually visually identified and clicked the green target canvas button, bypassing trap canvas."
    }
]

def parse_args():
    parser = argparse.ArgumentParser(description="Browser Agent 10-Task Benchmark Evaluation Suite")
    parser.add_argument("--max-steps", type=int, default=10, help="Max steps per task (default: 10)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless (default: True)")
    parser.add_argument("--no-vision", action="store_true", default=False, help="Disable Vision Fallback (Pure DOM Ablation Mode)")
    parser.add_argument("--runs", type=int, default=1, help="Number of benchmark runs for statistical mean/stddev (default: 1)")
    return parser.parse_args()

def main():
    args = parse_args()
    mode_name = "Pure DOM (Ablation)" if args.no_vision else "Hybrid (DOM + Vision Fallback)"
    
    print("\n" + "=" * 75)
    print(f"🏆 BROWSER AGENT EVALUATION HARNESS [{mode_name}]")
    print(f"Running {len(BENCHMARK_TASKS)} Tasks | Runs: {args.runs} | Max Steps: {args.max_steps} | Headless: {args.headless}")
    print("=" * 75 + "\n")

    logs_dir = PROJECT_ROOT / "logs"
    os.makedirs(logs_dir, exist_ok=True)

    task_summaries = []
    total_start_time = time.time()

    for idx, task in enumerate(BENCHMARK_TASKS, 1):
        print(f"\n" + "#" * 75)
        print(f"BENCHMARK TASK [{idx}/{len(BENCHMARK_TASKS)}]: {task['name']}")
        print(f"Goal: {task['goal']}")
        print(f"URL: {task['url']}")
        print("#" * 75 + "\n")

        run_times = []
        run_passes = []
        run_steps = []
        run_vision_steps = []
        last_status = "Unknown"

        for r in range(1, args.runs + 1):
            if args.runs > 1:
                print(f"--- Task Run {r}/{args.runs} ---")
            task_start_time = time.time()
            try:
                summary = run_agent(
                    goal=task["goal"],
                    url=task["url"],
                    max_steps=args.max_steps,
                    headless=args.headless,
                    disable_vision=args.no_vision
                )
                elapsed = round(time.time() - task_start_time, 2)
                last_status = summary.get("final_status", "Unknown")
                is_success = "Completed successfully" in last_status

                run_times.append(elapsed)
                run_passes.append(is_success)
                run_steps.append(summary.get("total_steps", 0))
                run_vision_steps.append(summary.get("vision_fallback_steps", 0))

            except Exception as e:
                elapsed = round(time.time() - task_start_time, 2)
                last_status = f"Execution exception: {e}"
                run_times.append(elapsed)
                run_passes.append(False)
                run_steps.append(0)
                run_vision_steps.append(0)

        mean_time = round(statistics.mean(run_times), 2)
        std_time = round(statistics.stdev(run_times), 2) if len(run_times) > 1 else 0.0
        pass_ratio = sum(1 for p in run_passes if p) / len(run_passes)
        avg_steps = round(statistics.mean(run_steps), 1)
        avg_vision_steps = round(statistics.mean(run_vision_steps), 1)

        task_summary = {
            "task_id": task["id"],
            "name": task["name"],
            "goal": task["goal"],
            "url": task["url"],
            "success_criteria": task["success_criteria"],
            "passed": pass_ratio >= 0.5,
            "pass_ratio": pass_ratio,
            "status": last_status,
            "mean_seconds": mean_time,
            "std_seconds": std_time,
            "avg_steps": avg_steps,
            "avg_vision_steps": avg_vision_steps
        }
        task_summaries.append(task_summary)

    total_benchmark_time = round(time.time() - total_start_time, 2)
    overall_passed = sum(1 for t in task_summaries if t["passed"])
    total_vision_activations = sum(t["avg_vision_steps"] for t in task_summaries)

    eval_summary = {
        "benchmark_mode": "pure_dom" if args.no_vision else "hybrid",
        "benchmark_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": len(BENCHMARK_TASKS),
        "passed_tasks": overall_passed,
        "success_rate": f"{(overall_passed / len(BENCHMARK_TASKS)) * 100:.1f}%",
        "total_benchmark_seconds": total_benchmark_time,
        "total_vision_fallback_steps": total_vision_activations,
        "task_results": task_summaries
    }

    mode_file = "evaluation_results_dom.json" if args.no_vision else "evaluation_results_hybrid.json"
    eval_file = os.path.join(logs_dir, mode_file)
    with open(eval_file, "w", encoding="utf-8") as f:
        json.dump(eval_summary, f, indent=2)

    # Always update main evaluation_results.json
    main_eval_file = os.path.join(logs_dir, "evaluation_results.json")
    with open(main_eval_file, "w", encoding="utf-8") as f:
        json.dump(eval_summary, f, indent=2)

    print("\n" + "=" * 80)
    print(f"📈 EVALUATION BENCHMARK SUMMARY REPORT [{mode_name}]")
    print("=" * 80)
    print(f"Tasks Completed: {overall_passed}/{len(BENCHMARK_TASKS)} (Success Rate: {eval_summary['success_rate']})")
    print(f"Total Benchmark Time: {total_benchmark_time}s | Total Vision Fallbacks: {total_vision_activations}")
    print(f"Detailed Results Saved: {eval_file}\n")

    print(f"{'Status':<8} | {'Task Name':<42} | {'Steps':<6} | {'Vision':<6} | {'Mean Time':<10}")
    print("-" * 80)
    for r in task_summaries:
        mark = "✅ PASS" if r["passed"] else "❌ FAIL"
        time_str = f"{r['mean_seconds']}s ±{r['std_seconds']}s" if r['std_seconds'] > 0 else f"{r['mean_seconds']}s"
        print(f"{mark:<8} | {r['name'][:42]:<42} | {r['avg_steps']:<6} | {r['avg_vision_steps']:<6} | {time_str}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
