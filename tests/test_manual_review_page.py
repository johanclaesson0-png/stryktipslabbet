"""Regression tests for the human-in-the-loop, no-API Stryktipslabbet page."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "manuell-spelarkoll.html"


class ManualPlayerReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")
        match = re.search(r"<script>\s*([\s\S]*?)</script>", cls.page)
        assert match, "Missing script"
        cls.script = match.group(1)

    def test_no_api_key_or_public_write(self):
        self.assertIn("localStorage", self.script)
        self.assertIn("https://", self.page)
        self.assertNotIn("APIFOOTBALL_KEY", self.script)
        self.assertNotIn("x-apisports-key", self.script)
        self.assertNotIn("api.github.com/repos", self.script)
        self.assertNotIn("fetch('https://v3.football.api-sports.io", self.script)

    def test_real_frozen_baseline_and_exact_budget_code_exist(self):
        self.assertIn("./data/analysis-index.json", self.script)
        self.assertIn("./data/analysis/", self.script)
        self.assertIn("./data/personal/", self.script)
        self.assertIn("function optimizeExact", self.script)
        self.assertIn("cost%rows", self.script)
        self.assertIn("original", self.script)
        self.assertIn("manuell", self.page.lower())

    @unittest.skipUnless(shutil.which("node"), "JavaScript runtime unavailable")
    def test_javascript_syntax(self):
        p = subprocess.run(["node", "--check"], input=self.script, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 0, p.stderr)

    @unittest.skipUnless(shutil.which("node"), "JavaScript runtime unavailable")
    def test_probability_direction_and_exact_equal_cost(self):
        # Strip event bindings / network initialization; only exercise pure functions.
        js = self.script.split("$('round').onchange=showRound;")[0]
        code = js + r"""
const p=[0.6,0.25,0.15], homeOut=probability(p,.09,0),
    awayOut=probability(p,0,.09), untouched=probability(p,0,0),
    samples=Array.from({length:13},()=>p),
    lines=optimizeExact(samples,96),
    rows=lines.reduce((n,choice)=>n*choice.length,1);
console.log(JSON.stringify({homeOut,awayOut,untouched,rows,length:lines.length}));
"""
        p = subprocess.run(["node", "-e", code], text=True, capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        info = json.loads(p.stdout.strip())
        self.assertLess(info["homeOut"][0],0.6)
        self.assertGreater(info["awayOut"][0],0.6)
        self.assertAlmostEqual(sum(info["awayOut"]),1,places=9)
        self.assertAlmostEqual(info["untouched"][0],0.6,places=9)
        self.assertEqual(info["length"],13)
        self.assertEqual(info["rows"],96)


if __name__ == "__main__":
    unittest.main()
