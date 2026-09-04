import tempfile
import unittest
from pathlib import Path

from spokenform_gold.campaign import campaign_next, campaign_status, create_campaign


class CampaignTests(unittest.TestCase):
    def test_campaign_creation_and_status_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = create_campaign("full", work_root=root, batch_size=1000)
            second = campaign_status("full", work_root=root)
            self.assertEqual(first["campaign_id"], "full")
            self.assertEqual(second["totals"]["batches"], 0)
            self.assertFalse(second["complete"])
            self.assertIsNone(campaign_next("full", "review-a", work_root=root))

    def test_unknown_role_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_campaign("full", work_root=tmp)
            with self.assertRaises(ValueError):
                campaign_next("full", "review-c", work_root=tmp)


if __name__ == "__main__":
    unittest.main()
