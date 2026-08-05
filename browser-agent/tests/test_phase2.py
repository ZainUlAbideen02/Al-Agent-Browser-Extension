import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.context_vault import ContextVault
from agent.memory import StepMemory
from agent.reasoner import ReasonerAgent, VisualActionDecision, ActionDecision

class TestPhase2Intelligence(unittest.TestCase):
    def setUp(self):
        self.vault = ContextVault()
        self.memory = StepMemory()

    def test_step_memory_spatial_loop_detection(self):
        """Test StepMemory loop detection when same coordinate is clicked repetitively."""
        action = {"action": "click", "x": 500, "y": 300, "thought": "Clicking button"}
        result = {"success": True, "message": "Clicked at (500, 300)"}
        page_state = {"url": "https://example.com", "title": "Example"}

        for i in range(1, 4):
            self.memory.record_step(
                step_num=i,
                action_taken=action,
                result=result,
                screenshot_path=f"step_{i}.png",
                page_state=page_state
            )

        self.assertTrue(self.memory.is_spatial_loop_detected(threshold=3))
        self.assertTrue(self.memory.should_trigger_zoom_retry())
        self.memory.zoom_retry_attempts = 2
        self.assertTrue(self.memory.is_visually_stuck(threshold=3))
        self.assertIsNotNone(self.memory.get_recovery_warning())
        self.assertIn("RECOVERY WARNING", self.memory.get_summary())

    def test_vault_injection_in_reasoner(self):
        """Test ReasonerAgent initialization with ContextVault."""
        self.vault.set_value("student_id", "STU-9999")
        reasoner = ReasonerAgent(api_key="mock_key", vault=self.vault)
        self.assertEqual(reasoner.vault.get_value("student_id"), "STU-9999")

    def test_action_decision_pydantic_schemas(self):
        """Test Pydantic schema validation for Visual and DOM action decisions."""
        v_decision = VisualActionDecision(
            thought="Found text input at 100, 200",
            action="type",
            x=100,
            y=200,
            text="john.doe@example.com"
        )
        self.assertEqual(v_decision.action, "type")
        self.assertEqual(v_decision.x, 100)

        dom_decision = ActionDecision(
            action="click",
            selector="#submit-btn",
            reasoning="Clicking submit"
        )
        self.assertEqual(dom_decision.action, "click")
        self.assertEqual(dom_decision.selector, "#submit-btn")

if __name__ == "__main__":
    unittest.main()
