# Multi-Source News Fetcher - Quick Start Guide

**Status**: Ready to use immediately with RSS & Web Scraper! 🚀

---

## ⚡ 5-Minute Setup

### Step 1: Install Dependencies
```bash
pip install feedparser beautifulsoup4
```

### Step 2: Run Phase F
```bash
# Option A: Run once
python phase_f_main.py --run-once

# Option B: Start daemon
bash run_phase_f_crypto.sh
```

**Done!** You're now fetching news from:
- ✅ **RSS Feeds** (Reddit, Medium, CoinDesk, Bitcoin Magazine, Yahoo Finance)
- ✅ **Web Scraper** (BeInCrypto, CoinGecko)

---

## 📊 What You Get

The multi-source fetcher will now provide Phase F with crypto news from 2 reliable public sources:

| Source | Type | Rate | Cost | Setup |
|--------|------|------|------|-------|
| RSS Feeds | Public | Unlimited | FREE | ✅ Done |
| Web Scraper | Public | ~2-3/sec | FREE | ✅ Done |

---

## ✨ What Phase F Does With Articles

1. **Fetch** articles from RSS feeds & web scrapers
2. **Extract claims** from articles
3. **Build hypotheses** about market regime
4. **Challenge hypotheses** (adversarial analysis)
5. **Produce verdict** about regime validity
6. **Apply confidence penalties** to governance decisions

---

## 🔗 Add APIs Later (When Ready)

### Add CoinTelegraph API (5 minutes)
```bash
# 1. Go to https://cointelegraph.com/api/v3
# 2. Apply for access
# 3. Once approved:
echo "COINTELEGRAPH_ENABLED=true" >> .env
```

### Add CryptoCompare API (5 minutes)
```bash
# 1. Go to https://www.cryptocompare.com/api
# 2. Sign up (free)
# 3. Copy your API key
echo "CRYPTOCOMPARE_API_KEY=your_api_key" >> .env
# (Auto-enabled when key is set)
```

### Add Twitter/X (Optional, 10 minutes)
```bash
# 1. Go to https://developer.twitter.com/
# 2. Create app & get Bearer token
echo "TWITTER_BEARER_TOKEN=your_token" >> .env
echo "TWITTER_SCRAPER_ENABLED=true" >> .env
```

---

## 🧪 Verify It's Working

### Check Enabled Sources
```bash
python -c "
from phase_f.fetchers.news_fetcher_multi_source import MultiSourceNewsFetcher
fetcher = MultiSourceNewsFetcher()
print('Enabled sources:', fetcher.get_enabled_sources())
"
```

### Run Phase F Once
```bash
python phase_f_main.py --run-once
```

Look for output like:
```
Stage 1 complete: XX articles, YY claims, ZZ hypotheses
```

### Check Verdict
```bash
# View the latest verdict
ls -ltr persist/phase_f/crypto/verdicts.jsonl | tail -1
tail -1 persist/phase_f/crypto/verdicts.jsonl | python -m json.tool
```

---

## 📚 Learn More

Full documentation: `phase_f/fetchers/MULTI_SOURCE_FETCHER.md`

Key topics:
- Performance metrics (typical runtime)
- Configuration options
- Troubleshooting guide
- Design principles

---

## 🔄 How to Add More Sources Later

When you have API keys, just update `.env`:

```bash
# CoinTelegraph
COINTELEGRAPH_ENABLED=true

# CryptoCompare
CRYPTOCOMPARE_API_KEY=your_api_key

# Twitter (optional)
TWITTER_BEARER_TOKEN=your_token
TWITTER_SCRAPER_ENABLED=true
```

**No code changes needed!** Phase F will automatically detect and use the new sources.

---

## ✅ Current Setup Summary

| Source | Status | Enabled | Action |
|--------|--------|---------|--------|
| RSS Feeds | Ready ✅ | Yes | *(Already working)* |
| Web Scraper | Ready ✅ | Yes | *(Already working)* |
| CoinTelegraph | Not Ready | No | Apply for API access |
| CryptoCompare | Not Ready | No | Sign up & get API key |
| Twitter | Not Ready | No | Create developer app |

---

## 🆘 Troubleshooting

### "feedparser not installed"
```bash
pip install feedparser
```

### "BeautifulSoup not installed"
```bash
pip install beautifulsoup4
```

### No articles fetched
```bash
# Check which sources are enabled
python -c "
from phase_f.fetchers.news_fetcher_multi_source import MultiSourceNewsFetcher
fetcher = MultiSourceNewsFetcher()
for source in fetcher.sources:
    print(f'{source.__class__.__name__}: {source.is_enabled()}')
"
```

### Want to disable a source
```bash
# Disable web scraper (for example)
echo "PHASE_F_WEB_SCRAPER_ENABLED=false" >> .env
```

---

## 📈 What's Next

Once you get API keys:

1. **CoinTelegraph** → More recent breaking news
2. **CryptoCompare** → Aggregated sentiment & analysis
3. **Twitter** → Real-time market commentary

Each additional source increases the quality and breadth of market intelligence for Phase F.

---

## 💡 Pro Tips

1. **RSS feeds are fast** - Usually return articles within 1-2 seconds
2. **Web scraper is thorough** - Catches analysis pieces and opinion content
3. **Together they're comprehensive** - Good balance of speed + depth
4. **Phase F is resilient** - If one source fails, others continue working
5. **Deduplication is automatic** - No duplicate articles in analysis

---

## 🎯 Success Criteria

Phase F is working correctly when:
- ✅ No errors in logs
- ✅ Articles are fetched from RSS & Web Scraper
- ✅ Claims are extracted from articles
- ✅ Hypotheses are generated
- ✅ Verdicts are produced
- ✅ Governance receives verdicts and applies confidence penalties

---

**Questions?** See `phase_f/fetchers/MULTI_SOURCE_FETCHER.md` for complete documentation.

**Status**: 🟢 Ready to use
**Last Updated**: 2026-02-11
