"""CLI interface for junk-detector — score content quality from the terminal."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from dotenv import load_dotenv

# Auto-load .env from project root (searches upward from cwd)
load_dotenv()

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.models.score import ScoreResult, Content

app = typer.Typer(
    name="junk-detector",
    help="AI content quality scorer — detect junk content with LLM-as-Judge + rules.",
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_color(score: float, *, inverted: bool = False) -> str:
    """Return a rich color name based on the score value.

    For positive dimensions: >= 70 green, 40-69 yellow, < 40 red.
    For negative/risk dimensions (inverted): < 40 green, 40-69 yellow, >= 70 red.
    """
    if inverted:
        if score >= 70:
            return "red"
        elif score >= 40:
            return "yellow"
        else:
            return "green"
    else:
        if score >= 70:
            return "green"
        elif score >= 40:
            return "yellow"
        else:
            return "red"


def _overall_emoji(score: float) -> str:
    """Return an emoji reflecting overall content quality."""
    if score >= 80:
        return "✅"
    elif score >= 60:
        return "👍"
    elif score >= 40:
        return "⚠️"
    else:
        return "🚨"


def _pretty_print_result(result: ScoreResult, content: Content) -> None:
    """Print a nicely formatted, colored score result to the console."""
    title = content.title or "无标题"
    emoji = _overall_emoji(result.overall_score)
    overall_color = _score_color(result.overall_score)

    console.print()
    console.print("📊 Junk Detector 评分结果", style="bold")
    console.print("━━━━━━━━━━━━━━━━━━━━━━━━━")
    console.print(f"标题: {title}")

    overall_text = Text()
    overall_text.append("综合评分: ")
    overall_text.append(f"{result.overall_score:.0f}/100", style=f"bold {overall_color}")
    overall_text.append(f"  {emoji}")
    console.print(overall_text)

    # Positive dimensions
    console.print()
    console.print("📈 正面维度:", style="bold")
    dims = result.dimensions
    positive_dims = [
        ("原创性", dims.originality),
        ("信息密度", dims.info_density),
        ("论证质量", dims.reasoning_quality),
        ("可读性", dims.readability),
        ("时效性", dims.timeliness),
    ]
    for name, value in positive_dims:
        color = _score_color(value, inverted=False)
        line = Text()
        line.append(f"  {name}:".ljust(14))
        line.append(f"{value:.0f}/100", style=color)
        console.print(line)

    # Negative / risk dimensions
    console.print()
    console.print("⚠️  风险维度:", style="bold")
    negative_dims = [
        ("AI生成概率", dims.ai_generated_prob),
        ("情绪操纵度", dims.emotional_manipulation),
        ("软文概率", dims.advertorial_prob),
        ("骗局概率", dims.scam_prob),
    ]
    for name, value in negative_dims:
        color = _score_color(value, inverted=True)
        line = Text()
        line.append(f"  {name}:".ljust(16))
        line.append(f"{value:.0f}/100", style=color)
        console.print(line)

    # Labels and summary
    console.print()
    labels_str = ", ".join(result.labels) if result.labels else "无"
    console.print(f"🏷️  标签: {labels_str}")
    console.print(f"💬 总结: {result.summary}")
    console.print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def score(
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text content to score"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL to fetch and score"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="File path to read and score"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Score content quality across 9 dimensions."""

    # Validate: exactly one input source
    sources = [s for s in (text, url, file) if s is not None]
    if len(sources) == 0:
        console.print("❌ 错误: 必须指定 --text, --url, 或 --file 中的一个", style="bold red")
        raise typer.Exit(code=1)
    if len(sources) > 1:
        console.print("❌ 错误: 只能指定 --text, --url, --file 中的一个", style="bold red")
        raise typer.Exit(code=1)

    try:
        content = _extract_content(text=text, url=url, file=file)
    except (ValueError, FileNotFoundError, TimeoutError) as exc:
        console.print(f"❌ 提取内容失败: {exc}", style="bold red")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"❌ 未知错误: {exc}", style="bold red")
        raise typer.Exit(code=1)

    # Score the content
    try:
        from src.core.scorer import score as do_score

        result: ScoreResult = asyncio.run(do_score(content.text))
    except Exception as exc:
        console.print(f"❌ 评分失败: {exc}", style="bold red")
        raise typer.Exit(code=1)

    # Save to storage
    try:
        from src.storage.db import save as db_save

        db_save(result, content)
    except Exception as exc:
        console.print(f"⚠️  保存记录失败 (评分结果仍然有效): {exc}", style="yellow")

    # Output
    if json_output:
        output = result.model_dump(mode="json")
        output["title"] = content.title
        output["source"] = content.source_url or "手动输入"
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _pretty_print_result(result, content)


def _extract_content(
    *,
    text: Optional[str],
    url: Optional[str],
    file: Optional[str],
) -> Content:
    """Extract content from the provided input source."""
    if text is not None:
        from src.extractors.text import extract_from_text

        return extract_from_text(text)

    if file is not None:
        from src.extractors.text import extract_from_file

        return extract_from_file(file)

    if url is not None:
        from src.extractors.web import extract_from_url

        return asyncio.run(extract_from_url(url))

    # Should not reach here due to earlier validation
    raise ValueError("No input source provided")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    min_score: Optional[float] = typer.Option(None, "--min-score", help="Filter by minimum overall score"),
    label: Optional[str] = typer.Option(None, "--label", help="Filter by label"),
) -> None:
    """View scoring history."""
    from src.storage.db import query

    filters: dict = {}
    if min_score is not None:
        filters["min_score"] = min_score
    if label is not None:
        filters["label"] = label

    try:
        records = query(filters=filters if filters else None, limit=limit)
    except Exception as exc:
        console.print(f"❌ 查询历史失败: {exc}", style="bold red")
        raise typer.Exit(code=1)

    if not records:
        console.print("📭 暂无评分记录", style="dim")
        return

    # Build table
    table = Table(title="评分历史", show_lines=False)
    table.add_column("日期", style="cyan", width=12)
    table.add_column("来源", style="blue", max_width=30, overflow="ellipsis")
    table.add_column("综合分", justify="right", width=6)
    table.add_column("标签", style="magenta")

    for record in records:
        # Parse date
        scored_at = record.get("scored_at", "")
        if scored_at:
            date_str = scored_at[:10]
        else:
            date_str = "—"

        # Source display
        source = record.get("source_url") or "手动输入"
        if len(source) > 28:
            source = source[:25] + "..."

        # Overall score with color
        overall = record.get("overall_score", 0)
        score_color = _score_color(overall)
        score_text = Text(f"{overall:.0f}", style=score_color)

        # Labels
        labels = record.get("labels", [])
        if isinstance(labels, str):
            try:
                labels = json.loads(labels)
            except (json.JSONDecodeError, TypeError):
                labels = [labels] if labels else []
        labels_str = ", ".join(labels) if labels else "—"

        table.add_row(date_str, source, score_text, labels_str)

    console.print()
    console.print(table)
    console.print()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
) -> None:
    """Start the API server."""
    import uvicorn

    uvicorn.run("src.api.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
