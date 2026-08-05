import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.context_vault import ContextVault, DEFAULT_PROFILE_VAULT
from browser.controller import BrowserController
from browser.actions import validate_and_clamp_coordinates, execute_visual_action, execute_action

class TestPhase1ContextVault(unittest.TestCase):
    def setUp(self):
        self.vault_file = PROJECT_ROOT / "tests" / "temp_vault.json"
        if self.vault_file.exists():
            self.vault_file.unlink()
        self.vault = ContextVault(vault_path=str(self.vault_file))

    def tearDown(self):
        if self.vault_file.exists():
            self.vault_file.unlink()

    def test_default_vault_keys(self):
        """Test default pre-filled fields in ContextVault."""
        self.assertEqual(self.vault.get_value("full_name"), "John Alexander Doe")
        self.assertEqual(self.vault.get_value("roll_number"), "STU-2026-8891")
        self.assertEqual(self.vault.get_value("email"), "john.doe@example.com")
        self.assertEqual(self.vault.get_value("program"), "Computer Science")
        self.assertEqual(self.vault.get_value("degree"), "Bachelor of Science in Computer Science")
        self.assertEqual(self.vault.get_value("university"), "Stanford University")

    def test_fuzzy_field_resolution(self):
        """Test resolve_field mapping fuzzy labels to profile keys."""
        # Roll number aliases
        self.assertEqual(self.vault.resolve_field("Student ID"), "STU-2026-8891")
        self.assertEqual(self.vault.resolve_field("Roll No"), "STU-2026-8891")
        self.assertEqual(self.vault.resolve_field("University ID"), "STU-2026-8891")
        self.assertEqual(self.vault.resolve_field("Reg No"), "STU-2026-8891")

        # Name aliases
        self.assertEqual(self.vault.resolve_field("Full Name"), "John Alexander Doe")
        self.assertEqual(self.vault.resolve_field("Student Name"), "John Alexander Doe")

        # Email & Academic aliases
        self.assertEqual(self.vault.resolve_field("Email Address"), "john.doe@example.com")
        self.assertEqual(self.vault.resolve_field("Major"), "Computer Science")
        self.assertEqual(self.vault.resolve_field("College"), "Stanford University")

    def test_custom_user_defined_field(self):
        """Test custom user-defined field insertion and resolution."""
        self.vault.set_value("gpa", "3.95")
        self.assertEqual(self.vault.get_value("gpa"), "3.95")
        self.assertEqual(self.vault.resolve_field("GPA Score"), "3.95")

class TestPhase1ControllerAndActions(unittest.TestCase):
    def test_coordinate_clamping(self):
        """Test coordinate clamping to viewport boundaries and low_confidence flag."""
        cx, cy, low_conf = validate_and_clamp_coordinates(-10, 900, 1280, 800)
        self.assertEqual(cx, 0)
        self.assertEqual(cy, 799)
        self.assertTrue(low_conf)

        cx, cy, low_conf = validate_and_clamp_coordinates(500, 400, 1280, 800)
        self.assertEqual(cx, 500)
        self.assertEqual(cy, 400)
        self.assertFalse(low_conf)

    def test_controller_initialization_and_headless_start(self):
        """Test BrowserController lifecycle with local canvas test HTML."""
        canvas_test_path = PROJECT_ROOT / "tests" / "canvas_test.html"
        file_url = f"file:///{str(canvas_test_path).replace('\\', '/')}"

        controller = BrowserController(width=1280, height=800)
        try:
            controller.start(headless=True)
            controller.goto(file_url)
            state = controller.get_visual_state()

            self.assertEqual(state["viewport_width"], 1280)
            self.assertEqual(state["viewport_height"], 800)
            self.assertIn("Canvas UI", state["page_title"])
            self.assertTrue(len(state["base64_image"]) > 100)

            # Test scroll & wait action
            succ, msg, low_conf = execute_visual_action(controller, {"action": "scroll", "direction": "down", "amount": 200})
            self.assertTrue(succ)

            succ, msg, low_conf = execute_visual_action(controller, {"action": "wait"})
            self.assertTrue(succ)

            # Test done action
            succ, msg, low_conf = execute_visual_action(controller, {"action": "done", "reasoning": "Completed test"})
            self.assertTrue(succ)
        finally:
            controller.close()

if __name__ == "__main__":
    unittest.main()
