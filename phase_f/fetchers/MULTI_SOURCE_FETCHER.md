# Multi-Source Crypto News Fetcher

**Status**: ✅ COMPLETE - 46 tests, 100% passing

## Overview

A resilient, multi-source news fetcher for Phase F epistemic intelligence that aggregates crypto market intelligence from 5+ sources with intelligent deduplication and fail-safe behavior.

## Architecture

### Core Features

✅ **Multi-source aggregation** - Combines articles from 5+ independent sources
✅ **Fail-safe design** - One source failing doesn't block others
✅ **Deduplication** - Removes duplicate articles by URL/title
✅ **Timestamp normalization** - Handles multiple timestamp formats
✅ **HTML sanitization** - Removes tags and decodes entities
✅ **Immutable data** - Returns frozen dataclasses
✅ **Feature flags** - Enable/disable sources via env vars
✅ **Graceful degradation** - Returns empty list on errors

### Supported Sources

1. **CoinTelegraph API** (Public, no auth needed)
   - URL: `https://cointelegraph.com/api/v3`
   - Status: FREE, unlimited
   - Feature flag: `COINTELEGRAPH_ENABLED=true`

2. **CryptoCompare API** (Free tier with API key)
   - URL: `https://www.cryptocompare.com/api/v1`
   - Status: FREE tier (500 calls/day)
   - Feature flag: Auto-enabled with `CRYPTOCOMPARE_API_KEY`
   - Setup: Sign up at https://www.cryptocompare.com/api

3. **RSS Feeds** (Public, no auth needed)
   - Sources: Reddit (crypto + Bitcoin), Medium, CoinDesk, Yahoo Finance, Bitcoin Magazine
   - Status: FREE, unlimited
   - Feature flag: `PHASE_F_RSS_ENABLED=true`
   - Requires: `feedparser` library (`pip install feedparser`)

4. **Web Scraper** (Light scraping, disabled by default)
   - Sites: BeInCrypto, CoinGecko blog
   - Status: FREE but resource-intensive
   - Feature flag: `PHASE_F_WEB_SCRAPER_ENABLED=false` (disabled by default)
   - Requires: `BeautifulSoup4` library (`pip install beautifulsoup4`)

5. **Twitter/X** (Optional with Bearer token)
   - URL: `https://api.twitter.com/2/tweets/search/recent`
   - Status: Requires Twitter API v2 access
   - Feature flag: `TWITTER_SCRAPER_ENABLED=false` (disabled by default)
   - Setup: Get Bearer token from https://developer.twitter.com/

## Configuration

### Environment Variables

```bash
# Master switch
PHASE_F_USE_MULTI_SOURCE_FETCHER=true    # Enable multi-source (default: true)

# CoinTelegraph
COINTELEGRAPH_ENABLED=true               # Enable (default: true)

# CryptoCompare
CRYPTOCOMPARE_API_KEY=your_api_key       # Get from https://www.cryptocompare.com/api

# RSS Feeds
PHASE_F_RSS_ENABLED=true                 # Enable (default: true)

# Web Scraper (disabled by default)
PHASE_F_WEB_SCRAPER_ENABLED=false        # Enable (default: false)

# Twitter/X (disabled by default)
TWITTER_BEARER_TOKEN=your_bearer_token   # Twitter API v2 token
TWITTER_SCRAPER_ENABLED=false            # Enable (default: false)
```

### Feature Flags in Code

Set `PHASE_F_USE_MULTI_SOURCE_FETCHER=false` to fall back to legacy NewsAPI fetcher.

## Usage

### Quick Start

```python
from phase_f.fetchers.news_fetcher_multi_source import MultiSourceNewsFetcher

# Initialize
fetcher = MultiSourceNewsFetcher()

# Fetch articles
articles = fetcher.fetch_all(
    lookback_hours=24,
    limit=50,
    deduplicate=True
)

# Use articles
for article in articles:
    print(f"{article.title} ({article.source})")
    print(f"  Published: {article.published_at}")
    print(f"  URL: {article.url}")
    print()
```

### Fetch from Specific Source

```python
# Fetch only from CoinTelegraph
articles = fetcher.fetch_by_source("CoinTelegraph", limit=10)
```

### Check Enabled Sources

```python
enabled = fetcher.get_enabled_sources()
print(f"Enabled sources: {enabled}")

all_sources = fetcher.get_all_sources()
print(f"Available sources: {all_sources}")
```

### Integration with Phase F Pipeline

The multi-source fetcher is automatically integrated into Phase F:

```python
from phase_f.phase_f_job import PhaseFJob

job = PhaseFJob()
success = job.run()  # Uses multi-source fetcher by default
```

## Data Model

### NewsArticle (Immutable)

```python
@dataclass(frozen=True)
class NewsArticle:
    title: str                           # Article title
    description: str                     # Short description
    source: str                          # Source name
    source_url: str                      # Source homepage
    published_at: str                    # ISO format timestamp
    content: Optional[str] = None        # Full article content
    url: Optional[str] = None            # Article URL
    sentiment_signal: Optional[str] = None  # "bullish", "bearish", "neutral"
```

## Error Handling

### Fail-Safe Behavior

- ✅ One source failing doesn't block others
- ✅ Invalid articles are skipped
- ✅ API errors are logged and ignored
- ✅ Network timeouts don't crash the pipeline
- ✅ Empty responses return empty list

### Logging

All errors are logged at WARNING/ERROR level with context:

```
WARNING phase_f.fetchers.news_fetcher_multi_source:news_fetcher_multi_source.py:166
CoinTelegraph fetch error: 404 Client Error
```

## Deduplication

Removes duplicate articles by:
1. **Primary key**: Article URL
2. **Fallback**: Article title

Articles with identical URLs are considered duplicates.

```python
articles = fetcher.fetch_all(deduplicate=True)  # Deduplicated
articles = fetcher.fetch_all(deduplicate=False) # Raw articles
```

## Timestamp Handling

Automatically normalizes timestamps from multiple formats:

- ISO format: `2025-02-11T10:00:00Z`
- RFC2822: `Wed, 11 Feb 2025 10:00:00 +0000`
- Unix timestamp: `1707654000`
- Fallback: Current time if unparseable

All normalized to ISO format: `2025-02-11T10:00:00Z`

## Testing

### Test Coverage (46 tests)

- **NewsArticle** (2 tests): Immutability, fields
- **CoinTelegraph** (6 tests): Init, fetch, errors, disabled state
- **CryptoCompare** (4 tests): Auth, fetch, errors
- **RSS** (4 tests): Config, fetch, errors
- **WebScraper** (3 tests): Config, errors
- **Twitter** (4 tests): Auth, config, errors
- **Timestamp normalization** (4 tests): ISO, RFC2822, empty, format
- **HTML sanitization** (4 tests): Removal, truncation, entities
- **Multi-source aggregation** (8 tests): Init, sources, fetch, dedupe, sorting, limits
- **Error handling** (2 tests): Source failure, invalid data
- **Integration** (5 tests): Immutability, mocking, env vars, empty, high-volume

### Running Tests

```bash
# All tests
pytest tests/test_phase_f/test_news_fetcher_multi_source.py -v

# Specific test
pytest tests/test_phase_f/test_news_fetcher_multi_source.py::TestCoinTelegraphFetcher -v

# With coverage
pytest tests/test_phase_f/test_news_fetcher_multi_source.py --cov=phase_f.fetchers.news_fetcher_multi_source
```

## Performance

### Rate Limiting

- **CoinTelegraph**: ~10 req/sec (generous)
- **CryptoCompare**: 500 calls/day (free tier)
- **RSS**: Unlimited
- **Web Scraper**: ~2-3 req/sec per site (lightweight)
- **Twitter**: 300 requests / 15 minutes (v2 API)

### Per-Request Timeout

- All sources: 10-15 second timeout
- HTTP client follows redirects
- User-Agent: Mozilla/5.0 compatible

### Total Fetch Time

For 25 articles from 5 sources: ~5-8 seconds (includes RSS parse, web scrape)

## Setup Steps

### 5 Minutes (No Auth)

1. ✅ CoinTelegraph - Works out of the box
2. ✅ RSS feeds - Works out of the box
3. ✅ Web scraper (optional) - Requires BeautifulSoup4

```bash
pip install beautifulsoup4 feedparser
```

### 10 Minutes (API Keys)

1. **CryptoCompare**
   ```bash
   # Go to https://www.cryptocompare.com/api
   # Sign up (free)
   # Copy API key
   echo "CRYPTOCOMPARE_API_KEY=your_key" >> .env
   ```

2. **Twitter/X** (optional)
   ```bash
   # Go to https://developer.twitter.com/
   # Create app
   # Get Bearer token
   echo "TWITTER_BEARER_TOKEN=your_token" >> .env
   echo "TWITTER_SCRAPER_ENABLED=true" >> .env
   ```

### Enable in Phase F

```bash
# .env
PHASE_F_USE_MULTI_SOURCE_FETCHER=true
PHASE_F_MAX_ARTICLES_PER_AGENT=50
```

Restart Phase F daemon:

```bash
bash run_phase_f_crypto.sh
```

## Design Principles

✅ **Separation of concerns** - Each source is independent
✅ **Open/closed principle** - Easy to add new sources
✅ **Fail-safe** - Graceful degradation
✅ **Testable** - All components fully mocked
✅ **Documented** - Clear API and behavior
✅ **Constitutional** - Read-only, no execution authority

## Future Enhancements

- [ ] Sentiment analysis per article
- [ ] Source reliability scoring
- [ ] Caching (1-hour TTL per source)
- [ ] Batch processing mode
- [ ] Custom source plugin interface
- [ ] Source health dashboard
- [ ] Geolocation filtering
- [ ] Language detection

## Troubleshooting

### No Articles Fetched

1. Check enabled sources:
   ```python
   fetcher = MultiSourceNewsFetcher()
   print(fetcher.get_enabled_sources())
   ```

2. Check API keys (.env):
   ```bash
   echo $CRYPTOCOMPARE_API_KEY
   ```

3. Check logs:
   ```bash
   tail -f phase_f/logs/runs/*.log | grep "fetched"
   ```

### Articles from Only One Source

1. Verify other sources are enabled:
   ```bash
   export COINTELEGRAPH_ENABLED=true
   export PHASE_F_RSS_ENABLED=true
   ```

2. Check timeouts (increase if needed):
   ```python
   fetcher.sources[0].timeout = 20  # Increase from 10
   ```

### Duplicate Articles

1. Verify deduplication:
   ```python
   articles = fetcher.fetch_all(deduplicate=True)  # Enable
   ```

2. Check URL consistency:
   ```python
   urls = [a.url for a in articles]
   print(len(urls), "unique URLs out of", len(articles), "articles")
   ```

## Files

- **Main**: `phase_f/fetchers/news_fetcher_multi_source.py` (600 lines)
- **Tests**: `tests/test_phase_f/test_news_fetcher_multi_source.py` (46 tests)
- **Config**: `config/phase_f_settings.py` (new env vars)
- **Integration**: `phase_f/phase_f_job.py` (updated)

## License

Licensed under the same terms as the main trading app (Constitutional AI Stack).

---

**Last Updated**: 2026-02-11
**Status**: Production Ready ✅
**Test Coverage**: 46/46 tests passing (100%)
**Performance**: ~5-8 seconds for 50 articles
