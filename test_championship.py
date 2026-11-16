import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import championship as c

class ChampionshipTests(unittest.TestCase):
    def test_unique_strategies(self):
        state = c.initial()
        self.assertEqual(len(state["bots"]), 30)
        self.assertEqual(len(set((b["kind"], b["a"], b["b"]) for b in state["bots"])), 30)

    def test_exposure_and_stop_loss(self):
        state = c.initial()
        bot = state["bots"][0]
        with patch.object(c, "signal", return_value=1):
            events = c.tick(state, 4000.0, "2026-11-16T10:00:00+00:00")
        self.assertEqual(events[0][2], "BUY")
        self.assertGreater(bot["cash"], 7400)
        self.assertLess(bot["oz"] * 4000, 2500)
        entry = bot["entry"]
        with patch.object(c, "signal", return_value=None):
            events = c.tick(state, entry * 0.97, "2026-11-16T10:01:00+00:00")
        self.assertEqual(events[0][3], "stop_loss")
        self.assertEqual(bot["oz"], 0)

    def test_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(c, "DATA", Path(d)):
                c.save_events([["time", 1, "BUY", "signal", 4000, 4001, 0.5, 0.8, 8000]])
                lines = (Path(d) / "trades.csv").read_text().splitlines()
                self.assertEqual(len(lines), 2)

if __name__ == "__main__":
    unittest.main()
