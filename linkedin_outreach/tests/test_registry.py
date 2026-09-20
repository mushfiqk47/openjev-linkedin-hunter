import json
import tempfile
import unittest
from pathlib import Path
import sys

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from outreach.registry import ConnectionsRegistry

class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.tmp_dir.name)
        self.ledger_file = self.dir_path / "Complete.md"
        self.registry_file = self.dir_path / "connections_registry.json"

        self.ledger_file.write_text(
            "- Md Hanjala (2026-08-15 10:38)\n"
            "- Ahamed Rizvi (2026-09-21 02:48:17) - SKIPPED - https://www.linkedin.com/in/ahamed-rizvi/\n"
            "- Labony Akter (2026-09-21 02:52:19) - SENT - https://www.linkedin.com/in/labony-akter-74a049303/\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_migration_from_ledger(self):
        reg = ConnectionsRegistry(path=str(self.registry_file), ledger_path=str(self.ledger_file))
        self.assertTrue(self.registry_file.exists())
        self.assertEqual(len(reg.connections), 3)

        self.assertTrue(reg.is_done("https://www.linkedin.com/in/labony-akter-74a049303/"))
        self.assertTrue(reg.is_done("labony-akter-74a049303"))
        self.assertTrue(reg.is_done("https://www.linkedin.com/in/ahamed-rizvi/"))

        self.assertTrue(reg.is_done("Md Hanjala"))

        self.assertFalse(reg.is_done("https://www.linkedin.com/in/unknown-designer/"))
        self.assertFalse(reg.is_done("Unknown Person"))

    def test_sync_contact_and_record_sent(self):
        reg = ConnectionsRegistry(path=str(self.registry_file), ledger_path=str(self.ledger_file))

        new_url = "https://www.linkedin.com/in/sarah-recruiter/"
        rec, is_new = reg.sync_contact("Sarah Recruiter", new_url, headline="Lead Talent Partner")
        self.assertTrue(is_new)
        self.assertEqual(rec["status"], "UNSENT")
        self.assertFalse(reg.is_done(new_url))

        rec2, is_new2 = reg.sync_contact("Sarah Recruiter", new_url)
        self.assertFalse(is_new2)

        reg.record_sent(rec, archetype="recruiter", relevance=92, detail="verified")
        self.assertTrue(reg.is_done(new_url))
        self.assertEqual(reg.connections["sarah-recruiter"]["status"], "SENT")
        self.assertEqual(reg.connections["sarah-recruiter"]["archetype"], "recruiter")

        content = self.ledger_file.read_text(encoding="utf-8")
        self.assertIn("Sarah Recruiter", content)
        self.assertIn("SENT", content)

    def test_mark_removed_connection(self):
        reg = ConnectionsRegistry(path=str(self.registry_file), ledger_path=str(self.ledger_file))
        slug = "labony-akter-74a049303"
        self.assertTrue(reg.connections[slug]["in_network"])

        reg.mark_removed(slug)
        self.assertFalse(reg.connections[slug]["in_network"])

        self.assertTrue(reg.is_done(slug))

if __name__ == "__main__":
    unittest.main()
