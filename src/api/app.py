from fastapi import FastAPI

app = FastAPI(
    title="Junk Detector",
    description="AI content quality scorer — detect junk content with LLM-as-Judge + rules",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
