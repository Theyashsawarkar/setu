"""bluez.connect: tries again on the failures a retry fixes, not on the rest."""
import unittest

from setu import bluez


def runner(*results):
    calls = []
    it = iter(results)

    def run():
        calls.append(1)
        return next(it)
    return run, calls


class Connect(unittest.TestCase):
    def go(self, *results, connected=False):
        run, calls = runner(*results)
        ok, _ = bluez.connect("AA:BB:CC:00:00:01", run=run, connected=lambda: connected, sleep=lambda _s: None)
        return ok, len(calls)

    def test_first_time(self):
        self.assertEqual(self.go((0, "Connection successful", "")), (True, 1))

    def test_busy_then_works(self):
        fail = (1, "Failed to connect: org.bluez.Error.Failed br-connection-unknown", "")
        self.assertEqual(self.go(fail, (0, "Connection successful", "")), (True, 2))

    def test_gives_up_after_three(self):
        fail = (1, "Failed to connect: org.bluez.Error.InProgress", "")
        self.assertEqual(self.go(fail, fail, fail), (False, 3))

    def test_device_away_tries_twice(self):
        away = (1, "Failed to connect: org.bluez.Error.Failed br-connection-page-timeout", "")
        self.assertEqual(self.go(away, away, away), (False, 2))

    def test_error_but_connected_counts(self):
        fail = (1, "Failed to connect: org.bluez.Error.Failed br-connection-profile-unavailable", "")
        self.assertEqual(self.go(fail, connected=True), (True, 1))

    def test_rejected_not_retried(self):
        self.assertEqual(self.go((1, "Failed to connect: org.bluez.Error.AuthenticationRejected", "")), (False, 1))


if __name__ == "__main__":
    unittest.main()
