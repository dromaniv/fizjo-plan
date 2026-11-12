import os
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import yaml


class PublicationWorkflowTests(unittest.TestCase):
    def workflow_script(self, job, name):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/main.yml"
        workflow = yaml.safe_load(path.read_text())
        return next(
            step["run"]
            for step in workflow["jobs"][job]["steps"]
            if step.get("name") == name
        )

    def run_copy(self, root):
        script = (
            Path(__file__).resolve().parents[1]
            / ".github/scripts/copy-calendar-feeds.sh"
        )
        return subprocess.run(
            ["bash", str(script)],
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
        for case in ["empty", "bad-name", "symlink", "oversized", "directory", "mixed"]:
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
                elif case == "directory":
                    (feeds / "example.ics").mkdir()
                elif case == "mixed":
                    (feeds / "a-valid.ics").write_text("data")
                    (feeds / "z invalid.ics").write_text("data")
                self.assertNotEqual(self.run_copy(root).returncode, 0)
                self.assertEqual(list((root / "docs").iterdir()), [])

    def test_artifact_size_boundary_and_spaces_in_parent_directory(self):
        with TemporaryDirectory(prefix="calendar artifact ") as directory:
            root = Path(directory)
            (root / "feeds").mkdir()
            (root / "docs").mkdir()
            payload = b"x" * 2097152
            (root / "feeds/example.ics").write_bytes(payload)
            result = self.run_copy(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "docs/example.ics").read_bytes(), payload)

    def git(self, root, *args):
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def test_commit_push_unchanged_and_concurrent_update(self):
        script = self.workflow_script("publish", "Commit and push calendars")
        for case in ["changed", "unchanged", "concurrent-push", "commit-failure"]:
            with self.subTest(case=case), TemporaryDirectory() as directory:
                root = Path(directory)
                remote = root / "remote.git"
                self.git(root, "init", "--bare", str(remote))
                publisher = root / "publisher"
                publisher.mkdir()
                self.git(publisher, "init", "--initial-branch=main")
                self.git(publisher, "config", "user.name", "test")
                self.git(publisher, "config", "user.email", "test@example.invalid")
                (publisher / "docs").mkdir()
                (publisher / "docs/example.ics").write_text("original\n")
                self.git(publisher, "add", "docs/example.ics")
                self.git(publisher, "commit", "-m", "Initial feed")
                self.git(publisher, "remote", "add", "origin", str(remote))
                self.git(publisher, "push", "origin", "HEAD:main")
                original = self.git(publisher, "rev-parse", "HEAD")
                self.git(publisher, "checkout", "--detach", original)
                expected_remote = original
                if case != "unchanged":
                    (publisher / "docs/example.ics").write_text("updated\n")
                if case == "concurrent-push":
                    other = root / "other"
                    self.git(root, "clone", "--branch", "main", str(remote), str(other))
                    self.git(other, "config", "user.name", "test")
                    self.git(other, "config", "user.email", "test@example.invalid")
                    (other / "README.md").write_text("A concurrent maintainer change\n")
                    self.git(other, "add", "README.md")
                    self.git(other, "commit", "-m", "Concurrent change")
                    self.git(other, "push", "origin", "HEAD:main")
                    expected_remote = self.git(other, "rev-parse", "HEAD")
                elif case == "commit-failure":
                    hook = publisher / ".git/hooks/pre-commit"
                    hook.write_text("#!/bin/sh\nexit 1\n")
                    hook.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-e", "-o", "pipefail", "-c", script],
                    cwd=publisher,
                    env={**os.environ, "GH_TOKEN": "dummy-local-test-token"},
                    capture_output=True,
                )
                remote_head = self.git(
                    root, "--git-dir=" + str(remote), "rev-parse", "refs/heads/main"
                )
                if case == "changed":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotEqual(remote_head, original)
                    self.assertEqual(
                        self.git(
                            root,
                            "--git-dir=" + str(remote),
                            "show",
                            "main:docs/example.ics",
                        ),
                        "updated",
                    )
                else:
                    self.assertEqual(remote_head, expected_remote)
                    self.assertEqual(result.returncode == 0, case == "unchanged")

    def test_pages_build_success_errors_and_timeout(self):
        script = self.workflow_script("pages", "Rebuild and verify GitHub Pages")
        cases = {
            "built": ["built"],
            "queued-to-built": ["queued", "building", "built"],
            "errored": ["errored"],
            "unknown-status": ["unexpected"],
            "timeout": ["building"],
            "api-failure": ["api-failure"],
        }
        for case, statuses in cases.items():
            with self.subTest(case=case), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "statuses.json").write_text(json.dumps(statuses))
                fake_gh = root / "gh"
                fake_gh.write_text(
                    f"#!{sys.executable}\n"
                    + """import json, pathlib, sys
root = pathlib.Path(__file__).parent
statuses = json.loads((root / 'statuses.json').read_text())
with (root / 'calls.jsonl').open('a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if statuses[0] == 'api-failure':
    sys.exit(1)
if '--method' in sys.argv:
    print('https://api.github.com/repos/example/repo/pages/builds/latest')
else:
    index_path = root / 'index'
    index = int(index_path.read_text()) if index_path.exists() else 0
    print(statuses[min(index, len(statuses) - 1)])
    index_path.write_text(str(index + 1))
"""
                )
                fake_gh.chmod(0o755)
                fake_sleep = root / "sleep"
                fake_sleep.write_text("#!/bin/sh\nexit 0\n")
                fake_sleep.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-e", "-o", "pipefail", "-c", script],
                    cwd=root,
                    env={
                        **os.environ,
                        "PATH": str(root) + os.pathsep + os.environ["PATH"],
                        "GITHUB_REPOSITORY": "example/repo",
                        "GH_TOKEN": "dummy-local-test-token",
                    },
                    capture_output=True,
                )
                self.assertEqual(
                    result.returncode == 0,
                    case in ["built", "queued-to-built"],
                    result.stderr,
                )
                calls = [
                    json.loads(line)
                    for line in (root / "calls.jsonl").read_text().splitlines()
                ]
                self.assertEqual(
                    calls[0],
                    [
                        "api",
                        "--method",
                        "POST",
                        "repos/example/repo/pages/builds",
                        "--jq",
                        ".url",
                    ],
                )
                if case == "timeout":
                    self.assertEqual(len(calls), 31)


if __name__ == "__main__":
    unittest.main()
