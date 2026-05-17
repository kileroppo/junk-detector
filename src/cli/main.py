import typer

app = typer.Typer(
    name="junk-detector",
    help="AI content quality scorer — detect junk content with LLM-as-Judge + rules.",
)


@app.command()
def score(
    text: str = typer.Option(None, "--text", "-t", help="Text content to score"),
    url: str = typer.Option(None, "--url", "-u", help="URL to fetch and score"),
    file: str = typer.Option(None, "--file", "-f", help="File path to read and score"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Score content quality across 9 dimensions."""
    typer.echo("🚧 Scoring not yet implemented")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    min_score: int = typer.Option(None, "--min-score", help="Filter by minimum score"),
    label: str = typer.Option(None, "--label", help="Filter by label"),
):
    """View scoring history."""
    typer.echo("🚧 History not yet implemented")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
):
    """Start the API server."""
    import uvicorn

    uvicorn.run("src.api.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
