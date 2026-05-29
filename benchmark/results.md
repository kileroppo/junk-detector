# Benchmark Results

> Note: This benchmark uses a synthetic dataset generated from the same keyword patterns
> used by the rules engine. These metrics measure rule coverage consistency, not real-world
> detection accuracy on unseen content. For production evaluation, use independently sourced
> labeled data.

## Overall Metrics

| Metric | Value |
|--------|-------|
| Precision | 0.9900 |
| Recall | 0.7960 |
| F1 Score | 0.8825 |

## Confusion Matrix

| | Predicted Junk | Predicted Quality |
|---|---|---|
| Actual Junk | 199 | 51 |
| Actual Quality | 2 | 248 |

## Per-Category Recall (Junk)

| Category | TP | FN | Recall |
|----------|----|----|--------|
| scam | 50 | 0 | 1.0000 |
| clickbait | 48 | 2 | 0.9600 |
| advertorial | 50 | 0 | 1.0000 |
| emotional_manipulation | 50 | 0 | 1.0000 |
| ai_slop | 1 | 49 | 0.0200 |

## Per-Category False Positive Rate (Quality)

| Category | FP | TN | FP Rate |
|----------|----|----|---------|
| news | 0 | 65 | 0.0000 |
| tech_blog | 0 | 65 | 0.0000 |
| educational | 0 | 60 | 0.0000 |
| opinion | 2 | 58 | 0.0333 |
