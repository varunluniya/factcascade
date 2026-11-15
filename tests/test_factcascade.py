import json
import pytest
from factcascade.core import validate_facts, validate_risks, validate_report, ModelRouter, run_chain


def test_validate_facts_happy_path():
    r = validate_facts(json.dumps(["fact one", "fact two"]))
    assert r.ok is True
    assert r.value == ["fact one", "fact two"]


def test_validate_facts_rejects_malformed_json():
    r = validate_facts("{not json")
    assert r.ok is False
    assert "did not parse" in r.error


def test_validate_facts_rejects_empty_list():
    r = validate_facts(json.dumps([]))
    assert r.ok is False


def test_validate_facts_rejects_non_string_fact():
    r = validate_facts(json.dumps(["ok", 123]))
    assert r.ok is False


def test_validate_risks_happy_path():
    r = validate_risks(json.dumps([{"risk": "x", "severity": "HIGH"}]))
    assert r.ok is True


def test_validate_risks_rejects_bad_severity():
    r = validate_risks(json.dumps([{"risk": "x", "severity": "URGENT"}]))
    assert r.ok is False
    assert "LOW/MEDIUM/HIGH" in r.error


def test_validate_risks_rejects_missing_risk_field():
    r = validate_risks(json.dumps([{"severity": "HIGH"}]))
    assert r.ok is False


def test_validate_report_rejects_empty():
    assert validate_report("").ok is False


def test_validate_report_rejects_too_short():
    assert validate_report("too short").ok is False


def test_validate_report_accepts_long_enough_prose():
    assert validate_report(" ".join(["word"] * 20)).ok is True


def test_chain_happy_path_all_three_stages_succeed():
    bank = {
        ("doc1", "extract", "cascade-lite"): [json.dumps(["fact a", "fact b"])],
        ("doc1", "analyze", "cascade-reason"): [json.dumps([{"risk": "r1", "severity": "HIGH"}])],
        ("doc1", "format", "cascade-lite"): [" ".join(["word"] * 20)],
    }
    result = run_chain(ModelRouter(bank), "doc1")
    assert not result.aborted
    assert result.facts == ["fact a", "fact b"]
    assert result.risks == [{"risk": "r1", "severity": "HIGH"}]
    assert result.report is not None


def test_chain_retries_then_falls_back_then_aborts_on_analyze_failure():
    bank = {
        ("doc2", "extract", "cascade-lite"): [json.dumps(["fact a"])],
        ("doc2", "analyze", "cascade-reason"): ["{bad json 1", "{bad json 2"],
        ("doc2", "analyze", "cascade-reason-alt"): [json.dumps([])],  # valid JSON, empty -- still fails content validation
        ("doc2", "format", "cascade-lite"): [" ".join(["word"] * 20)],
    }
    result = run_chain(ModelRouter(bank), "doc2")
    assert result.aborted
    assert "analyze" in result.error
    assert result.facts == ["fact a"]  # step 1 output retained for debugging
    assert result.risks is None
    assert result.report is None  # format never runs


def test_chain_log_shows_retry_then_fallback_then_abort():
    bank = {
        ("doc3", "extract", "cascade-lite"): [json.dumps(["fact a"])],
        ("doc3", "analyze", "cascade-reason"): ["{bad 1", "{bad 2"],
        ("doc3", "analyze", "cascade-reason-alt"): [json.dumps([])],
        ("doc3", "format", "cascade-lite"): [" ".join(["word"] * 20)],
    }
    result = run_chain(ModelRouter(bank), "doc3")
    full_log = "\n".join(result.log)
    assert "cascade-reason-alt" in full_log
    assert full_log.count("FAIL") == 3  # 2 primary attempts + 1 fallback attempt


def test_chain_aborts_cleanly_if_extract_fails_with_no_fallback():
    bank = {
        ("doc4", "extract", "cascade-lite"): ["not json", "still not json"],
    }
    result = run_chain(ModelRouter(bank), "doc4")
    assert result.aborted
    assert "extract" in result.error
    assert result.facts is None
