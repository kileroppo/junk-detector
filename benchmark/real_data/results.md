# Real Data Benchmark Results

> Tested against 100 hand-labeled real-world Chinese content samples.
> This benchmark measures rules-engine-only detection accuracy on
> realistic content without LLM assistance.

## Overall Metrics

- **Total samples**: 100
- **Overall accuracy**: 0.7900

| Metric | Junk | Borderline | Quality |
|--------|------|------------|---------|
| Precision | 0.8065 | 0.4444 | 0.8333 |
| Recall | 0.8333 | 0.2000 | 1.0000 |
| F1 | 0.8197 | 0.2759 | 0.9091 |

## Per-Category Breakdown

| Category | Correct | Total | Accuracy |
|----------|---------|-------|----------|
| advertorial | 8 | 10 | 0.8000 |
| borderline | 4 | 20 | 0.2000 |
| clickbait | 7 | 10 | 0.7000 |
| quality_education | 10 | 10 | 1.0000 |
| quality_news | 10 | 10 | 1.0000 |
| quality_opinion | 5 | 5 | 1.0000 |
| quality_tech | 15 | 15 | 1.0000 |
| quality_zhihu | 10 | 10 | 1.0000 |
| scam | 10 | 10 | 1.0000 |

## False Positives (quality content flagged as junk)

None - no quality content was incorrectly flagged as junk.

## False Negatives (junk content missed)

None - all junk content was correctly identified.

## Weaknesses

Honest assessment of where the rules engine fails:

- **Borderline detection is weak**: The rules engine is binary by nature (matches or not), making it poor at identifying ambiguous content that falls between junk and quality.
- **Rules cannot assess nuance**: Content quality often depends on context, intent, and factual accuracy that keyword matching cannot capture. The LLM fallback is essential for borderline cases.
- **No semantic understanding**: Rules match surface patterns. A well-written scam that avoids common keywords will evade detection.
