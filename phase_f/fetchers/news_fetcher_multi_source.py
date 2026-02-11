"""
Multi-source crypto news fetcher for Phase F epistemic intelligence.

Sources:
1. CoinTelegraph API (public, no auth needed)
2. CryptoCompare API (free tier with API key)
3. RSS Feeds (Reddit, Medium, CoinDesk, Yahoo Finance, etc.)
4. Web Scraper (light - BeInCrypto, CoinGecko blog)
5. Twitter/X (optional - requires Bearer token)

All sources return normalized NewsArticle dataclasses for downstream claim extraction.
Fail-safe: Errors in one source don't block others.
"""

import logging
import os
import re
import requests
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Set
from datetime import datetime, timedelta
from urllib.parse import quote, urljoin
from abc import ABC, abstractmethod

try:
    import feedparser
except ImportError:
    feedparser = None

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsArticle:
    """Immutable representation of a news article."""

    title: str
    description: str
    source: str
    source_url: str
    published_at: str
    content: Optional[str] = None
    url: Optional[str] = None
    sentiment_signal: Optional[str] = None  # "bullish", "bearish", "neutral"


class NewsSourceFetcher(ABC):
    """Abstract base for all news sources."""

    @abstractmethod
    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch articles from this source."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this source is configured and enabled."""
        pass

    def _normalize_timestamp(self, ts: str) -> str:
        """Convert various timestamp formats to ISO format."""
        if not ts:
            return datetime.utcnow().isoformat() + "Z"

        # Already ISO format
        if "T" in ts and ("Z" in ts or "+" in ts or "-" in ts.split("T")[1]):
            return ts if ts.endswith("Z") else ts.replace("+00:00", "Z")

        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %z",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(ts.replace(" +0000", " +0000"), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=None)
                return dt.isoformat() + "Z"
            except ValueError:
                continue

        # Fallback to current time
        logger.debug(f"Could not parse timestamp: {ts}")
        return datetime.utcnow().isoformat() + "Z"

    def _sanitize_title(self, title: str, max_length: int = 200) -> str:
        """Remove HTML tags and clean up title."""
        # Remove HTML tags
        clean = re.sub(r"<[^>]+>", "", title)
        # Decode HTML entities
        import html
        clean = html.unescape(clean)
        # Truncate
        return clean[:max_length]

    def _sanitize_description(self, desc: str, max_length: int = 500) -> str:
        """Remove HTML tags and clean up description."""
        if not desc:
            return ""
        clean = re.sub(r"<[^>]+>", "", desc)
        import html
        clean = html.unescape(clean)
        return clean[:max_length]


class CoinTelegraphFetcher(NewsSourceFetcher):
    """Fetch from CoinTelegraph API (public, no auth required)."""

    def __init__(self):
        """Initialize CoinTelegraph fetcher."""
        self.enabled = os.getenv("COINTELEGRAPH_ENABLED", "true").lower() == "true"
        self.base_url = os.getenv("COINTELEGRAPH_BASE_URL", "https://cointelegraph.com/api/v3")
        self.timeout = 10

    def is_enabled(self) -> bool:
        """Check if enabled."""
        return self.enabled

    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch from CoinTelegraph."""
        if not self.enabled:
            return []

        articles = []
        try:
            # CoinTelegraph API v3 - get latest articles
            params = {
                "limit": min(limit, 50),
            }

            resp = requests.get(
                f"{self.base_url}/news",
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", [])[:limit]:
                try:
                    article = NewsArticle(
                        title=self._sanitize_title(item.get("title", "")),
                        description=self._sanitize_description(
                            item.get("description", "") or item.get("summary", "")
                        ),
                        source="CoinTelegraph",
                        source_url=item.get("url", "https://cointelegraph.com"),
                        published_at=self._normalize_timestamp(item.get("published_at", "")),
                        content=item.get("content"),
                        url=item.get("url"),
                    )
                    articles.append(article)
                except Exception as e:
                    logger.debug(f"Error parsing CoinTelegraph article: {e}")
                    continue

            logger.info(f"CoinTelegraph: fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"CoinTelegraph fetch error: {e}")
            return []


class CryptoCompareFetcher(NewsSourceFetcher):
    """Fetch from CryptoCompare API (free tier, requires API key)."""

    def __init__(self):
        """Initialize CryptoCompare fetcher."""
        self.api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "").strip()
        self.enabled = bool(self.api_key)
        self.base_url = os.getenv("CRYPTOCOMPARE_BASE_URL", "https://www.cryptocompare.com/api/v1")
        self.timeout = 10

        if not self.enabled:
            logger.debug("CryptoCompareFetcher disabled: CRYPTOCOMPARE_API_KEY not set")

    def is_enabled(self) -> bool:
        """Check if enabled."""
        return self.enabled

    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch from CryptoCompare."""
        if not self.enabled:
            return []

        articles = []
        try:
            # CryptoCompare news endpoint
            params = {
                "limit": min(limit, 100),
                "feeds": "cointelegraph,coindesk,cryptocompare",  # Multiple feeds
                "lang": "EN",
            }

            headers = {
                "authorization": f"Apikey {self.api_key}",
                "User-Agent": "Mozilla/5.0",
            }

            resp = requests.get(
                f"{self.base_url}/news/list",
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("Data", [])[:limit]:
                try:
                    article = NewsArticle(
                        title=self._sanitize_title(item.get("title", "")),
                        description=self._sanitize_description(item.get("body", "")),
                        source=item.get("source", "CryptoCompare"),
                        source_url=item.get("url", "https://www.cryptocompare.com"),
                        published_at=self._normalize_timestamp(
                            str(item.get("published_on", ""))
                        ),
                        content=item.get("body"),
                        url=item.get("url"),
                    )
                    articles.append(article)
                except Exception as e:
                    logger.debug(f"Error parsing CryptoCompare article: {e}")
                    continue

            logger.info(f"CryptoCompare: fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"CryptoCompare fetch error: {e}")
            return []


class RSSSiteFetcher(NewsSourceFetcher):
    """Fetch from RSS feeds."""

    # RSS feed URLs
    FEEDS = {
        "reddit_crypto": "https://www.reddit.com/r/cryptocurrency/new/.rss",
        "reddit_bitcoin": "https://www.reddit.com/r/Bitcoin/new/.rss",
        "medium_crypto": "https://medium.com/feed/tag/cryptocurrency",
        "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "yahoo_finance": "https://feeds.finance.yahoo.com/rss/",
        "bitcoinmagazine": "https://bitcoinmagazine.com/feed",
    }

    def __init__(self):
        """Initialize RSS fetcher."""
        self.enabled = (
            os.getenv("PHASE_F_RSS_ENABLED", "true").lower() == "true"
            and feedparser is not None
        )
        self.timeout = 10

        if not feedparser:
            logger.warning("feedparser not installed, RSS fetcher disabled")
            self.enabled = False

    def is_enabled(self) -> bool:
        """Check if enabled."""
        return self.enabled

    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch from RSS feeds."""
        if not self.enabled:
            return []

        articles = []
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)

        try:
            for feed_name, feed_url in self.FEEDS.items():
                try:
                    feed = feedparser.parse(feed_url)

                    for entry in feed.entries[:limit // len(self.FEEDS) + 1]:
                        try:
                            # Parse publish date
                            pub_date = ""
                            if hasattr(entry, "published"):
                                pub_date = entry.published
                            elif hasattr(entry, "updated"):
                                pub_date = entry.updated

                            article = NewsArticle(
                                title=self._sanitize_title(entry.get("title", "")),
                                description=self._sanitize_description(
                                    entry.get("summary", "") or entry.get("description", "")
                                ),
                                source=feed_name.replace("_", " ").title(),
                                source_url=entry.get("link", feed_url),
                                published_at=self._normalize_timestamp(pub_date),
                                content=entry.get("content", [{}])[0].get("value"),
                                url=entry.get("link"),
                            )
                            articles.append(article)

                        except Exception as e:
                            logger.debug(f"Error parsing RSS entry from {feed_name}: {e}")
                            continue

                except Exception as e:
                    logger.debug(f"Error fetching RSS feed {feed_name}: {e}")
                    continue

            logger.info(f"RSS: fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"RSS fetch error: {e}")
            return []


class WebScraperFetcher(NewsSourceFetcher):
    """Light web scraper for news sites."""

    SITES = [
        {
            "name": "BeInCrypto",
            "url": "https://beincrypto.com/latest/",
            "selectors": {
                "article": "article.post",
                "title": "h2 a, h3 a",
                "link": "a",
                "time": "time",
            },
        },
        {
            "name": "CoinGecko Blog",
            "url": "https://www.coingecko.com/blog",
            "selectors": {
                "article": "div.blog-card",
                "title": "h2, h3",
                "link": "a",
                "time": "span.date",
            },
        },
    ]

    def __init__(self):
        """Initialize web scraper."""
        self.enabled = os.getenv("PHASE_F_WEB_SCRAPER_ENABLED", "false").lower() == "true"
        self.timeout = 15

        try:
            from bs4 import BeautifulSoup
            self.BeautifulSoup = BeautifulSoup
        except ImportError:
            logger.debug("BeautifulSoup not installed, web scraper disabled")
            self.enabled = False

    def is_enabled(self) -> bool:
        """Check if enabled."""
        return self.enabled

    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch from web sources."""
        if not self.enabled or not hasattr(self, "BeautifulSoup"):
            return []

        articles = []

        try:
            for site in self.SITES:
                try:
                    resp = requests.get(
                        site["url"],
                        timeout=self.timeout,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
                    )
                    resp.raise_for_status()

                    soup = self.BeautifulSoup(resp.content, "html.parser")
                    selectors = site["selectors"]

                    for article_elem in soup.select(selectors["article"])[:limit // 2]:
                        try:
                            title_elem = article_elem.select_one(selectors["title"])
                            link_elem = article_elem.select_one(selectors["link"])
                            time_elem = article_elem.select_one(selectors["time"])

                            if not title_elem or not link_elem:
                                continue

                            article = NewsArticle(
                                title=self._sanitize_title(title_elem.get_text()),
                                description="",  # Not always available in scraped content
                                source=site["name"],
                                source_url=urljoin(
                                    site["url"], link_elem.get("href", site["url"])
                                ),
                                published_at=self._normalize_timestamp(
                                    time_elem.get_text() if time_elem else ""
                                ),
                                url=urljoin(site["url"], link_elem.get("href", "")),
                            )
                            articles.append(article)

                        except Exception as e:
                            logger.debug(f"Error scraping article from {site['name']}: {e}")
                            continue

                except Exception as e:
                    logger.debug(f"Error scraping {site['name']}: {e}")
                    continue

            logger.info(f"WebScraper: fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"WebScraper fetch error: {e}")
            return []


class TwitterFetcher(NewsSourceFetcher):
    """Fetch from Twitter/X (requires Bearer token, optional)."""

    def __init__(self):
        """Initialize Twitter fetcher."""
        self.bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
        self.enabled = bool(
            self.bearer_token
            and os.getenv("TWITTER_SCRAPER_ENABLED", "false").lower() == "true"
        )
        self.timeout = 10

        if not self.enabled:
            logger.debug("TwitterFetcher disabled: TWITTER_BEARER_TOKEN not set or disabled")

    def is_enabled(self) -> bool:
        """Check if enabled."""
        return self.enabled

    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch recent tweets about crypto."""
        if not self.enabled:
            return []

        articles = []

        try:
            headers = {
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": "Mozilla/5.0",
            }

            # Search for tweets (requires v2 API)
            query = "crypto OR bitcoin OR ethereum lang:en"
            params = {
                "query": query,
                "max_results": min(limit, 100),
                "tweet.fields": "created_at,author_id,public_metrics",
            }

            resp = requests.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()

            for tweet in data.get("data", [])[:limit]:
                try:
                    article = NewsArticle(
                        title=tweet.get("text", "")[:200],
                        description=tweet.get("text", ""),
                        source="Twitter",
                        source_url=f"https://twitter.com/i/web/status/{tweet.get('id', '')}",
                        published_at=self._normalize_timestamp(tweet.get("created_at", "")),
                        url=f"https://twitter.com/i/web/status/{tweet.get('id', '')}",
                    )
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"Error parsing tweet: {e}")
                    continue

            logger.info(f"Twitter: fetched {len(articles)} tweets")
            return articles

        except Exception as e:
            logger.warning(f"Twitter fetch error: {e}")
            return []


class MultiSourceNewsFetcher:
    """
    Unified multi-source news fetcher.

    Aggregates articles from all available sources:
    - CoinTelegraph (public API)
    - CryptoCompare (free tier with API key)
    - RSS feeds (Reddit, Medium, CoinDesk, etc.)
    - Web scraping (BeInCrypto, CoinGecko)
    - Twitter/X (optional with Bearer token)

    Design:
    - Fail-safe: One source failing doesn't block others
    - Deduplication: Remove duplicate articles by URL/title
    - Rate-limited: Respects API limits and timeouts
    - Immutable: Returns frozen dataclasses
    """

    def __init__(self):
        """Initialize multi-source fetcher with all available sources."""
        self.sources: List[NewsSourceFetcher] = [
            CoinTelegraphFetcher(),
            CryptoCompareFetcher(),
            RSSSiteFetcher(),
            WebScraperFetcher(),
            TwitterFetcher(),
        ]

        enabled_count = sum(1 for s in self.sources if s.is_enabled())
        logger.info(f"MultiSourceNewsFetcher initialized: {enabled_count}/{len(self.sources)} sources enabled")

    def fetch_all(
        self,
        lookback_hours: int = 24,
        limit: int = 50,
        deduplicate: bool = True
    ) -> List[NewsArticle]:
        """
        Fetch articles from all sources.

        Args:
            lookback_hours: How far back to search
            limit: Total articles to return
            deduplicate: Remove duplicates by URL/title

        Returns:
            List of deduplicated NewsArticle objects
        """
        all_articles: List[NewsArticle] = []
        per_source_limit = max(limit // len(self.sources), 5)

        for source in self.sources:
            if not source.is_enabled():
                continue

            try:
                articles = source.fetch(
                    lookback_hours=lookback_hours,
                    limit=per_source_limit
                )
                all_articles.extend(articles)

            except Exception as e:
                logger.warning(f"Error fetching from {source.__class__.__name__}: {e}")
                continue

        # Deduplicate
        if deduplicate:
            all_articles = self._deduplicate(all_articles)

        # Sort by publish date (newest first)
        all_articles.sort(
            key=lambda a: a.published_at,
            reverse=True
        )

        # Limit total
        all_articles = all_articles[:limit]

        logger.info(f"MultiSourceNewsFetcher: fetched {len(all_articles)} total articles")
        return all_articles

    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Remove duplicate articles by URL and title."""
        seen: Set[str] = set()
        unique: List[NewsArticle] = []

        for article in articles:
            # Use URL as primary key
            key = article.url or article.title
            if key not in seen:
                seen.add(key)
                unique.append(article)

        logger.debug(f"Deduplication: {len(articles)} → {len(unique)} articles")
        return unique

    def fetch_by_source(
        self,
        source_name: str,
        lookback_hours: int = 24,
        limit: int = 10
    ) -> List[NewsArticle]:
        """
        Fetch from a specific source.

        Args:
            source_name: Class name or source identifier
            lookback_hours: How far back to search
            limit: Articles to return

        Returns:
            List of NewsArticle objects
        """
        for source in self.sources:
            if source_name.lower() in source.__class__.__name__.lower():
                return source.fetch(lookback_hours=lookback_hours, limit=limit)

        logger.warning(f"Source not found: {source_name}")
        return []

    def get_enabled_sources(self) -> List[str]:
        """Get list of enabled sources."""
        return [s.__class__.__name__ for s in self.sources if s.is_enabled()]

    def get_all_sources(self) -> List[str]:
        """Get list of all available sources."""
        return [s.__class__.__name__ for s in self.sources]
