# SemIf Phase 1: Sub-Millisecond Semantic Decision Engine & Proxy

SemIf Phase 1 is a high-throughput, low-latency runtime decision engine designed to replace slow, non-deterministic generative LLM calls with exact, logprob-calibrated semantic classification.

## Overview

In autonomous agents, many expensive generative LLM calls are fundamentally classification or ranking problems:
- "Does this job description match candidate qualifications?" (Yes/No with confidence)
- "Is this LinkedIn contact relevant to message?" (Score 0–100)
- "Does this direct message thread already contain an outbound message?" (Yes/No)

SemIf uses logprob token readouts from local open-weights models (via LM Studio, MLX, vLLM, or Hugging Face Transformers) to return calibrated probabilities in sub-milliseconds without multi-token generation latency or JSON parsing errors.

## Key Components

- **`semif_phase1.core`**: Core mathematical formulation for semantic decision boundaries and logprob token aggregation.
- **`semif_phase1.direct`**: Direct model inference pipeline for fast candidate scoring.
- **`semif_phase1.jev_server`**: Drop-in choice server exposing `/v1/chat/completions` and `/v1/score` endpoints.
- **`semif_phase1.typesafe_proxy`**: Lightweight proxy translating standard OpenAI tool calls and schemas into zero-overhead logprob choices.
- **`semif_phase1.reranker`**: Cross-entropy candidate ranker for multi-choice selection.
- **`semif_phase1.server`**: Interactive visual web interface (`port 8080`) for testing prompt templates and calibrating decision thresholds.

## CLI Commands

```bash
# Run SemIf Interactive Test UI:
python3 -m semif_phase1.server --port 8080

# Run SemIf Drop-in Choice Server:
python3 -m semif_phase1.jev_server --port 8090

# Score a decision directly from terminal:
python3 -m semif_phase1.cli --prompt "Role: Senior UI Designer" --choice "Match"
```

## Running Tests

```bash
pytest tests
```
