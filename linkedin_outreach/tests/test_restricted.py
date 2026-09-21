import os
import sys
import tempfile
import unittest
from pathlib import Path

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from outreach.registry import ConnectionsRegistry
from outreach.restricted import (apply_restricted_scan, is_restricted,
                                 load_restricted_list)
from outreach.pipeline import PipelineParams, run_pipeline

class TestRestrictedAccounts(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.tmp_dir.name)
        self.restricted_file = self.dir_path / "restricted.txt"
        self.ledger_file = self.dir_path / "Complete.md"
        self.registry_file = self.dir_path / "connections_registry.json"

        self.restricted_file.write_text(
            "# Comment line\n"
            "\n"
            "John Doe\n"
            "https://www.linkedin.com/in/sarah-connor/\n"
            "toxic-recruiter\n",
            encoding="utf-8",
        )

        self.ledger_file.write_text("", encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_restricted_list(self):
        data = load_restricted_list(file_path=str(self.restricted_file), force_reload=True)
        self.assertIn("john doe", data["names"])
        self.assertIn("sarah-connor", data["slugs"])
        self.assertIn("toxic-recruiter", data["slugs"])
        self.assertEqual(len(data["raw"]), 3)

    def test_is_restricted_by_name(self):
        data = load_restricted_list(file_path=str(self.restricted_file), force_reload=True)

        # Exact and case-insensitive
        res, reason = is_restricted({"name": "John Doe"}, restricted_data=data)
        self.assertTrue(res)
        self.assertIn("john doe", reason.lower())

        res2, _ = is_restricted({"name": "  JOHN DOE • 1st  "}, restricted_data=data)
        self.assertTrue(res2)

        # Not restricted
        res3, _ = is_restricted({"name": "Jane Smith"}, restricted_data=data)
        self.assertFalse(res3)

    def test_is_restricted_by_url_and_slug(self):
        data = load_restricted_list(file_path=str(self.restricted_file), force_reload=True)

        res, reason = is_restricted(
            {"name": "Different Name", "profile_url": "https://www.linkedin.com/in/sarah-connor?trk=xyz"},
            restricted_data=data,
        )
        self.assertTrue(res)
        self.assertIn("sarah-connor", reason)

        res2, reason2 = is_restricted(
            {"name": "Any Name", "compose_url": "https://www.linkedin.com/messaging/compose/?profileUrn=urn%3Ali%3Afsd_profile%3Atoxic-recruiter"},
            restricted_data=data,
        )
        self.assertTrue(res2)

    def test_apply_restricted_scan_and_registry_methods(self):
        reg = ConnectionsRegistry(path=str(self.registry_file), ledger_path=str(self.ledger_file))

        # Add 3 contacts
        reg.sync_contact("John Doe", "https://www.linkedin.com/in/john-doe/")
        reg.sync_contact("Alice Designer", "https://www.linkedin.com/in/alice-designer/")
        reg.sync_contact("Sarah Connor", "https://www.linkedin.com/in/sarah-connor/")

        self.assertEqual(len(reg.get_unsent_pool()), 3)

        # Apply restricted scan
        count = apply_restricted_scan(reg, file_path=str(self.restricted_file))
        self.assertEqual(count, 2)  # John Doe and Sarah Connor

        # Verify status in registry
        self.assertEqual(reg.connections["john-doe"]["status"], "RESTRICTED")
        self.assertEqual(reg.connections["john-doe"]["archetype"], "restricted_account")
        self.assertEqual(reg.connections["sarah-connor"]["status"], "RESTRICTED")
        self.assertEqual(reg.connections["alice-designer"]["status"], "UNSENT")

        # Verify excluded from unsent pool
        unsent = reg.get_unsent_pool()
        self.assertEqual(len(unsent), 1)
        self.assertEqual(unsent[0]["name"], "Alice Designer")

        # Verify is_done() returns True for restricted contacts
        self.assertTrue(reg.is_done("https://www.linkedin.com/in/john-doe/"))
        self.assertTrue(reg.is_done("John Doe"))
        self.assertTrue(reg.is_done("https://www.linkedin.com/in/sarah-connor/"))
        self.assertFalse(reg.is_done("Alice Designer"))

        # Verify written to Complete.md
        ledger_text = self.ledger_file.read_text(encoding="utf-8")
        self.assertIn("RESTRICTED", ledger_text)
        self.assertIn("John Doe", ledger_text)

        # Stats check
        stats = reg.get_stats()
        self.assertEqual(stats["restricted"], 2)
        self.assertEqual(stats["unsent"], 1)

    def test_pipeline_dry_run_intercepts_restricted(self):
        from unittest.mock import patch

        reg = ConnectionsRegistry(path=str(self.registry_file), ledger_path=str(self.ledger_file))
        reg.sync_contact("John Doe", "https://www.linkedin.com/in/john-doe/")
        reg.sync_contact("Alice Designer", "https://www.linkedin.com/in/alice-designer/")

        import outreach.restricted as r_mod
        saved_file = r_mod.RESTRICTED_FILE
        r_mod.RESTRICTED_FILE = str(self.restricted_file)
        r_mod._restricted_cache = None

        try:
            with patch("outreach.pipeline.sync_network", return_value=[]):
                params = PipelineParams(limit=5, top=2, dry_run=True)
                res = run_pipeline(params, registry=reg)

                self.assertEqual(res.restricted, 1)
                self.assertEqual(res.sent, 1)  # Alice simulated
        finally:
            r_mod.RESTRICTED_FILE = saved_file
            r_mod._restricted_cache = None

if __name__ == "__main__":
    unittest.main()
