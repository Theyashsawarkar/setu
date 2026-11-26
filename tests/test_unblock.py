"""bluez.unblock: lifts a soft block, reports one it couldn't lift."""
import unittest
from unittest import mock

from setu import bluez


class Unblock(unittest.TestCase):
    def run_unblock(self, rfkill_code, blocked_after):
        with mock.patch.object(bluez.util, "run", return_value=(rfkill_code, "")), \
             mock.patch.object(bluez, "adapter", return_value={"state": "off", "blocked": blocked_after}), \
             mock.patch.object(bluez.time, "sleep"):
            return bluez.unblock()

    def test_soft_block_lifted(self):
        self.assertEqual(self.run_unblock(0, False), 0)

    def test_hard_block_stays(self):
        self.assertEqual(self.run_unblock(0, True), 1)

    def test_rfkill_fails(self):
        self.assertEqual(self.run_unblock(1, True), 1)


if __name__ == "__main__":
    unittest.main()
