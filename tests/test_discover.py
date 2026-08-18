import unittest

from spokenform_gold.discover import discover, shape


class DiscoverTests(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(shape("192.168.0.1"), "ipv4")
        self.assertEqual(shape("v2.0.0-beta.4"), "version_like")
        self.assertEqual(shape(".02"), "decimal_like")
        self.assertEqual(shape("3/4"), "slash_numeric")

    def test_unseen_is_candidate(self):
        self.assertTrue(discover("Use XJ-900/2B.", [], rare_below=3))


if __name__ == "__main__":
    unittest.main()
