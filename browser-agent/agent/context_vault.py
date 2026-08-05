import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("browser_agent.agent.context_vault")

DEFAULT_PROFILE_VAULT: Dict[str, Any] = {
    "full_name": "John Alexander Doe",
    "legal_name": "John Alexander Doe",
    "first_name": "John",
    "last_name": "Doe",
    "roll_number": "STU-2026-8891",
    "student_roll_number": "STU-2026-8891",
    "email": "john.doe@example.com",
    "program": "Computer Science",
    "degree": "Bachelor of Science in Computer Science",
    "university": "Stanford University",
    "username": "tomsmith",
    "password": "SuperSecretPassword!",
    "employee_id": "EMP-9042",
    "phone": "+1-555-0199",
    "address": "123 Innovation Way, Tech Suite 400, San Francisco, CA 94105",
    "city": "San Francisco",
    "state": "CA",
    "zip_code": "94105",
    "country": "United States",
    "document_path": r"C:\Users\zain\OneDrive\Desktop\Al Agent Browser Extension\browser-agent\tests\sample_doc.pdf"
}

# Alias dictionary mapping canonical profile keys to common search queries / form label hints
FIELD_ALIAS_MAP: Dict[str, List[str]] = {
    "roll_number": [
        "roll_number", "roll_no", "roll", "student_id", "university_id",
        "reg_no", "registration_number", "student_roll_number", "id_number",
        "student_code", "roll#", "student_no", "rollno", "studentid"
    ],
    "full_name": [
        "full_name", "legal_name", "name", "student_name", "user_name",
        "applicant_name", "first_name", "last_name", "your_name", "fullname"
    ],
    "email": [
        "email", "e_mail", "mail", "email_address", "contact_email", "user_email"
    ],
    "program": [
        "program", "major", "field_of_study", "department", "course", "study_program", "branch"
    ],
    "degree": [
        "degree", "qualification", "academic_degree", "degree_title", "education_level"
    ],
    "university": [
        "university", "college", "institute", "school", "varsity", "institution", "uni", "campus"
    ],
    "username": [
        "username", "user_id", "login_id", "handle", "account_name", "login", "user"
    ],
    "password": [
        "password", "pass", "secret", "passcode", "pwd"
    ],
    "phone": [
        "phone", "mobile", "contact", "cell", "telephone", "phone_number", "contact_no"
    ],
    "address": [
        "address", "street", "residence", "location", "address_line"
    ],
    "city": ["city", "town"],
    "state": ["state", "province"],
    "zip_code": ["zip", "zip_code", "postal", "postal_code", "zipcode"],
    "country": ["country", "nation"],
    "employee_id": ["employee_id", "emp_id", "staff_id", "employee_number"],
    "document_path": ["file", "document", "cv", "resume", "upload", "attachment", "doc_path"]
}

class ContextVault:
    """
    Structured Dynamic Profile Vault storing user credentials, personal attributes,
    academic/employee roll numbers, emails, addresses, and document paths.
    Exposes key-value retrieval, robust fuzzy/alias context resolution mapping,
    and LLM system prompt context injection.
    """

    def __init__(self, vault_path: Optional[str] = None):
        self.vault_path = Path(vault_path) if vault_path else Path(__file__).resolve().parent.parent / "config" / "user_profile.json"
        self._data: Dict[str, Any] = {}
        self.load_vault()

    def load_vault(self) -> None:
        """Load profile vault from JSON file or initialize with default values if missing."""
        if self.vault_path.exists():
            try:
                with open(self.vault_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                # Merge loaded data with defaults to ensure all required pre-filled keys exist
                self._data = DEFAULT_PROFILE_VAULT.copy()
                self._data.update(file_data)
                logger.info(f"Loaded context vault with {len(self._data)} keys from {self.vault_path}")
                return
            except Exception as e:
                logger.warning(f"Failed to load vault file {self.vault_path}: {e}. Falling back to default profile.")
        
        self._data = DEFAULT_PROFILE_VAULT.copy()
        self.save_vault()

    def save_vault(self) -> None:
        """Persist profile vault data to JSON file."""
        try:
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.vault_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            logger.info(f"Saved context vault to {self.vault_path}")
        except Exception as e:
            logger.error(f"Failed to save context vault: {e}")

    def get_context_for_prompt(self) -> str:
        """
        Formats available profile vault keys for system prompt injection.
        Allows multimodal vision LLM to auto-populate form fields using exact values.
        """
        keys_summary = []
        for k, v in self._data.items():
            val_preview = "******" if "password" in k.lower() or "secret" in k.lower() else str(v)
            keys_summary.append(f"'{k}': '{val_preview}'")
        return "{ " + ", ".join(keys_summary) + " }"

    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve exact key value from vault."""
        val = self._data.get(key, default)
        return str(val) if val is not None else None

    def resolve_field(self, query_str: str) -> Optional[str]:
        """
        Robust fuzzy/alias key resolver. Maps query strings like 'Student ID', 'Roll No',
        'University ID', 'Degree', 'Email' to corresponding canonical profile keys and returns the value.
        Supports custom user-defined account fields.
        """
        if not query_str:
            return None

        # 1. Clean query string
        clean_query = query_str.strip().lower().replace("-", "_").replace(" ", "_").replace("#", "")

        # 2. Exact match in stored keys
        if clean_query in self._data:
            return str(self._data[clean_query])

        # 3. Check alias dictionary mapping
        for canonical_key, aliases in FIELD_ALIAS_MAP.items():
            for alias in aliases:
                alias_clean = alias.replace("-", "_").replace(" ", "_").replace("#", "")
                if clean_query == alias_clean:
                    if canonical_key in self._data:
                        return str(self._data[canonical_key])

        # 4. Fuzzy substring matching: check if query contains any alias or alias contains query
        for canonical_key, aliases in FIELD_ALIAS_MAP.items():
            for alias in aliases:
                alias_clean = alias.replace("-", "_").replace(" ", "_").replace("#", "")
                if alias_clean in clean_query or clean_query in alias_clean:
                    if canonical_key in self._data:
                        return str(self._data[canonical_key])

        # 5. Fuzzy matching against any custom user-defined keys in vault
        for key, val in self._data.items():
            key_clean = key.lower().replace("-", "_").replace(" ", "_")
            if key_clean in clean_query or clean_query in key_clean:
                return str(val)

        return None

    def resolve_field_value(self, field_hint: str) -> Optional[str]:
        """Backward-compatible wrapper for resolve_field."""
        return self.resolve_field(field_hint)

    def set_value(self, key: str, value: Any) -> None:
        """Update or insert key in vault and persist."""
        self._data[key] = value
        self.save_vault()
