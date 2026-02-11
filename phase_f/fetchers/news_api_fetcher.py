"""
NewsAPI fetcher for external market news and sentiment data.

Fetches articles from multiple sources and extracts factual claims.
"""

import logging
import os
import requests
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta

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


class NewsAPIFetcher:
    """Fetch crypto and market news from NewsAPI."""

    def __init__(self):
        """Initialize with API key from config."""
        self.api_key = os.getenv("NEWSAPI_KEY", "").strip()
        self.base_url = os.getenv("NEWSAPI_BASE_URL", "https://newsapi.org/v2")
        self.enabled = bool(self.api_key)

        if not self.enabled:
            logger.warning("NewsAPIFetcher disabled: NEWSAPI_KEY not set")

    def fetch_crypto_news(
        self,
        lookback_hours: int = 24,
        limit: int = 25,
        keywords: Optional[List[str]] = None
    ) -> List[NewsArticle]:
        """
        Fetch recent crypto and market news.

        Args:
            lookback_hours: How many hours back to search (max 30 days)
            limit: Maximum articles to fetch (capped at 25 per API limits)
            keywords: Keywords to search for (default: BTC, ETH, volatility, regime)

        Returns:
            List of NewsArticle objects, empty if disabled or error
        """
        if not self.enabled:
            logger.warning("NewsAPIFetcher disabled")
            return []

        if keywords is None:
            keywords = ["Bitcoin", "Ethereum", "crypto volatility", "market regime"]

        articles = []

        try:
            # Calculate date range
            from_date = (datetime.utcnow() - timedelta(hours=min(lookback_hours, 720))).isoformat()

            # Search for each keyword
            for keyword in keywords[:5]:  # Limit to 5 keywords to avoid too many requests
                try:
                    articles.extend(
                        self._search_keyword(
                            keyword,
                            from_date=from_date,
                            limit=limit // 5  # Distribute limit across keywords
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error fetching news for '{keyword}': {e}")
                    continue

            # Limit total articles
            articles = articles[:limit]

            logger.info(f"Fetched {len(articles)} articles from NewsAPI")
            return articles

        except Exception as e:
            logger.error(f"NewsAPIFetcher error: {e}", exc_info=True)
            return []

    def _search_keyword(
        self,
        query: str,
        from_date: str,
        limit: int = 5
    ) -> List[NewsArticle]:
        """
        Search NewsAPI for articles matching keyword.

        Args:
            query: Search query/keyword
            from_date: ISO format start date
            limit: Max articles for this query

        Returns:
            List of NewsArticle objects
        """
        params = {
            "q": query,
            "from": from_date,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": limit,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key.startswith("Bearer") else None,
            "X-API-Key": self.api_key if not self.api_key.startswith("Bearer") else None,
        }
        headers = {k: v for k, v in headers.items() if v}  # Remove None values

        try:
            resp = requests.get(
                f"{self.base_url}/everything",
                params=params,
                headers=headers,
                timeout=10
            )
            resp.raise_for_status()

            data = resp.json()
            if not data.get("articles"):
                return []

            articles = []
            for item in data["articles"][:limit]:
                try:
                    article = NewsArticle(
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        source=item.get("source", {}).get("name", "Unknown"),
                        source_url=item.get("source", {}).get("url", ""),
                        published_at=item.get("publishedAt", ""),
                        content=item.get("content"),
                        url=item.get("url"),
                    )
                    articles.append(article)
                except Exception as e:
                    logger.debug(f"Error parsing article: {e}")
                    continue

            return articles

        except requests.RequestException as e:
            logger.error(f"NewsAPI request error: {e}")
            return []
        except ValueError as e:
            logger.error(f"NewsAPI JSON parse error: {e}")
            return []

    def get_available_sources(self) -> List[str]:
        """
        Get list of available news sources (cached).

        Returns:
            List of source names
        """
        # Default sources for crypto news
        return [
            "Cointelegraph",
            "CoinDesk",
            "The Block",
            "Crypto Briefing",
            "Bitcoin Magazine",
            "Decrypt",
            "Reuters",
            "Bloomberg",
        ]
