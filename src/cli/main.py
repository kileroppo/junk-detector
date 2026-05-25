"""CLI interface for junk-detector — score content quality from the terminal."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from typing import Optional

# Suppress LiteLLM startup noise before any litellm imports
os.environ.setdefault("LITELLM_LOG", "ERROR")

from dotenv import load_dotenv

# Auto-load .env from project root (searches upward from cwd)
load_dotenv()

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.models.score import Content, FastScoreResult, ScoreResult

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
# API Key Validation
# ---------------------------------------------------------------------------


def _validate_api_key(model_name: str) -> None:
    """Check that the required API key env var is set for the given model.

    Raises typer.Exit(code=1) with a helpful message if the key is missing.
    Models containing 'ollama' do not require an API key.
    """
    model_lower = model_name.lower()

    if "ollama" in model_lower:
        return

    key_map: list[tuple[list[str], str]] = [
        (["deepseek"], "DEEPSEEK_API_KEY"),
        (["openai", "gpt"], "OPENAI_API_KEY"),
        (["anthropic", "claude"], "ANTHROPIC_API_KEY"),
    ]

    for keywords, env_var in key_map:
        if any(kw in model_lower for kw in keywords):
            if not os.environ.get(env_var):
                console.print(
                    f"❌ {env_var} not set. Run: export {env_var}=your-key",
                    style="bold red",
                )
                raise typer.Exit(code=1)
            return

    # No known provider matched — warn but don't block (custom models via litellm are valid)
    console.print(
        f"⚠️  Unknown model provider '{model_name}'. Cannot validate API key.",
        style="yellow",
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def score(
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text content to score"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL to fetch and score"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="File path to read and score"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Model preset: ollama, deepseek, openai, anthropic"
    ),
    fast: bool = typer.Option(
        False, "--fast", help="Use fast 4-dimension scoring instead of full 9-dimension"
    ),
    retry: int = typer.Option(1, "--retry", help="Number of retry attempts for LLM timeouts"),
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

    # Fast scoring path
    if fast:
        try:
            from src.core.config import load_config
            from src.core.fast_scorer import score_fast

            config = load_config(override_model=model)

            fast_result: FastScoreResult = asyncio.run(
                score_fast(content.text, config=config, max_retries=retry)
            )
        except typer.Exit:
            raise
        except Exception as exc:
            console.print(f"❌ 快速评分失败: {exc}", style="bold red")
            raise typer.Exit(code=1)

        if json_output:
            output = fast_result.model_dump(mode="json")
            typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            _print_quick_verdict(fast_result)
        return

    # Score the content
    try:
        from src.core.config import load_config
        from src.core.scorer import score as do_score

        config = load_config(override_model=model)

        # Pre-check: validate API key for the configured model
        _validate_api_key(config.primary_model)

        result: ScoreResult = asyncio.run(do_score(content.text, config=config))
    except typer.Exit:
        raise
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
        from src.extractors.web import extract_from_url, extract_from_url_simple

        try:
            return asyncio.run(extract_from_url(url))
        except Exception as original_error:
            console.print(
                f"⚠️  主提取失败，尝试简单提取: {original_error}",
                style="yellow",
            )
            try:
                return asyncio.run(extract_from_url_simple(url))
            except Exception:
                raise original_error

    # Should not reach here due to earlier validation
    raise ValueError("No input source provided")


def _print_quick_verdict(result: FastScoreResult) -> None:
    """Print a single-line verdict based on the fast score result."""
    score_val = result.quick_verdict
    if score_val > 60:
        verdict = f"\u2705 \u770b\u8d77\u6765\u6b63\u5e38 (score: {score_val:.0f})"
    elif score_val >= 40:
        verdict = f"\u26a0\ufe0f \u9700\u8981\u6ce8\u610f (score: {score_val:.0f})"
    else:
        verdict = f"\U0001f6a8 \u7591\u4f3c\u5783\u573e\u5185\u5bb9 (score: {score_val:.0f})"
    console.print(verdict)


@app.command()
def quick(
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text content to score"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL to fetch and score"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="File path to read and score"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model preset"),
    retry: int = typer.Option(1, "--retry", help="Number of retry attempts for LLM timeouts"),
) -> None:
    """Quick content screening - single-line pass/fail verdict."""

    # Validate: exactly one input source
    sources = [s for s in (text, url, file) if s is not None]
    if len(sources) == 0:
        console.print(
            "\u274c \u9519\u8bef: \u5fc5\u987b\u6307\u5b9a --text, --url, \u6216 --file \u4e2d\u7684\u4e00\u4e2a",
            style="bold red",
        )
        raise typer.Exit(code=1)
    if len(sources) > 1:
        console.print(
            "\u274c \u9519\u8bef: \u53ea\u80fd\u6307\u5b9a --text, --url, --file \u4e2d\u7684\u4e00\u4e2a",
            style="bold red",
        )
        raise typer.Exit(code=1)

    try:
        content = _extract_content(text=text, url=url, file=file)
    except (ValueError, FileNotFoundError, TimeoutError) as exc:
        console.print(f"\u274c \u63d0\u53d6\u5185\u5bb9\u5931\u8d25: {exc}", style="bold red")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"\u274c \u672a\u77e5\u9519\u8bef: {exc}", style="bold red")
        raise typer.Exit(code=1)

    try:
        from src.core.config import load_config
        from src.core.fast_scorer import score_fast

        config = load_config(override_model=model)

        fast_result: FastScoreResult = asyncio.run(
            score_fast(content.text, config=config, max_retries=retry)
        )
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"\u274c \u5feb\u901f\u8bc4\u5206\u5931\u8d25: {exc}", style="bold red")
        raise typer.Exit(code=1)

    if json_output:
        output = fast_result.model_dump(mode="json")
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_quick_verdict(fast_result)


@app.command()
def batch(
    urls_file: Optional[str] = typer.Option(
        None, "--urls-file", help="Path to a file with one URL per line"
    ),
    stdin: bool = typer.Option(False, "--stdin", help="Read URLs from stdin"),
    fast: bool = typer.Option(
        True, "--fast/--no-fast", help="Use fast 4-dimension scoring (default: True)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON array instead of table"),
    retry: int = typer.Option(1, "--retry", help="Number of retry attempts for LLM timeouts"),
) -> None:
    """Batch score multiple URLs concurrently."""

    # Validate: exactly one input source
    if not urls_file and not stdin:
        console.print("❌ 错误: 必须指定 --urls-file 或 --stdin 中的一个", style="bold red")
        raise typer.Exit(code=1)
    if urls_file and stdin:
        console.print("❌ 错误: 只能指定 --urls-file 或 --stdin 中的一个", style="bold red")
        raise typer.Exit(code=1)

    # Read URLs
    if urls_file:
        path = Path(urls_file)
        if not path.exists():
            console.print(f"❌ 错误: 文件不存在: {urls_file}", style="bold red")
            raise typer.Exit(code=1)
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    else:
        raw_lines = sys.stdin.read().splitlines()

    # Filter empty lines and comments
    urls = [line.strip() for line in raw_lines if line.strip() and not line.strip().startswith("#")]

    if not urls:
        console.print("📭 没有需要评分的 URL", style="dim")
        return

    # Run batch scoring
    results = asyncio.run(_batch_score(urls, fast=fast, max_retries=retry))

    # Output
    if json_output:
        _batch_json_output(results)
    else:
        _batch_table_output(results)


async def _batch_score(urls: list[str], *, fast: bool = True, max_retries: int = 1) -> list[dict]:
    """Score multiple URLs concurrently with max 3 in-flight."""
    from src.extractors.web import extract_from_url, extract_from_url_simple

    semaphore = asyncio.Semaphore(3)

    async def _score_one(url: str) -> dict:
        async with semaphore:
            try:
                content = await extract_from_url(url)
            except Exception as primary_error:
                try:
                    content = await extract_from_url_simple(url)
                except Exception:
                    return {
                        "url": url,
                        "score": None,
                        "verdict": "ERROR",
                        "labels": [],
                        "summary": "",
                        "error": str(primary_error),
                    }

            try:
                if fast:
                    from src.core.fast_scorer import score_fast

                    result = await score_fast(content.text, max_retries=max_retries)
                    return {
                        "url": url,
                        "score": result.quick_verdict,
                        "verdict": _batch_verdict_text(result.quick_verdict),
                        "labels": [],
                        "summary": result.summary,
                        "error": None,
                    }
                else:
                    from src.core.scorer import score as do_score

                    result = await do_score(content.text)
                    return {
                        "url": url,
                        "score": result.overall_score,
                        "verdict": _batch_verdict_text(result.overall_score),
                        "labels": result.labels,
                        "summary": result.summary,
                        "error": None,
                    }
            except Exception as exc:
                return {
                    "url": url,
                    "score": None,
                    "verdict": "ERROR",
                    "labels": [],
                    "summary": "",
                    "error": str(exc),
                }

    tasks = [_score_one(url) for url in urls]
    return await asyncio.gather(*tasks)


def _batch_verdict_text(score: float) -> str:
    """Return verdict string based on score."""
    if score > 60:
        return "OK"
    elif score >= 40:
        return "CAUTION"
    else:
        return "JUNK"


def _batch_verdict_emoji(score: float) -> str:
    """Return verdict emoji + text based on score."""
    if score > 60:
        return "\u2705 \u6b63\u5e38"
    elif score >= 40:
        return "\u26a0\ufe0f \u6ce8\u610f"
    else:
        return "\U0001f6a8 \u5783\u573e"


def _batch_table_output(results: list[dict]) -> None:
    """Print batch results as a Rich table."""
    table = Table(title="批量评分结果", show_lines=False)
    table.add_column("URL", max_width=40, overflow="ellipsis")
    table.add_column("Score", justify="right", width=6)
    table.add_column("Verdict", width=10)
    table.add_column("Summary", max_width=30, overflow="ellipsis")

    for item in results:
        url_display = item["url"]
        if len(url_display) > 40:
            url_display = url_display[:37] + "..."

        if item["error"]:
            error_msg = item["error"]
            if len(error_msg) > 30:
                error_msg = error_msg[:27] + "..."
            table.add_row(url_display, "--", "\u274c \u5931\u8d25", error_msg)
        else:
            score_val = item["score"]
            color = _score_color(score_val)
            score_text = Text(f"{score_val:.0f}", style=color)
            verdict = _batch_verdict_emoji(score_val)
            summary = item["summary"] or ""
            if len(summary) > 30:
                summary = summary[:27] + "..."
            table.add_row(url_display, score_text, verdict, summary)

    console.print()
    console.print(table)

    # Summary line
    total = len(results)
    scored = [r for r in results if r["score"] is not None]
    avg = sum(r["score"] for r in scored) / len(scored) if scored else 0
    junk_count = sum(1 for r in scored if r["score"] < 40)
    caution_count = sum(1 for r in scored if 40 <= r["score"] <= 60)
    ok_count = sum(1 for r in scored if r["score"] > 60)

    console.print(
        f"\n\u5171 {total} \u7bc7 | \u5e73\u5747\u5206: {avg:.0f} | "
        f"\U0001f6a8 \u5783\u573e: {junk_count} | \u26a0\ufe0f \u6ce8\u610f: {caution_count} | \u2705 \u6b63\u5e38: {ok_count}"
    )
    console.print()


def _batch_json_output(results: list[dict]) -> None:
    """Print batch results as JSON array."""
    output = []
    for item in results:
        entry: dict = {"url": item["url"]}
        if item["error"]:
            entry["score"] = None
            entry["verdict"] = "ERROR"
            entry["error"] = item["error"]
        else:
            entry["score"] = item["score"]
            entry["verdict"] = item["verdict"]
            entry["labels"] = item["labels"]
            entry["summary"] = item["summary"]
        output.append(entry)
    typer.echo(json.dumps(output, ensure_ascii=False, indent=2))


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    min_score: Optional[float] = typer.Option(
        None, "--min-score", help="Filter by minimum overall score"
    ),
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


def _is_port_available(host: str, port: int) -> bool:
    """Return True if the TCP port can be bound on this machine."""
    # Match uvicorn's default: bind all interfaces when host is 0.0.0.0.
    bind_host = "" if host in ("0.0.0.0", "::") else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((bind_host, port))
        return True
    except OSError:
        return False


def _resolve_port(host: str, port: int, max_attempts: int = 100) -> int:
    """Use *port* if free, otherwise scan the next available ports."""
    for offset in range(max_attempts):
        candidate = port + offset
        if candidate > 65535:
            break
        if _is_port_available(host, candidate):
            if offset > 0:
                console.print(
                    f"[yellow]Port {port} is in use, starting on {candidate} instead[/yellow]"
                )
            return candidate
    console.print(f"[red]No free port in range {port}–{min(port + max_attempts - 1, 65535)}[/red]")
    raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Preferred port to bind"),
    strict_port: bool = typer.Option(
        False,
        "--strict-port",
        help="Fail if the preferred port is occupied instead of trying the next one",
    ),
) -> None:
    """Start the API server."""
    import uvicorn

    bind_port = port if strict_port else _resolve_port(host, port)
    uvicorn.run("src.api.app:app", host=host, port=bind_port, reload=True)  # pragma: no cover


@app.command()
def feedback(
    id: Optional[str] = typer.Option(
        None, "--id", help="Content hash (or prefix, at least 8 chars) to look up"
    ),
    verdict: Optional[str] = typer.Option(
        None, "--verdict", help="User verdict: junk, ok, or excellent"
    ),
    stats: bool = typer.Option(False, "--stats", help="Show calibration statistics"),
    suggest: bool = typer.Option(False, "--suggest", help="Show rule update suggestions"),
) -> None:
    """Record feedback on scored content or view calibration stats."""
    from src.core.calibration import (
        VALID_VERDICTS,
        get_calibration_stats,
        suggest_rule_updates,
    )
    from src.core.calibration import (
        record_feedback as cal_record_feedback,
    )

    # Show calibration stats
    if stats:
        cal_stats = get_calibration_stats()
        table = Table(title="Calibration Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Total Feedback", str(cal_stats["total_feedback_count"]))
        table.add_row("Agreement Rate", f"{cal_stats['agreement_rate']:.1f}%")
        table.add_row("False Positives", str(cal_stats["false_positives"]))
        table.add_row("False Negatives", str(cal_stats["false_negatives"]))
        console.print()
        console.print(table)
        console.print()
        return

    # Show rule update suggestions
    if suggest:
        suggestions = suggest_rule_updates()
        console.print()
        console.print("[bold]Rule Update Suggestions[/bold]")
        console.print("━" * 40)
        keywords = suggestions.get("suggested_keywords", [])
        removals = suggestions.get("suggested_removals", [])
        if keywords:
            console.print()
            console.print("[green]Suggested keywords to add:[/green]")
            for kw in keywords:
                console.print(f"  + {kw}")
        if removals:
            console.print()
            console.print("[yellow]Suggested keywords to remove:[/yellow]")
            for kw in removals:
                console.print(f"  - {kw}")
        if not keywords and not removals:
            console.print()
            console.print("[dim]No suggestions available. Record more feedback first.[/dim]")
        console.print()
        return

    # Record feedback mode: --id is required
    if id is None:
        console.print("❌ Error: --id is required when recording feedback", style="bold red")
        raise typer.Exit(code=1)

    if verdict is None:
        console.print("❌ Error: --verdict is required when --id is provided", style="bold red")
        raise typer.Exit(code=1)

    if verdict not in VALID_VERDICTS:
        console.print(
            f"❌ Error: invalid verdict '{verdict}'. Must be one of: {', '.join(VALID_VERDICTS)}",
            style="bold red",
        )
        raise typer.Exit(code=1)

    if len(id) < 8:
        console.print("❌ Error: --id must be at least 8 characters", style="bold red")
        raise typer.Exit(code=1)

    # Look up score by content_hash prefix
    from src.storage.db import lookup_by_hash_prefix

    db_path = "junk_detector.db"
    record = lookup_by_hash_prefix(id, db_path=db_path)

    if record is None:
        # Determine if it's "not found" or "multiple matches"
        from src.storage.db import _ensure_initialized, _get_connection

        _ensure_initialized(db_path)
        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM scores WHERE content_hash LIKE ?",
                (f"{id}%",),
            )
            count = cursor.fetchone()["cnt"]
        finally:
            conn.close()

        if count > 1:
            console.print(
                f"❌ Error: multiple scores match prefix '{id}'. Use a longer prefix.",
                style="bold red",
            )
            raise typer.Exit(code=1)
        else:
            console.print(f"❌ Error: no score found matching hash prefix '{id}'", style="bold red")
            raise typer.Exit(code=1)

    content_hash = record["content_hash"]
    title = record.get("title") or "Untitled"
    overall_score = record["overall_score"]

    # Record the feedback
    cal_record_feedback(content_hash, verdict, db_path=db_path)

    console.print()
    console.print("[green]Feedback recorded successfully![/green]")
    console.print(f"  Content: {title}")
    console.print(f"  Hash:    {content_hash[:16]}...")
    console.print(f"  Score:   {overall_score:.0f}")
    console.print(f"  Verdict: {verdict}")
    console.print()


if __name__ == "__main__":
    app()
