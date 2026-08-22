import json
import tempfile
import unittest
from pathlib import Path

from spokenform_gold.evaluation_profiles import (
    load_registry,
    profile_hash,
    registry_hash,
    resolve_profile,
    validate_registry,
)


class EvaluationProfileTests(unittest.TestCase):
    def test_gold_v1_is_explicit_and_frozen(self):
        profile = resolve_profile("gold-v1")
        self.assertEqual(profile["kind"], "canonical")
        self.assertTrue(profile["policy_expansion"])
        self.assertEqual(
            profile["prepare_kwargs"],
            {
                "use_spacy": False,
                "normalize_literals": True,
                "generic_acronym_mode": "spell_unknown",
                "generic_acronym_case": "upper",
                "registered_acronym_mode": "spell",
                "symbol_mode": "none",
                "long_number_mode": "contextual",
                "sequence_fallback_mode": "preserve",
            },
        )

    def test_control_profile_inherits_deterministically(self):
        profile = resolve_profile("fallback-spell-0.3")
        self.assertEqual(profile["prepare_kwargs"]["use_spacy"], False)
        self.assertEqual(profile["prepare_kwargs"]["sequence_fallback_mode"], "spell")
        self.assertEqual(profile["extends"], "spokenform-default-0.3")

    def test_registry_and_profile_hashes_are_stable(self):
        registry = load_registry()
        self.assertEqual(registry_hash(registry), registry_hash(load_registry()))
        profile = resolve_profile("gold-v1")
        self.assertEqual(
            profile_hash(profile), profile_hash(resolve_profile("gold-v1"))
        )

    def test_unknown_profile_fails_closed(self):
        with self.assertRaises(ValueError):
            resolve_profile("does-not-exist")

    def test_inheritance_cycles_are_rejected(self):
        registry = {
            "version": "1.0.0",
            "profiles": {
                "a": {
                    "kind": "control",
                    "policy_expansion": False,
                    "extends": "b",
                    "prepare_kwargs": {},
                },
                "b": {
                    "kind": "control",
                    "policy_expansion": False,
                    "extends": "a",
                    "prepare_kwargs": {},
                },
            },
        }
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_registry(registry)

    def test_custom_registry_is_supported(self):
        registry = {
            "version": "2.0.0",
            "profiles": {
                "custom": {
                    "kind": "control",
                    "policy_expansion": False,
                    "prepare_kwargs": {"use_spacy": False},
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profiles.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            self.assertEqual(resolve_profile("custom", path)["name"], "custom")


if __name__ == "__main__":
    unittest.main()
