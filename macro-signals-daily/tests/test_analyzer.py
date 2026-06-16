from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from macro_signals import analyzer  # noqa: E402


class FakePipeline:
    def __init__(self, label: str, score: float) -> None:
        self.label = label
        self.score = score
        self.calls: list[dict[str, object]] = []

    def __call__(self, text: str, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append({"text": text, **kwargs})
        return [{"label": self.label, "score": self.score}]


class SentimentScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_pipeline = analyzer.get_finbert_pipeline

    def tearDown(self) -> None:
        analyzer.get_finbert_pipeline = self.original_pipeline

    def install_fake_pipeline(self, label: str, score: float) -> FakePipeline:
        fake = FakePipeline(label, score)
        analyzer.get_finbert_pipeline = lambda: fake
        return fake

    def test_score_sentiment_converts_positive_confidence(self) -> None:
        fake = self.install_fake_pipeline("positive", 0.91)

        score, label, confidence = analyzer.score_sentiment("Bank earnings improved.")

        self.assertEqual(score, 2)
        self.assertEqual(label, "positive")
        self.assertEqual(confidence, 0.91)
        self.assertEqual(fake.calls[0]["truncation"], True)
        self.assertEqual(fake.calls[0]["max_length"], 512)

    def test_score_sentiment_converts_lower_confidence_negative(self) -> None:
        self.install_fake_pipeline("negative", 0.72)

        score, label, confidence = analyzer.score_sentiment("Credit losses widened.")

        self.assertEqual(score, -1)
        self.assertEqual(label, "negative")
        self.assertEqual(confidence, 0.72)

    def test_score_sentiment_converts_neutral_to_zero(self) -> None:
        self.install_fake_pipeline("neutral", 0.99)

        score, label, confidence = analyzer.score_sentiment("Markets were little changed.")

        self.assertEqual(score, 0)
        self.assertEqual(label, "neutral")
        self.assertEqual(confidence, 0.99)

    def test_score_sentiment_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(analyzer.FinBERTError, "Invalid input"):
            analyzer.score_sentiment("   ")

    def test_analyze_document_scores_only_detected_themes(self) -> None:
        self.install_fake_pipeline("positive", 0.88)
        document = {
            "id": "doc-1",
            "published_at": "2026-06-16T12:00:00+00:00",
            "source": "Example",
            "feed_url": "https://example.com/rss",
            "title": "Fed watches inflation as prices remain firm",
            "body": "Central bank officials discussed CPI and policy risks.",
        }

        signal = analyzer.analyze_document(document)

        self.assertEqual(signal.sentiment_label, "positive")
        self.assertEqual(signal.sentiment_confidence, 0.88)
        self.assertEqual(signal.scores["inflation"], 2)
        self.assertEqual(signal.scores["policy"], 2)
        self.assertEqual(signal.scores["growth"], 0)


if __name__ == "__main__":
    unittest.main()
