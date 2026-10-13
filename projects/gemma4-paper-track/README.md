# Gemma 4 Developer Agent: Paper Track

This is a research entry for Kaggle's [Gemma 4 Developer Agent Paper Track](https://www.kaggle.com/competitions/gemma-4-developer-agent-paper). It studies how much a local coding agent should think, across thinking budgets and model sizes, on consumer GPUs.

[PLAN.md](PLAN.md) has the research questions, compute budget and timeline.

## Layout

- `thinkbudget/budget.py`: budget forcing for llama.cpp's `llama-server`. It caps thinking at N tokens, then forces the model to answer.
- `thinkbudget/metrics.py`: trajectory metrics (malformed share, repeat share, conditional malformed rate, thinking-token share) and paired significance tests.
- `notebooks/01_feasibility_kaggle.py`: the day-1 Kaggle spike. It measures speed and memory for each Gemma 4 size on 2× T4, and finds the thinking markers.

## Tests

```bash
pip install pytest
pytest
```

The code needs nothing beyond the standard library. Competition data is not committed here, because the rules forbid redistributing it.
