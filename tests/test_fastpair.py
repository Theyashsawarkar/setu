"""Fast Pair battery: left / right / case from the buds' advertisement."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "fastpair", pathlib.Path(__file__).resolve().parent.parent / "setu" / "fastpair.py")
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

# OnePlus Nord Buds 3 Pro, heard for real: left 100, right 90, case unknown
REAL = bytes.fromhex("006047534486c8c8115e34645aff")


class Parse(unittest.TestCase):
    def test_real_buds(self):
        p = fp.parse(REAL)
        self.assertEqual(p["left"], {"level": 100, "charging": False})
        self.assertEqual(p["right"], {"level": 90, "charging": False})
        self.assertEqual(p["case"], {"level": None, "charging": False})

    def test_charging_and_shown_ui_type(self):
        # type 3 (show in the phone's UI): left 55 charging, right 54 charging, case 80
        p = fp.parse(bytes.fromhex("00" "6047534486c8c8" "115e" "33b7b650"))
        self.assertEqual(p["left"], {"level": 55, "charging": True})
        self.assertEqual(p["right"], {"level": 54, "charging": True})
        self.assertEqual(p["case"], {"level": 80, "charging": False})

    def test_discoverable_form_has_no_battery(self):
        self.assertIsNone(fp.parse(bytes.fromhex("2c4a9e")))   # a 3-byte model ID

    def test_other_fields_only(self):
        self.assertIsNone(fp.parse(bytes.fromhex("006047534486c8c8115e")))

    def test_short_and_malformed(self):
        for bad in (b"", b"\x00", bytes.fromhex("0060475344"), bytes.fromhex("006047534486c8c81134"),
                    bytes.fromhex("00346450")):
            self.assertIsNone(fp.parse(bad), bad.hex())

    def test_all_unknown_is_nothing(self):
        self.assertIsNone(fp.parse(bytes.fromhex("0034ffffff")))

    def test_level_over_100_is_unknown(self):
        p = fp.parse(bytes.fromhex("0034655a50"))           # 101 isn't a level
        self.assertIsNone(p["left"]["level"])
        self.assertEqual(p["right"]["level"], 90)

    def test_compact(self):
        self.assertEqual(fp.compact(fp.parse(REAL)), "L 100 · R 90")
        self.assertEqual(fp.compact(fp.parse(bytes.fromhex("0033b7b650"))), "L 55⚡ · R 54⚡ · case 80")


class Fake(unittest.TestCase):
    def test_fake_file(self):
        import json
        import os
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"Buds": REAL.hex()}, f)
        os.environ["SETU_FASTPAIR_FAKE"] = f.name
        try:
            s = fp.Scanner()
            s.start()                       # no scan with a fake
            self.assertFalse(s.on)
            r = s.read(now=1000.0)
            self.assertEqual(r["Buds"]["parts"]["right"]["level"], 90)
        finally:
            del os.environ["SETU_FASTPAIR_FAKE"]
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
