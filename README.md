# FactCascade

A validated, three-stage sequential prompt chain — extract → analyze →
format — with retry-then-fallback-then-abort error handling at every
validation gate, and model mixing: a cheap model for the two mechanical
steps, a more capable model (with a capable, not downgraded, fallback) for
the one step that needs genuine judgment.

**Disclosure:** `ModelRouter.call()` is a deterministic stand-in. Instead
of calling a provider, it looks up a scripted response for a given
(document, step, model, attempt) from a response bank, written to mirror
real failure shapes — malformed JSON, and syntactically-valid-but-empty
output. It's the single swap point: point it at a real provider SDK and
nothing else (the chain, validators, or retry logic) needs to change.

## Usage

```bash
pip install -e .
python -m factcascade.cli
```

Demonstrates two documents: a happy path where all three stages succeed,
and a deliberately induced failure where `analyze` fails twice on the
primary model (two different failure shapes) and once on the fallback,
then the whole chain aborts — with `facts` from step 1 still retained for
debugging, and `format` never running on a broken intermediate result.

## Why decomposition over one big prompt

Validating between every step means a broken risk analysis can never be
silently formatted into a polished-looking executive summary — the chain
aborts with a stage-attributed reason instead of producing a fluent,
confident, but fabricated report.

## Tests

```bash
pytest -v
```

14/14 passing.

## License

MIT
