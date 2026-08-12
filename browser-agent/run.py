import sys
import os
import time
import logging
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure UTF-8 output encoding on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from agent.task_store import list_tasks, get_task, add_task, remove_task
from main import run_agent

def display_menu():
    tasks = list_tasks()
    print("\n" + "=" * 70)
    print("🤖 BROWSER AGENT QUICK-LAUNCH MENU")
    print("=" * 70)
    
    print(" [0] 🚀 Run Custom / One-Off Task")
    if not tasks:
        print("     (No saved tasks found yet. Use [0] to run a task or [A] to add one.)")
    else:
        for idx, t in enumerate(tasks, 1):
            goal_short = t['goal'][:60] + "..." if len(t['goal']) > 60 else t['goal']
            print(f" [{idx}] {t['name']:<15} -> Goal: {goal_short}")
            print(f"     URL: {t['url']} | Mode: {t['mode']}")

    print("-" * 70)
    print(" [A] Add Preset   | [R] Remove Preset   | [Q] Quit")
    print("=" * 70 + "\n")
    return tasks

def interactive_run_custom():
    print("\n🚀 RUN CUSTOM ONE-OFF TASK")
    goal = input("Enter Goal Description: ").strip()
    if not goal:
        print("❌ Goal cannot be empty.")
        return
    url = input("Enter Target URL: ").strip()
    if not url:
        print("❌ Target URL cannot be empty.")
        return
    mode = input("Operational Mode (visual/dom/hybrid) [default: visual]: ").strip().lower() or "visual"
    save_name = input("Save as preset for future use? (enter name or press ENTER to skip): ").strip()
    
    if save_name:
        add_task(name=save_name, goal=goal, url=url, mode=mode)
        print(f"💾 Saved preset '{save_name}'.")

    print(f"\n🚀 Launching Custom Task: '{goal}'...")
    res = run_agent(goal=goal, url=url, mode=mode)
    print_result_summary(save_name or "Custom Task", res)

def interactive_add():
    print("\n➕ ADD NEW TASK PRESET")
    name = input("Task Name (e.g., check_invoices): ").strip()
    if not name:
        print("❌ Task name cannot be empty.")
        return
    goal = input("Natural Language Goal: ").strip()
    if not goal:
        print("❌ Goal cannot be empty.")
        return
    url = input("Target URL: ").strip()
    if not url:
        print("❌ Target URL cannot be empty.")
        return
    mode = input("Operational Mode (visual/dom/hybrid) [default: visual]: ").strip().lower() or "visual"
    
    add_task(name=name, goal=goal, url=url, mode=mode)
    print(f"✅ Saved task preset '{name}' successfully!")

def interactive_remove():
    tasks = list_tasks()
    if not tasks:
        print("❌ No tasks to remove.")
        return
    name = input("Enter task name to remove: ").strip()
    if remove_task(name):
        print(f"🗑️ Removed task preset '{name}' successfully.")
    else:
        print(f"❌ Task preset '{name}' not found.")

def print_result_summary(task_label: str, summary_data: dict):
    final_status = summary_data.get("final_status", "Completed")
    self_assess = summary_data.get("self_assessment") or {}
    
    if "Failed" in final_status or final_status.startswith("Stuck"):
        status_code = "FAILED"
        accomplishment = summary_data.get("final_status")
    elif self_assess.get("completion_status"):
        status_code = self_assess.get("completion_status").upper()
        accomplishment = self_assess.get("accomplishment_summary", final_status)
    else:
        status_code = "COMPLETED"
        accomplishment = final_status

    print("\n" + "🔔" * 35)
    print(f"🔔 TASK EXECUTION RESULT SUMMARY")
    print(f"Task: {task_label}")
    print(f"Status: {status_code} ({final_status})")
    print(f"Accomplishment: {accomplishment}")
    print("🔔" * 35 + "\n")

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        tasks = list_tasks()
        if arg == "0":
            interactive_run_custom()
            return
        elif arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(tasks):
                t = tasks[idx]
                print(f"🚀 Quick-Launching Task #{arg}: '{t['name']}'...")
                res = run_agent(goal=t["goal"], url=t["url"], mode=t["mode"], session_file=t.get("session"))
                print_result_summary(t['name'], res)
                return
        else:
            t = get_task(arg)
            if t:
                print(f"🚀 Quick-Launching Task '{arg}'...")
                res = run_agent(goal=t["goal"], url=t["url"], mode=t["mode"], session_file=t.get("session"))
                print_result_summary(arg, res)
                return
            else:
                print(f"❌ Task preset '{arg}' not found.")
                return

    while True:
        tasks = display_menu()
        choice = input("Select a task number or option [0-N/A/R/Q]: ").strip().upper()
        
        if choice == "Q":
            print("👋 Exiting Quick-Launch menu.")
            break
        elif choice == "0" or choice == "C":
            interactive_run_custom()
            break
        elif choice == "A":
            interactive_add()
        elif choice == "R":
            interactive_remove()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(tasks):
                t = tasks[idx]
                print(f"\n🚀 Launching Task #{choice}: '{t['name']}'...")
                res = run_agent(
                    goal=t["goal"],
                    url=t["url"],
                    mode=t["mode"],
                    session_file=t.get("session")
                )
                print_result_summary(t['name'], res)
                break
            else:
                print("❌ Invalid task number. Please try again.")
        else:
            print("❌ Invalid option. Please try again.")

if __name__ == "__main__":
    main()
