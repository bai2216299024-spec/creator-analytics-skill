import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_report import _safe_zone_target


class ZoneSyncSafetyTests(unittest.TestCase):
    def test_safe_zone_target_allows_normal_zone_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = _safe_zone_target(root, "小红书专区", "数据报表")

            self.assertEqual(target, (root / "小红书专区" / "数据报表").resolve())

    def test_safe_zone_target_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = _safe_zone_target(root, "..", "outside")

            self.assertIsNone(target)


if __name__ == "__main__":
    unittest.main()
