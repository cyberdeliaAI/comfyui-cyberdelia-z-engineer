"""Guard the Registry upload against bypassing the project's test suites."""

from pathlib import Path
import re
import unittest


class RegistryWorkflowTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/publish.yml"
        self.workflow = path.read_text(encoding="utf-8")
        # This workflow uses one job with ordinary, ordered GitHub Actions steps.
        self.steps = re.split(r"(?m)^      - ", self.workflow)[1:]

    def test_both_suites_run_in_the_publish_job_before_the_upload(self):
        self.assertEqual(re.findall(r"(?m)^  ([\w-]+):$", self.workflow.split("jobs:\n", 1)[1]), ["publish-node"])
        publish = next(i for i, step in enumerate(self.steps) if "uses: Comfy-Org/publish-node-action@" in step)
        for command in (
            "python -m unittest discover -s tests -v",
            "node --test tests/test_wildcard_frontend.mjs",
        ):
            matches = [i for i, step in enumerate(self.steps) if f"run: {command}\n" in step]
            self.assertEqual(len(matches), 1, f"Missing mandatory test command: {command}")
            self.assertLess(matches[0], publish)
            self.assertNotRegex(self.steps[matches[0]], r"(?m)^\s+if:")

    def test_test_failures_cannot_be_ignored_before_publication(self):
        self.assertNotRegex(self.workflow, r"continue-on-error:\s*true")
        self.assertNotIn("always()", self.workflow)
        self.assertNotIn("failure()", self.workflow)
        self.assertNotIn("|| true", self.workflow)


if __name__ == "__main__":
    unittest.main()
