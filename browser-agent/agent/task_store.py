import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("browser_agent.agent.task_store")

TASKS_FILE = Path(__file__).resolve().parent.parent / "config" / "saved_tasks.json"

DEFAULT_SAVED_TASKS: Dict[str, Any] = {}

def get_saved_tasks() -> Dict[str, Any]:
    """Load dictionary of all saved tasks from config/saved_tasks.json."""
    if TASKS_FILE.exists():
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Failed to read tasks file {TASKS_FILE}: {e}")

    # Initialize empty tasks store if missing
    save_all_tasks(DEFAULT_SAVED_TASKS)
    return {}

def save_all_tasks(tasks: Dict[str, Any]) -> None:
    """Persist tasks dictionary to config/saved_tasks.json."""
    try:
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)
        logger.info(f"Saved {len(tasks)} tasks to {TASKS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save tasks file {TASKS_FILE}: {e}")

def add_task(name: str, goal: str, url: str, mode: str = "visual", session: Optional[str] = None) -> Dict[str, Any]:
    """Add or update a saved task preset."""
    tasks = get_saved_tasks()
    task_entry = {
        "goal": goal,
        "url": url,
        "mode": mode
    }
    if session:
        task_entry["session"] = session
    tasks[name] = task_entry
    save_all_tasks(tasks)
    return task_entry

def remove_task(name: str) -> bool:
    """Remove a saved task by name."""
    tasks = get_saved_tasks()
    if name in tasks:
        del tasks[name]
        save_all_tasks(tasks)
        return True
    return False

def get_task(name: str) -> Optional[Dict[str, Any]]:
    """Retrieve a specific task preset by name."""
    tasks = get_saved_tasks()
    return tasks.get(name)

def list_tasks() -> List[Dict[str, Any]]:
    """Returns formatted list of all saved task presets."""
    tasks = get_saved_tasks()
    result = []
    for name, data in tasks.items():
        result.append({
            "name": name,
            "goal": data.get("goal", ""),
            "url": data.get("url", ""),
            "mode": data.get("mode", "visual"),
            "session": data.get("session")
        })
    return result
