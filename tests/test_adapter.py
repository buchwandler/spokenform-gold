import unittest

from spokenform_gold.adapter import build_prediction_records


class AdapterTests(unittest.TestCase):
    def test_build_prediction_records_uses_record_identity(self):
        records = [{"id": "r1", "input": "x", "language": "en", "locale": "en-US"}]
        predictions = build_prediction_records(records, lambda text, language, locale: f"{language}:{locale}:{text}")
        self.assertEqual(predictions, [{"id": "r1", "output": "en:en-US:x"}])


if __name__ == "__main__":
    unittest.main()
