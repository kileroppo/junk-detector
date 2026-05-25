"""FastClassifier — lightweight ML model to pre-screen content before LLM.

Inspired by Phoenix's approach: train on historical data, use for high-confidence
predictions, fall back to LLM for uncertain cases.

Uses sklearn (optional dependency). Falls back gracefully if not installed.
"""
from __future__ import annotations

import hashlib
import logging
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("fast_classifier")

# Feature extraction patterns
_SCAM_KEYWORDS = ["日入过万", "限时免费", "私聊领取", "躺赚", "财富自由", "月入", "副业", "被动收入", "暴富"]
_EMOTIONAL_PATTERNS = [r"[!！]{3,}", r"[?？]{3,}", r"震惊", r"必看", r"不转不是"]
_AD_KEYWORDS = ["推荐码", "优惠券", "折扣", "限时", "点击链接", "扫码", "关注公众号"]
_AI_PATTERNS = ["综上所述", "总而言之", "值得注意的是", "需要指出的是", "不可否认"]


@dataclass
class ClassifierResult:
    """Result from the fast classifier."""
    predicted_score: float  # estimated overall score (0-100)
    confidence: float  # how confident the classifier is (0-1)
    category: str  # "junk", "low", "medium", "good"
    should_skip_llm: bool  # True if confidence high enough to skip LLM
    features: dict[str, float]  # extracted features (for debugging)


def extract_features(text: str) -> dict[str, float]:
    """Extract numerical features from text for classification.
    
    Features are designed to capture signals that correlate with
    content quality without needing an LLM.
    
    Args:
        text: The content text to analyze.
    
    Returns:
        Dictionary of feature_name -> float value.
    """
    features = {}
    
    # Length features
    features["char_count"] = len(text)
    features["word_count"] = len(text.split())
    lines = text.splitlines()
    features["line_count"] = len(lines)
    features["avg_line_length"] = features["char_count"] / max(features["line_count"], 1)
    
    # Punctuation features
    features["exclamation_ratio"] = text.count("!") + text.count("！") 
    features["question_ratio"] = text.count("?") + text.count("？")
    features["ellipsis_count"] = text.count("...") + text.count("…")
    
    # Keyword features
    text_lower = text.lower()
    features["scam_keyword_count"] = sum(1 for kw in _SCAM_KEYWORDS if kw in text)
    features["emotional_pattern_count"] = sum(1 for p in _EMOTIONAL_PATTERNS if re.search(p, text))
    features["ad_keyword_count"] = sum(1 for kw in _AD_KEYWORDS if kw in text)
    features["ai_pattern_count"] = sum(1 for p in _AI_PATTERNS if p in text)
    
    # Structure features
    features["has_title"] = 1.0 if any(line.startswith("#") for line in lines) else 0.0
    features["paragraph_count"] = sum(1 for line in lines if len(line.strip()) > 0)
    features["link_count"] = len(re.findall(r"https?://", text))
    features["number_ratio"] = len(re.findall(r"\d+", text)) / max(features["word_count"], 1)
    
    # Diversity features (unique chars / total chars — higher = more diverse vocabulary)
    unique_chars = len(set(text))
    features["char_diversity"] = unique_chars / max(len(text), 1)
    
    # Sentence structure
    sentences = re.split(r"[。.!！?？]", text)
    sentences = [s for s in sentences if len(s.strip()) > 2]
    features["sentence_count"] = len(sentences)
    features["avg_sentence_length"] = (
        sum(len(s) for s in sentences) / max(len(sentences), 1)
    )
    
    return features


def classify_fast(text: str, confidence_threshold: float = 0.85) -> ClassifierResult:
    """Classify content quality using rule-based heuristics + optional ML model.
    
    This is the "fast path" — runs in microseconds, no API calls.
    If the model file exists and sklearn is available, uses the trained model.
    Otherwise, falls back to rule-based heuristics.
    
    Args:
        text: Content to classify.
        confidence_threshold: Minimum confidence to skip LLM (default 0.85).
    
    Returns:
        ClassifierResult with predicted score, confidence, and skip recommendation.
    """
    features = extract_features(text)
    
    # Try ML model first
    model_result = _try_ml_model(features)
    if model_result is not None:
        return model_result
    
    # Fall back to rule-based heuristics
    return _rule_based_classify(features, confidence_threshold)


def _rule_based_classify(features: dict[str, float], threshold: float) -> ClassifierResult:
    """Rule-based classification when no ML model is available.
    
    Uses feature thresholds derived from common content patterns.
    """
    score = 50.0  # start neutral
    confidence = 0.5
    
    # Strong scam signals
    if features["scam_keyword_count"] >= 3:
        score = 15.0
        confidence = 0.9
    elif features["scam_keyword_count"] >= 2:
        score = 25.0
        confidence = 0.8
    
    # Strong ad signals
    elif features["ad_keyword_count"] >= 3:
        score = 30.0
        confidence = 0.8
    
    # Strong emotional manipulation
    elif features["emotional_pattern_count"] >= 3:
        score = 35.0
        confidence = 0.75
    
    # Very short content (< 50 chars) — likely junk
    elif features["char_count"] < 50:
        score = 20.0
        confidence = 0.85
    
    # High quality signals
    elif (features["char_count"] > 2000 
          and features["paragraph_count"] > 5 
          and features["scam_keyword_count"] == 0
          and features["ad_keyword_count"] == 0):
        score = 70.0
        confidence = 0.6  # less confident about high quality
    
    # AI-generated signals
    elif features["ai_pattern_count"] >= 3:
        score = 45.0
        confidence = 0.6
    
    # Determine category
    if score < 30:
        category = "junk"
    elif score < 50:
        category = "low"
    elif score < 70:
        category = "medium"
    else:
        category = "good"
    
    return ClassifierResult(
        predicted_score=score,
        confidence=confidence,
        category=category,
        should_skip_llm=confidence >= threshold,
        features=features,
    )


# --- ML Model support (optional) ---

_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "fast_classifier.pkl"
_loaded_model: Any = None


def _try_ml_model(features: dict[str, float]) -> ClassifierResult | None:
    """Try to use a trained sklearn model if available."""
    global _loaded_model
    
    if not _MODEL_PATH.exists():
        return None
    
    try:
        import numpy as np
        
        if _loaded_model is None:
            with open(_MODEL_PATH, "rb") as f:
                _loaded_model = pickle.load(f)
            logger.info(f"Loaded FastClassifier model from {_MODEL_PATH}")
        
        # Prepare feature vector
        feature_names = sorted(features.keys())
        X = np.array([[features[f] for f in feature_names]])
        
        # Predict
        predicted_category = _loaded_model.predict(X)[0]
        probabilities = _loaded_model.predict_proba(X)[0]
        confidence = float(max(probabilities))
        
        # Map category to score
        category_scores = {"junk": 15, "low": 40, "medium": 60, "good": 80}
        predicted_score = category_scores.get(predicted_category, 50)
        
        return ClassifierResult(
            predicted_score=predicted_score,
            confidence=confidence,
            category=predicted_category,
            should_skip_llm=confidence >= 0.85,
            features=features,
        )
    except ImportError:
        logger.debug("sklearn not available, skipping ML model")
        return None
    except Exception as e:
        logger.warning(f"ML model prediction failed: {e}")
        return None
