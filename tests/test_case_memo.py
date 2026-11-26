"""The case's last level is remembered while the buds don't report it."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import setu


def reading(case_level, charging=False, at=None):
    lvl = lambda v: {"level": v, "charging": False}  # noqa: E731
    return {"parts": {"left": lvl(100), "right": lvl(90), "case": {"level": case_level, "charging": charging}},
            "at": at or time.time(), "path": "", "address": ""}


class CaseMemo(unittest.TestCase):
    def setUp(self):
        self.p = SimpleNamespace(case_memo={})
        self.save = mock.patch.object(setu.util, "save_state").start()
        self.addCleanup(mock.patch.stopall)

    def run_(self, r):
        return setu.Plugin.with_case(self.p, "AA:BB:CC:00:00:02", r)

    def test_heard_case_is_remembered(self):
        self.run_(reading(80, charging=True))
        self.assertEqual(self.p.case_memo["AA:BB:CC:00:00:02"]["level"], 80)
        self.save.assert_called_once()

    def test_silent_case_filled_from_memory(self):
        self.run_(reading(80, charging=True))
        out = self.run_(reading(None))
        case = out["parts"]["case"]
        self.assertEqual((case["level"], case["charging"]), (80, True))
        self.assertIn("remembered", case)

    def test_old_charging_not_claimed(self):
        self.p.case_memo["AA:BB:CC:00:00:02"] = {"level": 60, "charging": True, "at": time.time() - 7200}
        case = self.run_(reading(None))["parts"]["case"]
        self.assertEqual((case["level"], case["charging"]), (60, False))

    def test_nothing_known_stays_unknown(self):
        self.assertIsNone(self.run_(reading(None))["parts"]["case"]["level"])


if __name__ == "__main__":
    unittest.main()
