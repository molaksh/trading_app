"""
Tests for claim extraction.
"""

import pytest
from phase_f.fetchers import NewsArticle
from phase_f.extractors import ClaimExtractor
from phase_f.schemas import SentimentEnum


class TestClaimExtractor:
    """Test claim extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return ClaimExtractor()

    def test_extract_from_article(self, extractor):
        """Extract claims from article."""
        article = NewsArticle(
            title="Bitcoin Reaches New ATH",
            description="Bitcoin has reached a new all-time high of $50,000",
            source="CoinTelegraph",
            source_url="https://cointelegraph.com/article",
            published_at="2026-02-11T10:30:00Z",
            content="Bitcoin has surged past previous records. The rally reflects strong investor confidence.",
        )

        claims = extractor.extract_from_article(article)
        assert len(claims) > 0
        # All claims should have proper attributes
        for claim in claims:
            assert claim.claim_text
            assert claim.source == "CoinTelegraph"
            assert 0.0 <= claim.confidence_in_claim <= 1.0

    def test_no_causation_words(self, extractor):
        """Extracted claims should not have causation words."""
        article = NewsArticle(
            title="News",
            description="Test",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
            content="Bitcoin ATH causes bullish sentiment. This leads to increased trading.",
        )

        claims = extractor.extract_from_article(article)
        # Claims with "causes" and "leads to" should be filtered
        for claim in claims:
            assert "causes" not in claim.claim_text.lower()
            assert "leads to" not in claim.claim_text.lower()

    def test_sentiment_classification(self, extractor):
        """Test sentiment classification."""
        # Positive article
        positive_article = NewsArticle(
            title="Bitcoin Bullish Rally",
            description="Strong gains as confidence surges",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
        )
        pos_claims = extractor.extract_from_article(positive_article)
        if pos_claims:
            assert any(c.sentiment == SentimentEnum.POSITIVE for c in pos_claims)

        # Negative article
        negative_article = NewsArticle(
            title="Bitcoin Bearish Crash",
            description="Sharp decline as fear spreads",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
        )
        neg_claims = extractor.extract_from_article(negative_article)
        if neg_claims:
            # At least some should be negative
            sentiments = [c.sentiment for c in neg_claims]
            assert SentimentEnum.NEGATIVE in sentiments or SentimentEnum.NEUTRAL in sentiments

    def test_empty_article(self, extractor):
        """Handle empty articles."""
        article = NewsArticle(
            title="",
            description="",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
        )
        claims = extractor.extract_from_article(article)
        assert len(claims) == 0

    def test_confidence_scoring(self, extractor):
        """Test confidence scoring."""
        article = NewsArticle(
            title="Fed Raises Interest Rates by 0.25%",
            description="The Federal Reserve increased rates significantly",
            source="Reuters",
            source_url="https://reuters.com",
            published_at="2026-02-11T10:30:00Z",
        )
        claims = extractor.extract_from_article(article)

        # Article with institution name + numbers should have high confidence
        if claims:
            confidences = [c.confidence_in_claim for c in claims]
            assert any(conf > 0.6 for conf in confidences)

    def test_speculation_reduces_confidence(self, extractor):
        """Speculative language reduces confidence."""
        article = NewsArticle(
            title="Bitcoin Could Possibly Crash",
            description="May fall if conditions change",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
        )
        claims = extractor.extract_from_article(article)

        # Speculative language should reduce confidence
        if claims:
            assert all(c.confidence_in_claim < 0.8 for c in claims)

    def test_max_claims_limit(self, extractor):
        """Respect max claims per article."""
        article = NewsArticle(
            title="Long Article",
            description="Many claims here",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
            content="Bitcoin rallied. Ethereum gained. Solana surged. Prices increased. Markets bullish. Sentiment positive.",
        )
        claims = extractor.extract_from_article(article, max_claims=2)
        assert len(claims) <= 2

    def test_all_claims_have_reasoning(self, extractor):
        """All extracted claims should be valid."""
        article = NewsArticle(
            title="Bitcoin ATH",
            description="Bitcoin reaches new high",
            source="Test",
            source_url="https://test.com",
            published_at="2026-02-11T10:30:00Z",
        )
        claims = extractor.extract_from_article(article)

        for claim in claims:
            # All required fields should be present
            assert claim.claim_text
            assert claim.source
            assert 0.0 <= claim.confidence_in_claim <= 1.0
            assert claim.is_factual is True
            assert claim.sentiment in [
                SentimentEnum.POSITIVE,
                SentimentEnum.NEUTRAL,
                SentimentEnum.NEGATIVE
            ]
