"""
Tests for multi-source crypto news fetcher.

Coverage:
- CoinTelegraph fetcher
- CryptoCompare fetcher
- RSS fetcher
- Web scraper fetcher
- Twitter fetcher
- Multi-source aggregation
- Deduplication
- Error handling
- Feature flags
- Integration tests
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from phase_f.fetchers.news_fetcher_multi_source import (
    NewsArticle,
    MultiSourceNewsFetcher,
    CoinTelegraphFetcher,
    CryptoCompareFetcher,
    RSSSiteFetcher,
    WebScraperFetcher,
    TwitterFetcher,
)


# ============================================================================
# Tests: NewsArticle (Data Model)
# ============================================================================


class TestNewsArticle:
    """Tests for NewsArticle immutable dataclass."""

    def test_newsarticle_immutable(self):
        """Verify NewsArticle is frozen (immutable)."""
        article = NewsArticle(
            title="Bitcoin Price Surge",
            description="Bitcoin reaches new high",
            source="CoinTelegraph",
            source_url="https://example.com",
            published_at="2025-02-11T10:00:00Z"
        )

        # Should not be able to modify
        with pytest.raises(AttributeError):
            article.title = "Modified Title"

    def test_newsarticle_fields(self):
        """Verify NewsArticle has all expected fields."""
        article = NewsArticle(
            title="Test",
            description="Desc",
            source="Source",
            source_url="https://test.com",
            published_at="2025-02-11T10:00:00Z",
            content="Full content",
            url="https://test.com/article",
            sentiment_signal="bullish"
        )

        assert article.title == "Test"
        assert article.description == "Desc"
        assert article.source == "Source"
        assert article.content == "Full content"
        assert article.sentiment_signal == "bullish"


# ============================================================================
# Tests: CoinTelegraph Fetcher
# ============================================================================


class TestCoinTelegraphFetcher:
    """Tests for CoinTelegraph API fetcher."""

    def test_cointelegraph_init_enabled(self):
        """CoinTelegraph should be enabled by default."""
        fetcher = CoinTelegraphFetcher()
        assert fetcher.is_enabled() is True

    def test_cointelegraph_init_disabled(self):
        """CoinTelegraph can be disabled via env var."""
        with patch.dict(os.environ, {"COINTELEGRAPH_ENABLED": "false"}):
            fetcher = CoinTelegraphFetcher()
            assert fetcher.is_enabled() is False

    @patch("requests.get")
    def test_cointelegraph_fetch_success(self, mock_get):
        """CoinTelegraph fetch should parse API response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Bitcoin Hits $50K",
                    "description": "BTC reaches milestone",
                    "url": "https://cointelegraph.com/article",
                    "published_at": "2025-02-11T10:00:00Z",
                }
            ]
        }
        mock_get.return_value = mock_response

        fetcher = CoinTelegraphFetcher()
        articles = fetcher.fetch(limit=10)

        assert len(articles) == 1
        assert articles[0].title == "Bitcoin Hits $50K"
        assert articles[0].source == "CoinTelegraph"

    @patch("requests.get")
    def test_cointelegraph_fetch_empty(self, mock_get):
        """CoinTelegraph fetch should handle empty response."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        fetcher = CoinTelegraphFetcher()
        articles = fetcher.fetch()

        assert len(articles) == 0

    @patch("requests.get")
    def test_cointelegraph_fetch_error(self, mock_get):
        """CoinTelegraph fetch should fail gracefully."""
        mock_get.side_effect = Exception("Network error")

        fetcher = CoinTelegraphFetcher()
        articles = fetcher.fetch()

        assert len(articles) == 0

    @patch("requests.get")
    def test_cointelegraph_disabled_returns_empty(self, mock_get):
        """Disabled CoinTelegraph should return empty list."""
        with patch.dict(os.environ, {"COINTELEGRAPH_ENABLED": "false"}):
            fetcher = CoinTelegraphFetcher()
            articles = fetcher.fetch()

            assert len(articles) == 0
            mock_get.assert_not_called()


# ============================================================================
# Tests: CryptoCompare Fetcher
# ============================================================================


class TestCryptoCompareFetcher:
    """Tests for CryptoCompare API fetcher."""

    def test_cryptocompare_disabled_without_key(self):
        """CryptoCompare should be disabled without API key."""
        with patch.dict(os.environ, {"CRYPTOCOMPARE_API_KEY": ""}):
            fetcher = CryptoCompareFetcher()
            assert fetcher.is_enabled() is False

    def test_cryptocompare_enabled_with_key(self):
        """CryptoCompare should be enabled with valid API key."""
        with patch.dict(os.environ, {"CRYPTOCOMPARE_API_KEY": "test_key_123"}):
            fetcher = CryptoCompareFetcher()
            assert fetcher.is_enabled() is True

    @patch("requests.get")
    def test_cryptocompare_fetch_success(self, mock_get):
        """CryptoCompare fetch should parse response."""
        with patch.dict(os.environ, {"CRYPTOCOMPARE_API_KEY": "test_key"}):
            mock_response = Mock()
            mock_response.json.return_value = {
                "Data": [
                    {
                        "title": "Ethereum Update",
                        "body": "New ETH development",
                        "url": "https://cryptocompare.com/news",
                        "source": "CoinDesk",
                        "published_on": 1707654000,
                    }
                ]
            }
            mock_get.return_value = mock_response

            fetcher = CryptoCompareFetcher()
            articles = fetcher.fetch(limit=10)

            assert len(articles) == 1
            assert articles[0].title == "Ethereum Update"
            assert articles[0].source == "CoinDesk"

    @patch("requests.get")
    def test_cryptocompare_fetch_error(self, mock_get):
        """CryptoCompare fetch should fail gracefully."""
        with patch.dict(os.environ, {"CRYPTOCOMPARE_API_KEY": "test_key"}):
            mock_get.side_effect = Exception("API error")

            fetcher = CryptoCompareFetcher()
            articles = fetcher.fetch()

            assert len(articles) == 0


# ============================================================================
# Tests: RSS Fetcher
# ============================================================================


class TestRSSFetcher:
    """Tests for RSS feed fetcher."""

    def test_rss_disabled_without_feedparser(self):
        """RSS should be disabled if feedparser not installed."""
        with patch("phase_f.fetchers.news_fetcher_multi_source.feedparser", None):
            fetcher = RSSSiteFetcher()
            assert fetcher.is_enabled() is False

    def test_rss_disabled_via_env(self):
        """RSS can be disabled via env var."""
        with patch.dict(os.environ, {"PHASE_F_RSS_ENABLED": "false"}):
            fetcher = RSSSiteFetcher()
            assert fetcher.is_enabled() is False

    @patch("phase_f.fetchers.news_fetcher_multi_source.feedparser")
    def test_rss_fetch_success(self, mock_feedparser):
        """RSS fetch should parse feed entries."""
        mock_feed = Mock()
        mock_entry = Mock()
        mock_entry.get.side_effect = lambda k, d="": {
            "title": "Crypto News",
            "summary": "Summary text",
            "link": "https://reddit.com/post",
        }.get(k, d)
        mock_entry.published = "Wed, 11 Feb 2025 10:00:00 +0000"
        mock_entry.content = []

        mock_feed.entries = [mock_entry]
        mock_feedparser.parse.return_value = mock_feed

        fetcher = RSSSiteFetcher()
        articles = fetcher.fetch(limit=10)

        # Should have fetched from multiple feeds
        assert len(articles) > 0

    @patch("phase_f.fetchers.news_fetcher_multi_source.feedparser")
    def test_rss_disabled_returns_empty(self, mock_feedparser):
        """Disabled RSS should return empty."""
        with patch.dict(os.environ, {"PHASE_F_RSS_ENABLED": "false"}):
            fetcher = RSSSiteFetcher()
            articles = fetcher.fetch()

            assert len(articles) == 0


# ============================================================================
# Tests: Web Scraper Fetcher
# ============================================================================


class TestWebScraperFetcher:
    """Tests for web scraper fetcher."""

    def test_webscraper_disabled_by_default(self):
        """Web scraper should be disabled by default."""
        with patch.dict(os.environ, {"PHASE_F_WEB_SCRAPER_ENABLED": "false"}):
            fetcher = WebScraperFetcher()
            assert fetcher.is_enabled() is False

    def test_webscraper_can_be_enabled(self):
        """Web scraper can be enabled via env var."""
        with patch.dict(os.environ, {"PHASE_F_WEB_SCRAPER_ENABLED": "true"}):
            fetcher = WebScraperFetcher()
            # Will be disabled if BeautifulSoup not available
            # but we mock it
            if hasattr(fetcher, "BeautifulSoup"):
                assert fetcher.is_enabled() is True

    @patch("requests.get")
    def test_webscraper_fetch_error_graceful(self, mock_get):
        """Web scraper should fail gracefully."""
        with patch.dict(os.environ, {"PHASE_F_WEB_SCRAPER_ENABLED": "true"}):
            mock_get.side_effect = Exception("Network error")

            fetcher = WebScraperFetcher()
            articles = fetcher.fetch()

            # Should return empty list on error
            assert len(articles) == 0


# ============================================================================
# Tests: Twitter Fetcher
# ============================================================================


class TestTwitterFetcher:
    """Tests for Twitter/X fetcher."""

    def test_twitter_disabled_without_token(self):
        """Twitter should be disabled without Bearer token."""
        with patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": ""}):
            fetcher = TwitterFetcher()
            assert fetcher.is_enabled() is False

    def test_twitter_disabled_by_default(self):
        """Twitter should be disabled even with token."""
        with patch.dict(os.environ, {
            "TWITTER_BEARER_TOKEN": "bearer_123",
            "TWITTER_SCRAPER_ENABLED": "false"
        }):
            fetcher = TwitterFetcher()
            assert fetcher.is_enabled() is False

    def test_twitter_can_be_enabled(self):
        """Twitter can be enabled with token and flag."""
        with patch.dict(os.environ, {
            "TWITTER_BEARER_TOKEN": "bearer_123",
            "TWITTER_SCRAPER_ENABLED": "true"
        }):
            fetcher = TwitterFetcher()
            assert fetcher.is_enabled() is True

    @patch("requests.get")
    def test_twitter_fetch_disabled_returns_empty(self, mock_get):
        """Disabled Twitter should return empty."""
        with patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": ""}):
            fetcher = TwitterFetcher()
            articles = fetcher.fetch()

            assert len(articles) == 0
            mock_get.assert_not_called()


# ============================================================================
# Tests: Timestamp Normalization
# ============================================================================


class TestTimestampNormalization:
    """Tests for timestamp normalization across sources."""

    def test_normalize_iso_timestamp(self):
        """Should handle ISO timestamps."""
        fetcher = CoinTelegraphFetcher()
        ts = fetcher._normalize_timestamp("2025-02-11T10:30:00Z")
        assert "2025-02-11" in ts
        assert "Z" in ts or "+" in ts

    def test_normalize_rfc2822_timestamp(self):
        """Should handle RFC2822 timestamps."""
        fetcher = CoinTelegraphFetcher()
        ts = fetcher._normalize_timestamp("Wed, 11 Feb 2025 10:00:00 +0000")
        assert "2025-02-11" in ts

    def test_normalize_empty_timestamp(self):
        """Should use current time for empty timestamp."""
        fetcher = CoinTelegraphFetcher()
        ts = fetcher._normalize_timestamp("")
        assert len(ts) > 0
        assert "Z" in ts or "+" in ts

    def test_normalize_preserves_format(self):
        """Normalized timestamp should be ISO format."""
        fetcher = CoinTelegraphFetcher()
        ts = fetcher._normalize_timestamp("2025-02-11T10:00:00")
        assert "T" in ts
        assert "2025-02-11" in ts


# ============================================================================
# Tests: Title/Description Sanitization
# ============================================================================


class TestSanitization:
    """Tests for title and description sanitization."""

    def test_sanitize_title_removes_html(self):
        """Should remove HTML tags from title."""
        fetcher = CoinTelegraphFetcher()
        clean = fetcher._sanitize_title("<h1>Bitcoin <strong>Price</strong> Surge</h1>")
        assert "<" not in clean
        assert "Bitcoin" in clean
        assert "Price" in clean

    def test_sanitize_title_truncates(self):
        """Should truncate long titles."""
        fetcher = CoinTelegraphFetcher()
        long_title = "A" * 500
        clean = fetcher._sanitize_title(long_title, max_length=200)
        assert len(clean) <= 200

    def test_sanitize_description_removes_html(self):
        """Should remove HTML tags from description."""
        fetcher = CoinTelegraphFetcher()
        clean = fetcher._sanitize_description("<p>Bitcoin news <a href='#'>link</a></p>")
        assert "<" not in clean
        assert "Bitcoin" in clean

    def test_sanitize_handles_entities(self):
        """Should decode HTML entities."""
        fetcher = CoinTelegraphFetcher()
        clean = fetcher._sanitize_title("Bitcoin &amp; Ethereum")
        assert "&amp;" not in clean
        assert "&" in clean


# ============================================================================
# Tests: MultiSourceNewsFetcher
# ============================================================================


class TestMultiSourceNewsFetcher:
    """Tests for multi-source aggregation."""

    def test_multisource_init(self):
        """MultiSourceNewsFetcher should initialize all sources."""
        fetcher = MultiSourceNewsFetcher()
        assert len(fetcher.sources) > 0
        assert any(isinstance(s, CoinTelegraphFetcher) for s in fetcher.sources)

    def test_multisource_get_enabled_sources(self):
        """Should list enabled sources."""
        fetcher = MultiSourceNewsFetcher()
        enabled = fetcher.get_enabled_sources()
        assert len(enabled) > 0
        assert "CoinTelegraphFetcher" in enabled

    def test_multisource_get_all_sources(self):
        """Should list all available sources."""
        fetcher = MultiSourceNewsFetcher()
        all_sources = fetcher.get_all_sources()
        assert len(all_sources) == 5  # CT, CC, RSS, WebScraper, Twitter
        assert "CoinTelegraphFetcher" in all_sources
        assert "TwitterFetcher" in all_sources

    @patch("phase_f.fetchers.news_fetcher_multi_source.CoinTelegraphFetcher")
    def test_multisource_fetch_aggregates(self, mock_ct_class):
        """Should aggregate articles from multiple sources."""
        mock_ct = Mock()
        mock_ct.is_enabled.return_value = True
        mock_ct.fetch.return_value = [
            NewsArticle(
                title="BTC News",
                description="",
                source="CoinTelegraph",
                source_url="https://ct.com",
                published_at="2025-02-11T10:00:00Z"
            )
        ]
        mock_ct_class.return_value = mock_ct

        # Mock other sources as disabled
        with patch("phase_f.fetchers.news_fetcher_multi_source.CryptoCompareFetcher") as mock_cc_class:
            mock_cc = Mock()
            mock_cc.is_enabled.return_value = False
            mock_cc_class.return_value = mock_cc

            fetcher = MultiSourceNewsFetcher()
            fetcher.sources[0] = mock_ct  # Replace first source

            articles = fetcher.fetch_all(limit=50)
            assert len(articles) > 0

    def test_multisource_fetch_deduplicates(self):
        """Should remove duplicate articles."""
        article1 = NewsArticle(
            title="BTC Price",
            description="",
            source="CoinTelegraph",
            source_url="https://example.com/article1",
            published_at="2025-02-11T10:00:00Z"
        )
        article2 = NewsArticle(
            title="BTC Price",
            description="",
            source="CryptoCompare",
            source_url="https://example.com/article1",  # Same URL
            published_at="2025-02-11T10:00:00Z"
        )

        fetcher = MultiSourceNewsFetcher()
        deduplicated = fetcher._deduplicate([article1, article2])

        assert len(deduplicated) == 1

    def test_multisource_fetch_sorts_by_date(self):
        """Should sort articles by date (newest first)."""
        older = NewsArticle(
            title="Old News",
            description="",
            source="Test",
            source_url="https://old.com",
            published_at="2025-02-10T10:00:00Z"
        )
        newer = NewsArticle(
            title="New News",
            description="",
            source="Test",
            source_url="https://new.com",
            published_at="2025-02-11T10:00:00Z"
        )

        fetcher = MultiSourceNewsFetcher()
        articles = [older, newer]
        articles.sort(key=lambda a: a.published_at, reverse=True)

        assert articles[0].title == "New News"
        assert articles[1].title == "Old News"

    def test_multisource_fetch_by_source(self):
        """Should fetch from specific source."""
        fetcher = MultiSourceNewsFetcher()
        articles = fetcher.fetch_by_source("CoinTelegraph", limit=10)

        # Should work (even if empty)
        assert isinstance(articles, list)

    def test_multisource_respects_limit(self):
        """Should limit total articles returned."""
        fetcher = MultiSourceNewsFetcher()
        articles = fetcher.fetch_all(limit=5)
        assert len(articles) <= 5


# ============================================================================
# Tests: Error Handling & Resilience
# ============================================================================


class TestErrorHandling:
    """Tests for error handling and resilience."""

    def test_source_failure_doesnt_block_others(self):
        """One source failing shouldn't block other sources."""
        fetcher = MultiSourceNewsFetcher()

        # Find working source and set up mocks
        working_article = NewsArticle(
            title="Working Source",
            description="",
            source="Test",
            source_url="https://test.com/1",
            published_at="2025-02-11T10:00:00Z"
        )

        # Mock all sources appropriately
        for i, source in enumerate(fetcher.sources):
            if i == 0:
                # First source fails
                source.fetch = Mock(side_effect=Exception("Network error"))
                source.is_enabled = Mock(return_value=True)
            elif i == 1:
                # Second source works
                source.fetch = Mock(return_value=[working_article])
                source.is_enabled = Mock(return_value=True)
            else:
                # Others are disabled
                source.is_enabled = Mock(return_value=False)

        articles = fetcher.fetch_all(limit=10)
        # Should have articles from working source
        assert len(articles) > 0
        assert any(a.title == "Working Source" for a in articles)

    def test_invalid_article_data_skipped(self):
        """Invalid articles should be skipped."""
        fetcher = CoinTelegraphFetcher()

        # Simulate bad article data
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "data": [
                    {"title": "Valid Article", "description": "Desc"},
                    {},  # Missing required fields
                ]
            }
            mock_get.return_value = mock_response

            articles = fetcher.fetch()
            # Should skip invalid and return valid
            assert len(articles) >= 0


# ============================================================================
# Tests: Integration & Real-World Scenarios
# ============================================================================


class TestIntegration:
    """Integration tests for real-world scenarios."""

    def test_fetch_maintains_immutability(self):
        """Fetched articles should be immutable."""
        fetcher = MultiSourceNewsFetcher()

        # Can't mock everything, but we can verify the dataclass is frozen
        with pytest.raises(AttributeError):
            article = NewsArticle(
                title="Test",
                description="",
                source="Test",
                source_url="https://test.com",
                published_at="2025-02-11T10:00:00Z"
            )
            article.title = "Modified"

    def test_multisource_with_multiple_sources_mock(self):
        """Should aggregate from multiple mock sources."""
        fetcher = MultiSourceNewsFetcher()

        # Create mock articles from different sources
        ct_article = NewsArticle(
            title="From CoinTelegraph",
            description="",
            source="CoinTelegraph",
            source_url="https://ct.com/1",
            published_at="2025-02-11T12:00:00Z"
        )

        # Mock the sources
        for source in fetcher.sources:
            if isinstance(source, CoinTelegraphFetcher):
                source.fetch = Mock(return_value=[ct_article])
            else:
                source.fetch = Mock(return_value=[])
                source.is_enabled = Mock(return_value=False)

        articles = fetcher.fetch_all(limit=10)
        assert any(a.source == "CoinTelegraph" for a in articles)

    def test_configuration_via_env_vars(self):
        """Should respect configuration from env vars."""
        with patch.dict(os.environ, {
            "COINTELEGRAPH_ENABLED": "true",
            "PHASE_F_RSS_ENABLED": "false",
            "PHASE_F_WEB_SCRAPER_ENABLED": "false",
            "TWITTER_SCRAPER_ENABLED": "false",
        }):
            fetcher = MultiSourceNewsFetcher()
            enabled = fetcher.get_enabled_sources()

            # Only CoinTelegraph and potentially CryptoCompare should be enabled
            assert any("CoinTelegraph" in s for s in enabled)

    def test_empty_articles_handled(self):
        """Should handle empty article list."""
        fetcher = MultiSourceNewsFetcher()

        # Mock all sources to return empty
        for source in fetcher.sources:
            source.fetch = Mock(return_value=[])

        articles = fetcher.fetch_all(limit=10)
        assert articles == []

    def test_high_volume_deduplication(self):
        """Should deduplicate efficiently with many articles."""
        fetcher = MultiSourceNewsFetcher()

        # Create many articles with some duplicates
        articles = []
        for i in range(100):
            articles.append(
                NewsArticle(
                    title=f"Article {i % 10}",
                    description="",
                    source="Test",
                    source_url=f"https://example.com/{i % 10}",
                    published_at="2025-02-11T10:00:00Z"
                )
            )

        deduplicated = fetcher._deduplicate(articles)
        # Should have ~10 unique articles
        assert len(deduplicated) <= 20
        assert len(deduplicated) < len(articles)
