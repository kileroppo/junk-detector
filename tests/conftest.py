"""Shared test fixtures for junk-detector test suite.

Provides mock LLM responses, sample texts, temp DB paths,
and mock scoring config for all test modules.
"""

from __future__ import annotations

import pytest

from src.models.score import ScoringConfig


@pytest.fixture
def mock_llm_response():
    """Return a dict matching DimensionScores structure for LLM mock responses."""
    return {
        "originality": 75,
        "info_density": 60,
        "reasoning_quality": 70,
        "readability": 80,
        "timeliness": 50,
        "ai_generated_prob": 20,
        "emotional_manipulation": 10,
        "advertorial_prob": 15,
        "scam_prob": 5,
        "summary": "This is a test summary",
        "confidence": 0.85,
        "labels": [],
    }


@pytest.fixture
def sample_junk_text():
    """Known bad text containing scam keywords."""
    return (
        "日入过万！躺赚财富自由！限时免费加微信领取秘籍！"
        "名额有限，最后一天！私聊领取！零成本稳赚不赔！"
    )


@pytest.fixture
def sample_good_text():
    """High quality article text (clean, no rule triggers)."""
    return (
        "近年来，人工智能技术在自然语言处理领域取得了显著进展。"
        "基于Transformer架构的大语言模型展现了强大的文本理解和生成能力。"
        "研究者通过在大规模语料库上进行预训练，使模型能够学习丰富的语言知识。"
        "随后的指令微调阶段则帮助模型更好地遵循用户指令，完成各类文本任务。"
        "这些技术的发展正在深刻改变信息处理和知识获取的方式。"
    )


@pytest.fixture
def tmp_db_path(tmp_path):
    """Temp SQLite path using pytest's tmp_path fixture."""
    return str(tmp_path / "test_junk_detector.db")


@pytest.fixture
def mock_config():
    """ScoringConfig with test defaults."""
    return ScoringConfig(
        primary_model="test-model/test",
        fallback_model="test-fallback/test",
        confidence_threshold=0.7,
    )


@pytest.fixture(autouse=True)
def reset_dedup_cache():
    """Reset the dedup cache before each test to prevent cross-test interference."""
    from src.core.dedup import reset_cache

    reset_cache()
    yield
    reset_cache()


@pytest.fixture
def set_api_key(monkeypatch):
    """Set a fake DEEPSEEK_API_KEY for tests that need app startup."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-for-testing")
