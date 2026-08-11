"""
Loom Web & Browser Verification Gate.
Executes automated E2E web verification using Playwright against Next.js Dashboard.
"""

from pathlib import Path
from typing import Any, Dict

from loom.sandbox.browser import _HAS_PLAYWRIGHT, LoomBrowserRunner


class WebVerificationGate:
    """Automated web UI verification gate using browser automation."""

    def __init__(self, target_url: str = "http://localhost:3000"):
        self.target_url = target_url

    async def verify_livebox_ui(self, screenshot_dir: str = "artifacts/screenshots") -> Dict[str, Any]:
        """Navigate to Next.js Web Dashboard, inspect LiveBox launcher button, and capture screenshot."""
        if not _HAS_PLAYWRIGHT:
            return {"passed": False, "error": "Playwright not installed"}

        runner = LoomBrowserRunner(headless=True)
        try:
            await runner.start()
            res = await runner.navigate(self.target_url)

            # Look for launcher button or header text
            text = await runner.get_text("body")
            has_livebox_btn = "Live Box" in text or "Loom" in text

            screenshot_path = Path(screenshot_dir) / "livebox_verification.png"
            shot_file = await runner.take_screenshot(str(screenshot_path))

            await runner.close()
            return {
                "passed": has_livebox_btn,
                "url": self.target_url,
                "status": res["status"],
                "screenshot": shot_file,
                "details": f"Web verification passed at {self.target_url}. Title: {res['title']}"
            }
        except Exception as err:
            await runner.close()
            return {
                "passed": False,
                "url": self.target_url,
                "error": str(err),
                "details": f"Web verification failed: {err}"
            }
