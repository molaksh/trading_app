"""
Claim extraction from news articles.

Extracts factual statements from articles and validates them.
"""

import logging
import re
from typing import List, Optional
from phase_f.schemas import Claim, SentimentEnum
from phase_f.fetchers import NewsArticle

logger = logging.getLogger(__name__)


class ClaimExtractor:
    """Extract claims from articles using heuristics and validation."""

    def __init__(self):
        """Initialize extractor with forbidden words list."""
        self.forbidden_causation = ["causes", "leads to", "->", "results in", "makes", "forces"]
        self.sentiment_indicators = {
            "positive": [
                "bullish", "surge", "rally", "gain", "rise", "strength", "bull",
                "positive", "growth", "recovery", "outperform", "optimism", "confidence",
                "strength", "support", "bull case", "catalysts"
            ],
            "negative": [
                "bearish", "crash", "plunge", "decline", "fall", "weakness", "bear",
                "negative", "contraction", "collapse", "underperform", "fear", "concern",
                "weakness", "resistance", "bear case", "headwinds"
            ]
        }

    def extract_from_article(
        self,
        article: NewsArticle,
        max_claims: int = 3
    ) -> List[Claim]:
        """
        Extract claims from a news article.

        Args:
            article: NewsArticle to extract from
            max_claims: Maximum claims to extract per article

        Returns:
            List of Claim objects
        """
        claims = []

        # Combine title, description, content
        text_parts = [
            article.title,
            article.description or "",
            article.content or ""
        ]
        full_text = " ".join([p for p in text_parts if p])

        if not full_text.strip():
            return []

        try:
            # Extract factual sentences
            sentences = self._extract_sentences(full_text)

            for sentence in sentences[:max_claims]:
                claim = self._sentence_to_claim(
                    sentence,
                    article.source,
                    article.source_url,
                    article.published_at
                )
                if claim:
                    claims.append(claim)

            logger.debug(f"Extracted {len(claims)} claims from {article.source}")
            return claims

        except Exception as e:
            logger.error(f"Error extracting claims from article: {e}")
            return []

    def _extract_sentences(self, text: str) -> List[str]:
        """
        Extract factual sentences from text.

        Args:
            text: Full text to extract from

        Returns:
            List of candidate sentences
        """
        # Split by sentence
        sentences = re.split(r'[.!?]+', text)

        # Filter for substantial sentences
        candidates = []
        for sent in sentences:
            sent = sent.strip()
            # Must be at least 20 chars and not a question
            if len(sent) > 20 and not sent.endswith("?") and not any(
                x in sent.lower() for x in ["how do you", "what is", "when did"]
            ):
                candidates.append(sent)

        return candidates[:10]  # Limit to top 10 sentences

    def _sentence_to_claim(
        self,
        sentence: str,
        source: str,
        source_url: str,
        published_at: str
    ) -> Optional[Claim]:
        """
        Convert sentence to Claim object.

        Args:
            sentence: Sentence to convert
            source: Source name
            source_url: URL to source
            published_at: Publication timestamp

        Returns:
            Claim object or None if invalid
        """
        # Validate: no forbidden causation words
        sent_lower = sentence.lower()
        for forbidden in self.forbidden_causation:
            if forbidden in sent_lower:
                logger.debug(f"Skipping sentence with forbidden word '{forbidden}': {sentence[:50]}")
                return None

        # Determine sentiment
        sentiment = self._classify_sentiment(sentence)

        # Assign confidence (simple heuristic)
        confidence = self._estimate_confidence(sentence)

        # Create claim
        try:
            claim = Claim(
                claim_text=sentence,
                source=source,
                source_url=source_url,
                publication_timestamp=published_at,
                confidence_in_claim=confidence,
                is_factual=True,  # Assume news articles are factual
                sentiment=sentiment,
            )
            return claim
        except Exception as e:
            logger.debug(f"Error creating claim: {e}")
            return None

    def _classify_sentiment(self, text: str) -> SentimentEnum:
        """
        Classify sentiment of text.

        Args:
            text: Text to classify

        Returns:
            Sentiment enum
        """
        text_lower = text.lower()

        # Count positive and negative indicators
        pos_count = sum(1 for word in self.sentiment_indicators["positive"] if word in text_lower)
        neg_count = sum(1 for word in self.sentiment_indicators["negative"] if word in text_lower)

        if pos_count > neg_count:
            return SentimentEnum.POSITIVE
        elif neg_count > pos_count:
            return SentimentEnum.NEGATIVE
        else:
            return SentimentEnum.NEUTRAL

    def _estimate_confidence(self, sentence: str) -> float:
        """
        Estimate confidence in claim.

        Args:
            sentence: Claim sentence

        Returns:
            Confidence score (0.0-1.0)
        """
        # Heuristics for confidence
        confidence = 0.5  # Base

        # Specific numbers increase confidence
        if any(c.isdigit() for c in sentence):
            confidence += 0.15

        # Names of institutions increase confidence
        institutions = ["Fed", "IMF", "SEC", "CFTC", "ECB", "CME"]
        if any(inst in sentence for inst in institutions):
            confidence += 0.2

        # Precise language increases confidence
        precise_words = ["reached", "hit", "increased", "decreased", "rallied", "fell"]
        if any(word in sentence.lower() for word in precise_words):
            confidence += 0.1

        # Speculation words decrease confidence
        speculative = ["may", "could", "might", "possibly", "reportedly"]
        if any(word in sentence.lower() for word in speculative):
            confidence -= 0.2

        return max(0.0, min(1.0, confidence))
