# Junk Detector Comparison Framework

## Junk Detector Rules Engine Performance

Evaluated on 500 labeled samples.

| Metric | Value |
|--------|-------|
| Precision | 0.9900 |
| Recall | 0.7960 |
| F1 Score | 0.8825 |
| Accuracy | 0.8940 |
| Avg latency | 0.14 ms/sample |
| Total time | 0.07s for 500 samples |
| Cost | $0 (no API calls) |

## What Junk Detector Covers

### Dimensions

| Dimension | Detection Method |
|-----------|-----------------|
| Scam probability | Keyword matching, regex patterns, combo rules |
| Clickbait detection | Emotional trigger phrases, exaggeration patterns |
| Advertorial probability | Product promotion keywords, affiliate patterns |
| Emotional manipulation | Anxiety/urgency phrases, fear-based language |
| AI-generated content | Hedging phrases, formulaic structure detection |

### Technical Approach

- **Keyword matching**: Curated Chinese-language keyword lists per dimension
- **Regex patterns**: Complex pattern matching for phone numbers, URLs, monetary claims
- **Combo rules**: Multi-signal rules requiring multiple indicators to fire
- **Platform-specific**: WeChat, Xiaohongshu, Zhihu, Douyin platform profiles
- **Custom rules**: User-defined YAML rules for domain-specific detection

## Comparison with Other Approaches

| Approach | Accuracy | Latency | Cost | Setup Complexity |
|----------|----------|---------|------|-----------------|
| **Junk Detector (rules)** | 89.4% | <1ms/sample | $0 | Low (pip install) |
| Pure keyword filters | ~50-60% | <1ms/sample | $0 | Low |
| ML text classifiers (BERT) | ~85-92% | 10-50ms/sample | $0 (after training) | High (training data, GPU) |
| LLM-based scoring | ~90-95% | 500-3000ms/sample | $0.001-0.01/sample | Medium (API key) |
| Commercial APIs | ~88-94% | 100-500ms/sample | $0.005-0.05/sample | Low (API key) |

## Detailed Approach Comparison

### Pure Keyword Filters

- **Pros**: Fastest possible, zero cost, easy to understand
- **Cons**: High false positive rate, no context understanding, easily evaded
- **vs Junk Detector**: Junk Detector uses combo rules and confidence scoring
  to reduce false positives while maintaining the speed advantage

### ML Text Classifiers (BERT, FastText)

- **Pros**: High accuracy, learns subtle patterns, generalizes well
- **Cons**: Requires labeled training data, GPU for training, model serving infra
- **vs Junk Detector**: Junk Detector requires zero training data and runs
  without ML infrastructure. Can be combined with ML as a pre-filter.

### LLM-based Scoring (GPT-4, Claude, DeepSeek)

- **Pros**: Highest accuracy, understands context and nuance, no training needed
- **Cons**: Expensive at scale, high latency, rate limits, requires API key
- **vs Junk Detector**: Junk Detector can pre-filter obvious cases at zero cost,
  sending only ambiguous content to LLM. This hybrid approach reduces costs by 60-80%.

### Commercial Content Moderation APIs

- **Pros**: Managed service, high accuracy, multi-language
- **Cons**: Per-request cost, vendor lock-in, requires authentication, privacy concerns
- **vs Junk Detector**: Junk Detector is self-hosted, free, and focused on Chinese content.
  No data leaves your infrastructure.

## Hybrid Strategy (Recommended)

For production use, combine approaches:

1. **Layer 1 - Rules Engine** (junk-detector rules-only): Catches obvious junk at <1ms, $0
2. **Layer 2 - LLM Scoring** (junk-detector with API): Evaluates ambiguous content
3. **Layer 3 - Human Review**: Final check for edge cases

This layered approach optimizes for both accuracy and cost.

---

*Note: External API comparisons are theoretical estimates based on published benchmarks.
Actual performance varies by content type and language. Add external API testing
by implementing adapters in benchmark/adapters/ (requires authentication).*
