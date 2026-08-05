import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.context_vault import ContextVault
from main import run_agent

class TestPhase3EndToEnd(unittest.TestCase):
    def test_run_agent_local_canvas_task(self):
        """End-to-end test of run_agent executing on local canvas test target."""
        canvas_test_path = PROJECT_ROOT / "tests" / "canvas_test.html"
        file_url = f"file:///{str(canvas_test_path).replace('\\', '/')}"
        vault = ContextVault()

        # Execute run_agent in headless mode for 2 max steps
        summary = run_agent(
            goal="Find and click target element on canvas",
            url=file_url,
            max_steps=2,
            headless=True,
            disable_vision=True,
            vault=vault
        )

        self.assertIn("task_id", summary)
        self.assertGreaterEqual(summary["total_steps"], 1)
        self.assertIn("mode", summary)
        self.assertEqual(summary["mode"], "dom")

if __name__ == "__main__":
    unittest.main()
