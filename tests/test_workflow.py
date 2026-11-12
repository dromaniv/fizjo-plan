import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

import yaml


class PublicationWorkflowTests(unittest.TestCase):
    def run_copy(self, root):
        workflow_path = (
            Path(__file__).resolve().parents[1] / ".github/workflows/main.yml"
        )
        workflow = yaml.safe_load(workflow_path.read_text())
        script = next(
            step["run"]
            for step in workflow["jobs"]["publish"]["steps"]
            if step.get("name") == "Copy calendar data"
        )
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            cwd=root,
            env={**os.environ, "FEED_DIR": str(root / "feeds")},
            capture_output=True,
        )

    def test_valid_calendar_data_is_copied_without_execution(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "feeds").mkdir()
            (root / "docs").mkdir()
            # Data resembling shell syntax must be copied verbatim.
            payload = b"$(touch executed)\n"
            (root / "feeds/example.ics").write_bytes(payload)
            result = self.run_copy(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "docs/example.ics").read_bytes(), payload)
            self.assertFalse((root / "executed").exists())

    def test_invalid_artifacts_stop_publication(self):
        for case in ["empty", "bad-name", "symlink", "oversized"]:
            with self.subTest(case=case), TemporaryDirectory() as directory:
                root = Path(directory)
                feeds = root / "feeds"
                feeds.mkdir()
                (root / "docs").mkdir()
                if case == "bad-name":
                    (feeds / "bad name.ics").write_text("data")
                elif case == "symlink":
                    (root / "target").write_text("data")
                    (feeds / "example.ics").symlink_to(root / "target")
                elif case == "oversized":
                    (feeds / "example.ics").write_bytes(b"x" * 2097153)
                self.assertNotEqual(self.run_copy(root).returncode, 0)
                self.assertEqual(list((root / "docs").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
