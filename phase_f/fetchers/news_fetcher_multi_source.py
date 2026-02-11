"""
Multi-source crypto news fetcher for Phase F epistemic intelligence.

Simplified sources (3 core):
1. NewsAPI (50+ outlets - Bloomberg, Reuters, CoinDesk, etc.)
2. RSS Feeds (Reddit, Medium, CoinDesk, Bitcoin Magazine, etc.)
3. Web Scraper (BeInCrypto, CoinGecko blog - requires BeautifulSoup4)

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




class NewsAPIFetcher(NewsSourceFetcher):
    """Fetch news from NewsAPI (50+ outlets)."""

    def __init__(self):
        """Initialize with API key from config."""
        self.api_key = os.getenv("NEWSAPI_KEY", "").strip()
        self.base_url = os.getenv("NEWSAPI_BASE_URL", "https://newsapi.org/v2")
        self.enabled = bool(self.api_key)
        self.timeout = 10

        if not self.enabled:
            logger.warning("NewsAPIFetcher disabled: NEWSAPI_KEY not set")

    def is_enabled(self) -> bool:
        """Check if enabled."""
        return self.enabled

    def fetch(self, lookback_hours: int = 24, limit: int = 10) -> List[NewsArticle]:
        """Fetch from NewsAPI."""
        if not self.enabled:
            return []

        articles = []
        try:
            # Search for crypto/market keywords with different search strategies
            keywords = [
                "Bitcoin market",
                "Ethereum trading",
                "cryptocurrency news",
                "blockchain regulation",
                "crypto volatility"
            ]

            for keyword in keywords:
                try:
                    # NOTE: Removed 'from' parameter as it filters out free tier results
                    # Use sortBy relevancy instead of publishedAt for better results
                    params = {
                        "q": keyword,
                        "sortBy": "relevancy",
                        "language": "en",
                        "apiKey": self.api_key,
                    }

                    resp = requests.get(
                        f"{self.base_url}/everything",
                        params=params,
                        timeout=self.timeout
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    # Take top articles from this keyword search
                    for item in data.get("articles", [])[:limit // len(keywords) + 1]:
                        try:
                            article = NewsArticle(
                                title=self._sanitize_title(item.get("title", "")),
                                description=self._sanitize_description(item.get("description", "")),
                                source=item.get("source", {}).get("name", "NewsAPI"),
                                source_url=item.get("url", "https://newsapi.org"),
                                published_at=self._normalize_timestamp(item.get("publishedAt", "")),
                                content=item.get("content"),
                                url=item.get("url"),
                            )
                            articles.append(article)
                        except Exception as e:
                            logger.debug(f"Error parsing NewsAPI article: {e}")
                            continue
                except Exception as e:
                    logger.debug(f"NewsAPI keyword search failed for '{keyword}': {e}")
                    continue

            logger.info(f"NewsAPI: fetched {len(articles)} articles")
            return articles[:limit]

        except Exception as e:
            logger.warning(f"NewsAPI fetch error: {e}")
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
            "name": "Crypto.com Blog",
            "url": "https://blog.crypto.com/",
            "selectors": {
                # a.group elements contain blog posts with h2 titles
                "article": "a.group[href*='product-news'], a.group[href*='blog']",
                "title": "h2",
                "link": "a",  # The article container itself
                "time": "span, time, div",  # Time/date text within the link
            },
        },
        {
            "name": "CoinDesk News",
            "url": "https://www.coindesk.com/news/",
            "selectors": {
                "article": "div[data-article], article, div[class*='story-card']",
                "title": "h2, h3, h4, span[class*='title']",
                "link": "a[href*='/news/']",
                "time": "time, span[class*='date'], span[class*='time']",
            },
        },
        {
            "name": "Bitcoin Magazine",
            "url": "https://bitcoinmagazine.com/",
            "selectors": {
                "article": "article, div[class*='post'], div[class*='article-card']",
                "title": "h2, h3, h1, span[class*='title']",
                "link": "a[href*='article'], a[href*='news']",
                "time": "time, span[class*='date']",
            },
        },
    ]

    def __init__(self):
        """Initialize web scraper."""
        self.enabled = os.getenv("PHASE_F_WEB_SCRAPER_ENABLED", "true").lower() == "true"
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

                            # Handle case where article_elem itself might be an <a> tag
                            if article_elem.name == "a":
                                link_elem = article_elem
                            else:
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
            NewsAPIFetcher(),      # 50+ outlets (primary source)
            RSSSiteFetcher(),      # Reddit, Medium, CoinDesk, etc.
            WebScraperFetcher(),   # BeInCrypto, CoinGecko (requires BeautifulSoup4)
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
