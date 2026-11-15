"""
FactCascade: a validated, three-stage sequential prompt chain
(extract -> analyze -> format) with retry-then-fallback-then-abort error
handling at every validation gate.

DISCLOSURE: ModelRouter.call() is a deterministic stand-in: instead of
sending a prompt to a provider, it looks up a scripted response for the
given (document, step, attempt) from a response bank. The scripted text is
written to look like what a real model would plausibly return for that
step, including a realistic malformed-JSON failure and a realistic
"parses fine but is still useless" failure, so the retry/fallback/abort
logic is exercised the same way it would be against a real API. This is
the single swap point: point it at a real provider call and nothing else
needs to change.
"""
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    value: object = None
    error: str = None


def _safe_parse_json(raw_text: str):
    try:
        return True, json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        return False, str(exc)


def validate_facts(raw_text: str) -> ValidationResult:
    ok, parsed = _safe_parse_json(raw_text)
    if not ok:
        return ValidationResult(False, error=f"extraction output did not parse: {parsed}")
    if not isinstance(parsed, list) or len(parsed) == 0:
        return ValidationResult(False, error="extraction output is not a non-empty JSON list")
    if not all(isinstance(f, str) and f.strip() for f in parsed):
        return ValidationResult(False, error="extraction output contains an empty or non-string fact")
    return ValidationResult(True, value=parsed)


def validate_risks(raw_text: str) -> ValidationResult:
    ok, parsed = _safe_parse_json(raw_text)
    if not ok:
        return ValidationResult(False, error=f"analysis output did not parse: {parsed}")
    if not isinstance(parsed, list) or len(parsed) == 0:
        return ValidationResult(False, error="analysis output is not a non-empty JSON list of risks")
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            return ValidationResult(False, error=f"risk #{i} is not an object")
        if not isinstance(item.get("risk"), str) or not item["risk"].strip():
            return ValidationResult(False, error=f"risk #{i} is missing a non-empty 'risk' field")
        if item.get("severity") not in {"LOW", "MEDIUM", "HIGH"}:
            return ValidationResult(False, error=f"risk #{i} has severity '{item.get('severity')}', not LOW/MEDIUM/HIGH")
    return ValidationResult(True, value=parsed)


def validate_report(report_text) -> ValidationResult:
    if not isinstance(report_text, str) or not report_text.strip():
        return ValidationResult(False, error="formatted report is empty")
    if len(report_text.split()) < 15:
        return ValidationResult(False, error="formatted report is too short to be useful")
    return ValidationResult(True, value=report_text.strip())


@dataclass(frozen=True)
class ScriptedResponse:
    text: str


class ModelRouter:
    """Deterministic stand-in model backend. See module docstring."""

    def __init__(self, response_bank: dict):
        # response_bank[(document, step, model)] -> list[str], one per attempt (1-indexed)
        self._bank = response_bank

    def call(self, document: str, step: str, model: str, attempt: int) -> str:
        key = (document, step, model)
        attempts = self._bank.get(key, [])
        idx = min(attempt - 1, len(attempts) - 1) if attempts else None
        if idx is None:
            raise KeyError(f"no scripted response for {key}")
        return attempts[idx]


MAX_ATTEMPTS_PER_MODEL = 2


def _run_stage(router, document, step, primary_model, validate_fn, fallback_model=None, log=None):
    log = log if log is not None else []
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
        raw = router.call(document, step, primary_model, attempt)
        result = validate_fn(raw)
        log.append(f"  [{'OK ' if result.ok else 'FAIL'}] step={step:<8} model={primary_model:<16} attempt=primary attempt {attempt}"
                   + ("" if result.ok else f"\n         -> {result.error}"))
        if result.ok:
            return result
        last_error = result.error
    if fallback_model:
        raw = router.call(document, step, fallback_model, 1)
        result = validate_fn(raw)
        log.append(f"  [{'OK ' if result.ok else 'FAIL'}] step={step:<8} model={fallback_model:<16} attempt=fallback"
                   + ("" if result.ok else f"\n         -> {result.error}"))
        if result.ok:
            return result
        last_error = result.error
    return ValidationResult(False, error=f"step '{step}' aborted after {MAX_ATTEMPTS_PER_MODEL} attempt(s)"
                             f" on '{primary_model}'" + (f" and 1 attempt on fallback '{fallback_model}'" if fallback_model else "")
                             + f": {last_error}")


@dataclass
class ChainResult:
    facts: list = None
    risks: list = None
    report: str = None
    error: str = None
    log: list = field(default_factory=list)

    @property
    def aborted(self) -> bool:
        return self.error is not None


def run_chain(router: ModelRouter, document: str) -> ChainResult:
    """Run extract -> analyze -> format with validation at every gate.
    extract/format use 'cascade-lite'; analyze uses 'cascade-reason' with a
    capable (not downgraded) fallback 'cascade-reason-alt'."""
    log = []
    result = ChainResult(log=log)

    extract_result = _run_stage(router, document, "extract", "cascade-lite", validate_facts, log=log)
    if not extract_result.ok:
        result.error = extract_result.error
        return result
    result.facts = extract_result.value

    analyze_result = _run_stage(router, document, "analyze", "cascade-reason", validate_risks,
                                 fallback_model="cascade-reason-alt", log=log)
    if not analyze_result.ok:
        result.error = analyze_result.error
        return result  # facts survive on the result even though the chain aborts
    result.risks = analyze_result.value

    format_result = _run_stage(router, document, "format", "cascade-lite", validate_report, log=log)
    if not format_result.ok:
        result.error = format_result.error
        return result
    result.report = format_result.value
    return result
