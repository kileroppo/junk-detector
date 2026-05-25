"""CLI interface for junk-detector — score content quality from the terminal."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Auto-load .env from project root (searches upward from cwd)
load_dotenv()

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.models.score import ScoreResult, FastScoreResult, Content

app = typer.Typer(
    name="junk-detector",
    help="AI content quality scorer — detect junk content with LLM-as-Judge + rules.",
)

# Monitor command group
monitor_app = typer.Typer(
    name="monitor",
    help="Real-time content stream monitoring (Thunder + Dispatcher).",
)
app.add_typer(monitor_app, name="monitor")

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
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model preset: ollama, deepseek, openai, anthropic"),
    fast: bool = typer.Option(False, "--fast", help="Use fast 4-dimension scoring instead of full 9-dimension"),
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
            _validate_api_key(config.primary_model)

            fast_result: FastScoreResult = asyncio.run(score_fast(content.text, config=config, max_retries=retry))
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
        console.print("\u274c \u9519\u8bef: \u5fc5\u987b\u6307\u5b9a --text, --url, \u6216 --file \u4e2d\u7684\u4e00\u4e2a", style="bold red")
        raise typer.Exit(code=1)
    if len(sources) > 1:
        console.print("\u274c \u9519\u8bef: \u53ea\u80fd\u6307\u5b9a --text, --url, --file \u4e2d\u7684\u4e00\u4e2a", style="bold red")
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
        _validate_api_key(config.primary_model)

        fast_result: FastScoreResult = asyncio.run(score_fast(content.text, config=config, max_retries=retry))
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
    urls_file: Optional[str] = typer.Option(None, "--urls-file", help="Path to a file with one URL per line"),
    stdin: bool = typer.Option(False, "--stdin", help="Read URLs from stdin"),
    fast: bool = typer.Option(True, "--fast/--no-fast", help="Use fast 4-dimension scoring (default: True)"),
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
    results = asyncio.run(_batch_score(urls, fast=fast))

    # Output
    if json_output:
        _batch_json_output(results)
    else:
        _batch_table_output(results)


async def _batch_score(urls: list[str], *, fast: bool = True) -> list[dict]:
    """Score multiple URLs concurrently with max 3 in-flight."""
    from src.extractors.web import extract_from_url

    semaphore = asyncio.Semaphore(3)

    async def _score_one(url: str) -> dict:
        async with semaphore:
            try:
                content = await extract_from_url(url)
            except Exception as exc:
                return {"url": url, "score": None, "verdict": "ERROR", "labels": [], "summary": "", "error": str(exc)}

            try:
                if fast:
                    from src.core.fast_scorer import score_fast

                    result = await score_fast(content.text)
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
                return {"url": url, "score": None, "verdict": "ERROR", "labels": [], "summary": "", "error": str(exc)}

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
    console.print(
        f"[red]No free port in range {port}–{min(port + max_attempts - 1, 65535)}[/red]"
    )
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


# ---------------------------------------------------------------------------
# Monitor Commands
# ---------------------------------------------------------------------------


def _print_monitor_banner(stats: dict) -> None:
    """Print a startup banner showing monitoring status."""
    thunder = stats.get("thunder", {})
    dispatcher = stats.get("dispatcher", {})

    console.print()
    console.print("=" * 60, style="bold cyan")
    console.print("  [bold cyan]Thunder Monitor[/bold cyan] — Real-time Content Scoring")
    console.print("=" * 60, style="bold cyan")
    console.print()
    console.print(f"  Sources active:     {thunder.get('sources_count', 0)}")
    console.print(f"  Max concurrency:    {dispatcher.get('max_in_flight', 0)}")
    console.print(f"  Queue size:         {dispatcher.get('queue_size', 0)}")
    console.print()
    console.print("  Press [bold]Ctrl+C[/bold] to stop gracefully.")
    console.print("━" * 60)
    console.print()


def _print_status_update(stats: dict) -> None:
    """Print a periodic status update."""
    thunder = stats.get("thunder", {})
    dispatcher = stats.get("dispatcher", {})

    console.print(
        f"  [dim][status][/dim] "
        f"Sources: {thunder.get('sources_count', 0)} | "
        f"Discovered: {thunder.get('items_discovered', 0)} | "
        f"Scored: {dispatcher.get('total_scored', 0)} | "
        f"Failed: {dispatcher.get('total_failed', 0)} | "
        f"In-flight: {dispatcher.get('in_flight', 0)} | "
        f"Queue: {dispatcher.get('queue_size', 0)}"
    )


def _print_monitor_summary(summary: dict) -> None:
    """Print the daily monitor summary using Rich."""
    console.print()
    console.print("━" * 60)
    console.print("  [bold]Daily Summary[/bold]")
    console.print("━" * 60)
    console.print()
    console.print(f"  Total scored:   {summary['total_scored']}")
    console.print(f"  Total failed:   {summary['total_failed']}")
    console.print(f"  Average score:  {summary['average_score']:.1f}")

    top_labels = summary.get("top_labels", [])
    if top_labels:
        console.print(f"  Top labels:     {', '.join(top_labels)}")

    high_risk = summary.get("high_risk_items", [])
    if high_risk:
        console.print()
        console.print(f"  [bold red]High risk items ({len(high_risk)}):[/bold red]")
        for item in high_risk[:10]:
            title = item.get("title", "Unknown")
            score_val = item.get("score", 0)
            console.print(f"    - {title} (score: {score_val:.0f})")
    console.print()


async def _run_monitor(config_path: str) -> None:
    """Async entrypoint for the monitor service."""
    from src.monitor.service import MonitorService

    try:
        service = MonitorService.from_config_file(config_path)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return
    except Exception as e:
        console.print(f"[bold red]Failed to initialize monitor:[/bold red] {e}")
        return

    # Set up graceful shutdown
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        console.print("\n  [yellow]Shutting down gracefully...[/yellow]")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:  # pragma: no cover
            # Windows doesn't support add_signal_handler
            pass

    # Start the service
    await service.start()
    _print_monitor_banner(service.stats)

    # Print status every 30 seconds until stopped
    status_interval = 30  # seconds
    elapsed = 0.0
    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                break
            except asyncio.TimeoutError:
                elapsed += 1.0
                if elapsed >= status_interval:
                    _print_status_update(service.stats)
                    elapsed = 0.0
    except asyncio.CancelledError:
        pass

    # Graceful shutdown
    await service.stop()
    console.print()
    console.print("  [green]Monitor stopped.[/green] Final stats:")
    _print_status_update(service.stats)

    # Print daily summary if available
    summary = service.last_summary
    if summary and summary.get("total_scored", 0) > 0:
        _print_monitor_summary(summary)

    console.print()


@monitor_app.command("start")
def monitor_start(
    config: str = typer.Option(
        "config.yaml", "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Start the real-time content monitor (runs until Ctrl+C)."""
    try:
        # pragma: no cover -- long-running event loop that blocks until signal;
        # cannot be exercised meaningfully in unit tests.
        asyncio.run(_run_monitor(config))  # pragma: no cover
    except KeyboardInterrupt:
        console.print("\n  [yellow]Interrupted.[/yellow]")


@monitor_app.command("add-source")
def monitor_add_source(
    name: str = typer.Option(..., "--name", help="Source name (e.g. 'tech-blog')"),
    url: str = typer.Option(..., "--url", help="Source URL (RSS feed or webhook endpoint)"),
    source_type: str = typer.Option("rss", "--type", "-t", help="Source type: rss or webhook"),
    interval: int = typer.Option(300, "--interval", "-i", help="Poll interval in seconds"),
    priority: int = typer.Option(5, "--priority", "-p", help="Priority 1-10 (1=highest)"),
    config: str = typer.Option(
        "config.yaml", "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Add a content source to the monitor configuration."""
    import yaml

    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[bold red]Error:[/bold red] Config file not found: {config}")
        raise typer.Exit(code=1)

    # Validate source type
    if source_type not in ("rss", "webhook"):
        console.print(f"[bold red]Error:[/bold red] Type must be 'rss' or 'webhook', got '{source_type}'")
        raise typer.Exit(code=1)

    # Validate priority
    if not (1 <= priority <= 10):
        console.print("[bold red]Error:[/bold red] Priority must be between 1 and 10")
        raise typer.Exit(code=1)

    # Read existing config
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    # Ensure thunder.sources exists
    if "thunder" not in cfg:
        cfg["thunder"] = {"enabled": True, "sources": []}
    if "sources" not in cfg["thunder"]:
        cfg["thunder"]["sources"] = []

    # Check for duplicate name
    existing_names = [s["name"] for s in cfg["thunder"]["sources"]]
    if name in existing_names:
        console.print(f"[bold red]Error:[/bold red] Source '{name}' already exists in config")
        raise typer.Exit(code=1)

    # Add new source
    new_source = {
        "name": name,
        "type": source_type,
        "url": url,
        "poll_interval_seconds": interval,
        "priority": priority,
        "enabled": True,
    }
    cfg["thunder"]["sources"].append(new_source)

    # Write back
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    console.print(f"[green]Added source '{name}' ({source_type}) — {url}[/green]")
    console.print(f"  Poll interval: {interval}s | Priority: {priority}")


@monitor_app.command("stats")
def monitor_stats(
    config: str = typer.Option(
        "config.yaml", "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Show monitoring configuration and source info."""
    import yaml

    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[bold red]Error:[/bold red] Config file not found: {config}")
        raise typer.Exit(code=1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    thunder_cfg = cfg.get("thunder", {})
    dispatcher_cfg = cfg.get("dispatcher", {})
    sources = thunder_cfg.get("sources", [])

    console.print()
    console.print("[bold]Monitor Configuration[/bold]")
    console.print("━" * 50)
    console.print()

    # Thunder status
    enabled = thunder_cfg.get("enabled", False)
    status_str = "[green]enabled[/green]" if enabled else "[red]disabled[/red]"
    console.print(f"  Thunder: {status_str}")
    console.print(f"  Max concurrency: {dispatcher_cfg.get('max_in_flight', 3)}")
    console.print(
        f"  Retry policy: {dispatcher_cfg.get('retry', {}).get('max_attempts', 3)} attempts, "
        f"base delay {dispatcher_cfg.get('retry', {}).get('base_delay_seconds', 2.0)}s"
    )
    console.print()

    # Sources table
    if not sources:
        console.print("  [dim]No sources configured.[/dim]")
    else:
        table = Table(title="Configured Sources", show_lines=False)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("URL", max_width=40, overflow="ellipsis")
        table.add_column("Interval", justify="right")
        table.add_column("Priority", justify="center")
        table.add_column("Status")

        for src in sources:
            status = "[green]on[/green]" if src.get("enabled", True) else "[red]off[/red]"
            interval_str = f"{src.get('poll_interval_seconds', 300)}s"
            table.add_row(
                src.get("name", "?"),
                src.get("type", "?"),
                src.get("url", "?"),
                interval_str,
                str(src.get("priority", 5)),
                status,
            )

        console.print(table)

    # Webhook info
    webhook_cfg = thunder_cfg.get("webhook", {})
    if webhook_cfg.get("enabled", False):
        console.print()
        console.print(
            f"  Webhook endpoint: [cyan]{webhook_cfg.get('path', '/webhook/content')}[/cyan]"
        )

    console.print()


if __name__ == "__main__":
    app()
