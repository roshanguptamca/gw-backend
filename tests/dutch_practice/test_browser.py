import os
import subprocess
import unittest
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase


@unittest.skipUnless(os.environ.get("RUN_DUTCH_BROWSER_TESTS") == "1", "Opt-in real-browser integration")
class DutchBrowserTests(LiveServerTestCase):
    def test_authenticated_full_mock_journeys(self):
        frontend = Path(os.environ["DUTCH_FRONTEND_DIR"])
        user = get_user_model().objects.create_user("browser-exam-learner")
        self.client.force_login(user)
        environment = {
            **os.environ,
            "DUTCH_LIVE_SERVER": self.live_server_url,
            "DUTCH_TEST_SESSION": self.client.cookies["sessionid"].value,
        }
        result = subprocess.run(
            ["node", str(frontend / "tests/e2e/dutch-mock-live.cjs")],
            cwd=frontend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=480,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout)
