import json
import tempfile
import unittest
from pathlib import Path
from gdn_brain import connect, put_project, get_project, list_projects, add_checkpoint, import_jack

class BrainTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"private"/"brain.sqlite3"
    def tearDown(self):
        self.tmp.cleanup()
    def test_project_lifecycle(self):
        v=put_project(self.db,id="sample-project",name="Example project",
                      next_action="Run tests",actor="test",source_ref="unit-test")
        self.assertEqual(v["version"],1)
        self.assertEqual(len(list_projects(self.db)),1)
        with self.assertRaisesRegex(ValueError,"expected_version"):
            put_project(self.db,id="sample-project",status="active")
        new=put_project(self.db,id="sample-project",status="active",expected_version=1)
        self.assertEqual(new["version"],2)
        with self.assertRaises(ValueError):
            put_project(self.db,id="sample-project",status="done",expected_version=1)
        ev=add_checkpoint(self.db,id="sample-project",detail="Smoke test passed",
                          actor="tester",source_ref="unit-test:1",evidence="verified",kind="test")
        self.assertTrue(ev["event_id"])
        self.assertEqual(get_project(self.db,id="sample-project")["events"][0]["evidence"],"verified")
    def test_private_files(self):
        with connect(self.db): pass
        self.assertEqual(self.db.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.db.parent.stat().st_mode & 0o777,0o700)
    def test_secrets_rejected(self):
        with self.assertRaisesRegex(ValueError,"secret"):
            put_project(self.db,id="secret-test",name="password=definitely_not_safe")
    def test_jack_import_is_idempotent(self):
        reg=Path(self.tmp.name)/"registry.json"
        reg.write_text(json.dumps({"projects":[{"id":"100BTC-TEST","title":"Test idea"}]}))
        x=import_jack(self.db,reg)
        y=import_jack(self.db,reg)
        self.assertEqual(x["imported"],1)
        self.assertEqual(y["imported"],0)
        self.assertEqual(get_project(self.db,id="jack-100BTC-TEST")["status"],"needs_review")

if __name__=="__main__":
    unittest.main()
