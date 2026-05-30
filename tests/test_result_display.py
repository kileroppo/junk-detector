"""Tests for result display data builder and persisted dual-score fields."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.storage.db import init_db, query, save
from src.web.result_display import (
    build_annotated_paragraphs,
    build_dimension_explanation,
    build_label_chips,
    build_reading_map_display,
    build_reading_verdict,
    build_result_display_data,
    build_result_display_data_from_record,
    build_skippable_display,
    align_display_tier,
    build_reading_action,
    build_sticky_bar_data,
    score_tier,
)


@pytest.fixture
def web_client(set_api_key):
    from src.api.app import app

    with patch("src.api.rate_limit.SlidingWindowLimiter.is_allowed", return_value=True):
        with TestClient(app) as client:
            yield client


def test_build_result_display_data_from_record_dual_score():
    record = {
        "overall_score": 75.0,
        "rule_score": 35.0,
        "rules_fired": True,
        "dimensions": {"scam_prob": 90},
        "labels": ["疑似骗局"],
        "summary": "Scam content",
        "rule_hits": ["scam_keywords"],
        "dimension_sources": {"scam_prob": "rule"},
        "scored_at": "2024-01-01T12:00:00",
    }

    data = build_result_display_data_from_record(record)

    assert data["rules_fired"] is True
    assert data["rule_score"] == 35.0
    assert data["llm_score"] == 75.0
    assert data["divergence_warning"] is True
    assert data["rule_hits"] == ["scam_keywords"]


def test_save_and_query_persists_dual_score_fields(tmp_db_path):
    init_db(tmp_db_path)
    content = Content(input_type=InputType.TEXT, text="日入过万 躺赚 财富自由")
    content.compute_hash()
    result = ScoreResult(
        overall_score=25.0,
        dimensions=DimensionScores(
            originality=10,
            info_density=5,
            reasoning_quality=10,
            readability=30,
            timeliness=20,
            ai_generated_prob=20,
            emotional_manipulation=80,
            advertorial_prob=70,
            scam_prob=95,
        ),
        labels=["疑似骗局"],
        summary="Scam",
        rule_hits=["scam_keywords"],
        dimension_sources={"scam_prob": "rule"},
        rule_score=18.5,
        rules_fired=True,
    )

    save(result, content, db_path=tmp_db_path)
    records = query(limit=1, db_path=tmp_db_path)

    assert len(records) == 1
    stored = records[0]
    assert stored["rule_score"] == 18.5
    assert stored["rules_fired"] is True
    assert stored["dimension_sources"] == {"scam_prob": "rule"}
    assert stored["rule_hits"] == ["scam_keywords"]


def test_save_and_query_persists_focus_guide(tmp_db_path):
    init_db(tmp_db_path)
    content = Content(input_type=InputType.TEXT, text="首先，在当今社会，人工智能技术已经成为了一个不可忽视的力量。")
    content.compute_hash()
    result = ScoreResult(
        overall_score=30.0,
        dimensions=DimensionScores(
            originality=20,
            info_density=25,
            reasoning_quality=30,
            readability=50,
            timeliness=30,
            ai_generated_prob=85,
            emotional_manipulation=15,
            advertorial_prob=20,
            scam_prob=10,
        ),
        labels=["可能AI生成"],
        summary="AI content",
        focus_guide={
            "recommendation": "skim",
            "information_nuggets": [{"index": 0, "summary": "AI趋势概述"}],
            "empty_calorie_indices": [2],
        },
    )

    save(result, content, db_path=tmp_db_path)
    stored = query(limit=1, db_path=tmp_db_path)[0]

    assert stored["focus_guide"]["recommendation"] == "skim"
    assert stored["focus_guide"]["information_nuggets"][0]["summary"] == "AI趋势概述"


def test_save_and_query_persists_content_text(tmp_db_path):
    init_db(tmp_db_path)
    text = "第一段核心观点，含具体数据 85。\n\n第二段空洞废话。\n\n第三段此外科技参数堆砌。"
    content = Content(input_type=InputType.TEXT, text=text)
    content.compute_hash()
    result = ScoreResult(
        overall_score=40.0,
        dimensions=DimensionScores(
            originality=30,
            info_density=35,
            reasoning_quality=30,
            readability=50,
            timeliness=30,
            ai_generated_prob=60,
            emotional_manipulation=20,
            advertorial_prob=40,
            scam_prob=10,
        ),
        labels=["软文倾向"],
        summary="Mixed",
        focus_guide={
            "recommendation": "skim",
            "top_nuggets": [{"index": 0, "preview": "第一段", "search_anchor": "第一段核心"}],
            "reading_map": ["gold", "skip", "caution"],
            "empty_calorie_indices": [1],
            "caution": {
                "headline": "别被参数带跑",
                "message": "数字密集",
                "search_anchor": "此外科技",
                "index": 2,
            },
        },
    )

    save(result, content, db_path=tmp_db_path)
    stored = query(limit=1, db_path=tmp_db_path)[0]

    assert stored["content_text"] == text
    assert stored["content_truncated"] is False


def test_build_annotated_paragraphs():
    text = "第一段核心观点。\n\n第二段可略。\n\n第三段警惕内容。"
    focus_guide = {
        "top_nuggets": [{"index": 0}],
        "reading_map": ["gold", "skip", "caution"],
        "caution": {"search_anchor": "第三段警惕"},
    }
    paras = build_annotated_paragraphs(text, focus_guide)

    assert len(paras) == 3
    assert paras[0]["status"] == "gold"
    assert paras[0]["label"] == "必看"
    assert paras[1]["status"] == "skip"
    assert paras[2]["status"] == "caution"
    assert paras[2]["label"] == "警惕"


def test_build_reading_map_display_groups_and_summarizes():
    focus_guide = {
        "recommendation": "skim",
        "reading_map": ["gold", "gold", "skip", "skip", "skip", "neutral"],
        "reading_time_saved_percent": 50,
        "caution": {"index": 5, "headline": "警惕"},
    }
    display = build_reading_map_display(focus_guide)

    assert display is not None
    assert display["total_paragraphs"] == 6
    assert "全文 6 段" in display["summary"]
    assert "2 处值得看" in display["summary"]
    assert "3 段可略" in display["summary"]
    assert len(display["segments"]) == 3
    assert display["segments"][-1]["status"] == "caution"
    assert "开篇重点看" in display["route_hint"]


def test_build_skippable_display_enriches_sections():
    focus_guide = {
        "paragraph_count": 10,
        "reading_time_saved_percent": 40,
        "skippable_sections": [
            {
                "start_index": 2,
                "end_index": 4,
                "preview": "此外，随着科技发展…（共 3 段同类内容）",
                "search_anchor": "此外，随着科技",
                "reason": "连续 3 段缺少数据",
                "evidence": ["此外", "总而言之"],
                "position_label": "中部",
                "position_percent": 35,
                "headline": "连续注水区",
                "skip_advice": "整段可略，节省最多阅读时间",
                "pattern_type": "water",
                "paragraph_count": 3,
            }
        ],
    }
    display = build_skippable_display(focus_guide)

    assert display is not None
    assert display["zone_count"] == 1
    assert "1 处可略" in display["summary"]
    assert "涉及 3 段" in display["summary"]
    section = display["sections"][0]
    assert section["pattern_label"] == "注水"
    assert section["index_label"] == "第 3–5 段"
    assert section["range_width_percent"] >= 6
    assert display["preview_sections"][0]["paragraph_count"] >= display["preview_sections"][-1]["paragraph_count"]
    assert "compact_title" in section


@patch("src.web.router.query")
def test_result_detail_shows_skippable_zones(mock_query, web_client):
    mock_query.return_value = [
        {
            "id": 5,
            "overall_score": 35.0,
            "dimensions": {
                "originality": 20,
                "info_density": 25,
                "reasoning_quality": 30,
                "readability": 50,
                "timeliness": 30,
                "ai_generated_prob": 80,
                "emotional_manipulation": 15,
                "advertorial_prob": 20,
                "scam_prob": 10,
            },
            "labels": ["可能AI生成"],
            "summary": "AI",
            "model_used": "test",
            "cost": 0.0,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": "Skip zones",
            "source_url": None,
            "focus_guide": {
                "recommendation": "skim",
                "paragraph_count": 8,
                "information_nuggets": [],
                "top_nuggets": [],
                "skippable_sections": [{
                    "start_index": 1,
                    "end_index": 2,
                    "preview": "首先，在当今社会…",
                    "search_anchor": "首先，在当今",
                    "reason": "命中 2 处空泛表述",
                    "evidence": ["首先", "在当今社会"],
                    "position_label": "前部",
                    "position_percent": 20,
                    "headline": "套话堆叠区",
                    "skip_advice": "跳过不影响理解文章主线",
                    "pattern_type": "filler",
                    "paragraph_count": 2,
                }],
            },
        }
    ]

    response = web_client.get("/result/5")

    assert response.status_code == 200
    html = response.text
    assert "哪里可以略读" in html
    assert "套话堆叠区" in html
    assert "skip-zone-disclosure" in html


@patch("src.web.router.query")
def test_result_detail_shows_reading_route(mock_query, web_client):
    mock_query.return_value = [
        {
            "id": 4,
            "overall_score": 40.0,
            "dimensions": {
                "originality": 30,
                "info_density": 35,
                "reasoning_quality": 30,
                "readability": 50,
                "timeliness": 30,
                "ai_generated_prob": 60,
                "emotional_manipulation": 20,
                "advertorial_prob": 40,
                "scam_prob": 10,
            },
            "labels": [],
            "summary": "Mixed",
            "model_used": "test",
            "cost": 0.0,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": "Route map",
            "source_url": None,
            "focus_guide": {
                "recommendation": "skim",
                "reading_map": ["gold", "skip", "skip", "neutral"],
                "reading_time_saved_percent": 50,
                "top_nuggets": [{"index": 0}],
            },
        }
    ]

    response = web_client.get("/result/4")

    assert response.status_code == 200
    html = response.text
    assert "阅读路线" in html
    assert "全文 4 段" in html
    assert "reading-map-block" in html
    assert "reading-map-track--magnify" in html


@patch("src.web.router.query")
def test_result_detail_shows_side_by_side_source(mock_query, web_client):
    mock_query.return_value = [
        {
            "id": 3,
            "overall_score": 40.0,
            "dimensions": {
                "originality": 30,
                "info_density": 35,
                "reasoning_quality": 30,
                "readability": 50,
                "timeliness": 30,
                "ai_generated_prob": 60,
                "emotional_manipulation": 20,
                "advertorial_prob": 40,
                "scam_prob": 10,
            },
            "labels": ["软文倾向"],
            "summary": "Mixed",
            "model_used": "test",
            "cost": 0.0,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": "Side by side",
            "source_url": None,
            "content_text": "第一段核心观点。\n\n第二段可略。",
            "content_truncated": False,
            "focus_guide": {
                "recommendation": "skim",
                "verdict_headline": "跳读即可",
                "top_nuggets": [{
                    "index": 0,
                    "preview": "第一段",
                    "search_anchor": "第一段核心",
                    "why_read": "含核心观点",
                    "position_label": "开篇",
                    "position_percent": 5,
                }],
                "reading_map": ["gold", "skip"],
            },
        }
    ]

    response = web_client.get("/result/3")

    assert response.status_code == 200
    html = response.text
    assert "原文对照" in html
    assert "focus-para-0" in html
    assert "focus-icon-btn" in html
    assert 'aria-label="定位原文"' in html
    assert "focus-junk-toggle" in html
    assert "data-focus-junk-toggle" in html
    assert 'id="focus-source-panel"' in html
    assert "verdict-hero" in html
    assert "scrollToFocusPara(" in html
    assert "/static/focus_guide.js" in html
    assert "dimension-row--linkable" in html
    assert "linkDimensionToSource" in html
    assert "linkParagraphToDimensions" in html
    assert "focus-para-dim-tag" in html
    assert "data-paragraph-indices" in html


@patch("src.web.router.query")
def test_result_title_links_to_source_url_when_no_inline_text(mock_query, web_client):
    mock_query.return_value = [
        {
            "id": 1,
            "overall_score": 75.0,
            "dimensions": {
                "originality": 80,
                "info_density": 70,
                "reasoning_quality": 75,
                "readability": 85,
                "timeliness": 60,
                "ai_generated_prob": 15,
                "emotional_manipulation": 10,
                "advertorial_prob": 20,
                "scam_prob": 5,
            },
            "labels": [],
            "summary": "Good",
            "model_used": "test",
            "cost": 0.0,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": "Article headline",
            "source_url": "https://example.com/article",
        }
    ]

    response = web_client.get("/result/1")

    assert response.status_code == 200
    html = response.text
    assert "verdict-hero" in html
    assert 'href="https://example.com/article"' in html
    assert "来源 URL" in html
    assert "scrollToFocusSource()" not in html


@patch("src.web.router.query")
def test_result_detail_shows_focus_guide_from_db(mock_query, web_client):
    mock_query.return_value = [
        {
            "id": 2,
            "overall_score": 30.0,
            "dimensions": {
                "originality": 20,
                "info_density": 25,
                "reasoning_quality": 30,
                "readability": 50,
                "timeliness": 30,
                "ai_generated_prob": 85,
                "emotional_manipulation": 15,
                "advertorial_prob": 20,
                "scam_prob": 10,
            },
            "labels": ["可能AI生成"],
            "summary": "AI content",
            "model_used": "test",
            "cost": 0.0,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": "Test",
            "source_url": None,
            "focus_guide": {
                "recommendation": "skim",
                "verdict_headline": "跳读即可",
                "verdict_detail": "精华集中在 2 处",
                "top_nuggets": [{
                    "index": 0,
                    "summary": "核心观点",
                    "preview": "首先人工智能",
                    "search_anchor": "首先人工智能",
                    "why_read": "含具体数据: 85",
                    "position_label": "开篇",
                    "position_percent": 8,
                    "density_score": 0.5,
                }],
                "caution": {
                    "headline": "别被参数带跑",
                    "message": "数字密集但缺乏独立判断",
                    "preview": "此外科技",
                    "search_anchor": "此外科技",
                },
                "snippets": [{
                    "index": 0,
                    "text": "首先，在当今社会…",
                    "status": "gold",
                    "search_anchor": "首先人工智能",
                    "label": "必看",
                }],
                "information_nuggets": [{"index": 0, "summary": "核心观点", "preview": "x", "search_anchor": "a", "why_read": "y", "position_label": "开篇", "position_percent": 8, "density_score": 0.5}],
                "empty_calorie_indices": [1, 3],
            },
        }
    ]

    response = web_client.get("/result/2")

    assert response.status_code == 200
    html = response.text
    assert "阅读结论" in html or "必看" in html
    assert "别信" in html or "原文摘录" in html


@patch("src.web.router.query")
def test_result_detail_shows_dual_score_from_db(mock_query, web_client):
    mock_query.return_value = [
        {
            "id": 1,
            "overall_score": 75.0,
            "rule_score": 30.0,
            "rules_fired": True,
            "dimensions": {
                "originality": 80,
                "info_density": 70,
                "reasoning_quality": 75,
                "readability": 85,
                "timeliness": 60,
                "ai_generated_prob": 15,
                "emotional_manipulation": 10,
                "advertorial_prob": 20,
                "scam_prob": 5,
            },
            "labels": [],
            "summary": "Good",
            "model_used": "test",
            "cost": 0.0,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": "Test",
            "source_url": "https://example.com",
            "rule_hits": ["scam_keywords"],
            "dimension_sources": {"scam_prob": "rule"},
        }
    ]

    response = web_client.get("/result/1")

    assert response.status_code == 200
    html = response.text
    assert "规则预检" in html
    assert "判定依据" in html
    assert "关键词匹配" not in html


def test_score_tier_bands():
    from src.web.result_display import score_tier

    assert score_tier(85)["label"] == "质量良好"
    assert score_tier(65)["label"] == "整体一般"
    assert score_tier(45)["label"] == "存在风险"
    assert score_tier(20)["label"] == "高风险"

    roundup_dims = {"scam_prob": 30, "emotional_manipulation": 10}
    assert score_tier(38, content_genre="roundup", dimensions=roundup_dims)["label"] == "汇编参考"
    assert score_tier(20, content_genre="roundup", dimensions=roundup_dims)["label"] == "高风险"


def test_roundup_low_score_action_skim_not_junk_headline():
    """38 分汇编文：裁决为速查，档位为汇编参考，非高风险。"""
    dims = {
        "scam_prob": 30,
        "emotional_manipulation": 10,
        "ai_generated_prob": 85,
        "advertorial_prob": 70,
    }
    tier = score_tier(38, content_genre="roundup", dimensions=dims)
    verdict = build_reading_verdict(
        {"recommendation": "skim", "verdict_detail": "汇编参考"},
        tier,
        38,
        {"top_risks": [], "top_positive": []},
        content_genre="roundup",
    )
    action = build_reading_action(
        verdict, tier, content_genre="roundup", dimensions=dims, overall_score=38
    )
    display = align_display_tier(tier, action, content_genre="roundup")
    assert action["label"] == "速查即可"
    assert display["label"] == "汇编参考"
    assert display["label"] != "高风险"


def test_build_dimension_highlights():
    from src.web.result_display import build_dimension_highlights

    highlights = build_dimension_highlights(
        {
            "originality": 90,
            "info_density": 40,
            "reasoning_quality": 50,
            "readability": 60,
            "timeliness": 30,
            "ai_generated_prob": 80,
            "emotional_manipulation": 70,
            "advertorial_prob": 10,
            "scam_prob": 5,
        }
    )
    assert highlights["top_positive"][0]["key"] == "originality"
    assert {d["key"] for d in highlights["top_risks"]} == {
        "ai_generated_prob",
        "emotional_manipulation",
    }


def test_build_rule_hit_display_dedupes_labels():
    from src.web.result_display import build_rule_hit_display

    display = build_rule_hit_display(["scam_keywords", "scam_combo"])
    assert len(display) == 1
    assert display[0]["label"] == "骗局关键词"
    assert display[0]["rules"] == ["scam_keywords", "scam_combo"]
    assert display[0]["dim_keys"] == ["scam_prob"]


def test_build_rule_hit_display_links_evidence():
    from src.web.result_display import build_rule_hit_display

    evidence = {
        "scam_prob": {"paragraph_indices": [2, 3], "linkable": True},
    }
    display = build_rule_hit_display(["scam_keywords"], evidence)
    assert display[0]["linkable"] is True
    assert display[0]["paragraph_indices"] == [2, 3]


def test_enrich_annotated_paragraphs_with_dimensions():
    from src.web.result_display import enrich_annotated_paragraphs_with_dimensions

    paragraphs = [{"index": 0, "status": "gold", "text": "a"}]
    evidence = {
        "originality": {"paragraph_indices": [0], "linkable": True},
        "scam_prob": {"paragraph_indices": [0], "linkable": True},
    }
    enriched = enrich_annotated_paragraphs_with_dimensions(paragraphs, evidence)
    assert len(enriched[0]["related_dimensions"]) == 2
    keys = {d["key"] for d in enriched[0]["related_dimensions"]}
    assert keys == {"originality", "scam_prob"}


def test_build_dimension_evidence_map_links_paragraphs():
    from src.web.result_display import build_dimension_evidence_map

    focus_guide = {
        "recommendation": "skim",
        "top_nuggets": [{"index": 1, "summary": "核心观点"}],
        "caution": {"index": 3, "headline": "警惕"},
        "empty_calorie_indices": [5, 6],
    }
    paragraphs = [
        {"index": 0, "status": "neutral", "label": "", "text": "a"},
        {"index": 1, "status": "gold", "label": "必看", "text": "b"},
        {"index": 2, "status": "skip", "label": "可略", "text": "c"},
        {"index": 3, "status": "caution", "label": "警惕", "text": "d"},
        {"index": 5, "status": "skip", "label": "可略", "text": "e"},
    ]
    dimensions = {
        "originality": 88,
        "info_density": 70,
        "reasoning_quality": 60,
        "readability": 60,
        "timeliness": 50,
        "ai_generated_prob": 75,
        "emotional_manipulation": 80,
        "advertorial_prob": 40,
        "scam_prob": 90,
    }

    evidence = build_dimension_evidence_map(
        dimensions=dimensions,
        focus_guide=focus_guide,
        annotated_paragraphs=paragraphs,
    )

    assert evidence["scam_prob"]["paragraph_indices"] == [3]
    assert evidence["originality"]["paragraph_indices"] == [1]
    assert 5 in evidence["ai_generated_prob"]["paragraph_indices"]
    assert all(item["linkable"] for item in evidence.values())


def test_build_dimension_evidence_empty_without_source():
    from src.web.result_display import build_dimension_evidence_map

    assert build_dimension_evidence_map(
        dimensions={"scam_prob": 90},
        focus_guide=None,
        annotated_paragraphs=[],
    ) == {}


def test_build_reading_verdict_from_focus_guide():
    focus_guide = {
        "recommendation": "skim",
        "verdict_headline": "跳读即可",
        "verdict_detail": "精华集中在 2 处",
    }
    tier = score_tier(65)
    highlights = {"top_positive": [], "top_risks": []}

    verdict = build_reading_verdict(focus_guide, tier, 65, highlights)

    assert verdict["headline"] == "跳读即可"  # explicit focus_guide headline preserved
    assert verdict["detail"] == "精华集中在 2 处"
    assert verdict["css"] == "focus-verdict--skim"


def test_build_reading_verdict_focus_guide_recommendation_fallback():
    focus_guide = {"recommendation": "skip", "tldr": "水分太多"}
    tier = score_tier(30)

    verdict = build_reading_verdict(focus_guide, tier, 30, {"top_positive": [], "top_risks": []})

    assert verdict["headline"] == "建议跳过"
    assert verdict["detail"] == "水分太多"


def test_build_reading_verdict_no_focus_guide_quality():
    tier = score_tier(85)
    highlights = {
        "top_positive": [{"label": "原创性", "value": 90}],
        "top_risks": [{"label": "骗局概率", "value": 10}],
    }

    verdict = build_reading_verdict(None, tier, 85, highlights)

    assert verdict["headline"] == "值得细读"
    assert verdict["detail"] == "未发现明显风险信号"
    assert verdict["css"] == "focus-verdict--read_carefully"


def test_build_reading_verdict_no_focus_guide_with_risks():
    tier = score_tier(45)
    highlights = {
        "top_positive": [{"label": "原创性", "value": 40}],
        "top_risks": [
            {"label": "骗局概率", "value": 82},
            {"label": "情绪操纵", "value": 71},
        ],
    }

    verdict = build_reading_verdict(None, tier, 45, highlights)

    assert verdict["headline"] == "速查即可"
    assert "骗局概率 82" in verdict["detail"]


def test_build_dimension_explanation_risks():
    highlights = {
        "top_positive": [{"label": "原创性", "value": 40}],
        "top_risks": [
            {"label": "骗局概率", "value": 82},
            {"label": "情绪操纵", "value": 71},
        ],
    }

    assert build_dimension_explanation(highlights) == "拉低分数的主要是：骗局概率 82、情绪操纵 71"


def test_build_dimension_explanation_positive():
    highlights = {
        "top_positive": [{"label": "原创性", "value": 88}],
        "top_risks": [{"label": "骗局概率", "value": 20}],
    }

    assert build_dimension_explanation(highlights) == "主要亮点：原创性 88"


def test_build_label_chips_types():
    chips = build_label_chips(["高质量内容", "疑似骗局", "可能AI生成", "软文倾向"])

    assert chips == [
        {"text": "高质量内容", "type": "good"},
        {"text": "疑似骗局", "type": "bad"},
        {"text": "可能AI生成", "type": "ai"},
        {"text": "软文倾向", "type": "warn"},
    ]


def test_build_sticky_bar_data():
    reading_verdict = {
        "headline": "速查即可",
        "css": "focus-verdict--skim",
        "recommendation": "skim",
    }
    tier = score_tier(65)
    action = build_reading_action(reading_verdict, tier)
    display = align_display_tier(tier, action)

    bar = build_sticky_bar_data(
        title="测试标题",
        reading_verdict=reading_verdict,
        reading_action=action,
        score=65.4,
        score_tier=tier,
        display_tier=display,
        dimension_explanation="主要亮点：原创性 88",
        source_url="https://example.com",
        record_id=42,
    )

    assert bar["title"] == "测试标题"
    assert bar["verdict_label"] == "速查即可"
    assert bar["verdict_css"] == "focus-verdict--skim"
    assert bar["score"] == 65
    assert bar["score_tier_label"] == "整体一般"
    assert bar["score_tier_css"] == "score-tier-normal"
    assert bar["source_url"] == "https://example.com"
    assert bar["record_id"] == 42
    assert "速查即可" in bar["copy_text"]
    assert "65分" in bar["copy_text"]
    assert "测试标题" in bar["copy_text"]


def test_build_result_display_data_includes_new_fields():
    data = build_result_display_data(
        overall_score=85,
        dimensions={
            "originality": 90,
            "info_density": 70,
            "reasoning_quality": 75,
            "readability": 80,
            "timeliness": 60,
            "ai_generated_prob": 15,
            "emotional_manipulation": 10,
            "advertorial_prob": 20,
            "scam_prob": 5,
        },
        labels=["高质量内容"],
        title="Good article",
        source_url="https://example.com/article",
    )

    assert "reading_verdict" in data
    assert data["reading_verdict"]["headline"] == "值得细读"
    assert "reading_action" in data
    assert data["reading_action"]["label"] == "值得细读"
    assert data["dimension_explanation"] == "主要亮点：原创性 90"
    assert data["sticky_bar"]["score"] == 85
    assert data["label_chips"] == [{"text": "高质量内容", "type": "good"}]

