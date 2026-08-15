from echoscene_core import redact_trace


def test_redacts_secrets_and_personal_identifiers() -> None:
    trace = {
        "authorization": "Bearer private-token",
        "nested": {
            "api_key": "secret-key",
            "message": "Reach me at learner@example.com or +86 138 0013 8000",
        },
    }

    redacted = redact_trace(trace)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert "learner@example.com" not in redacted["nested"]["message"]
    assert "138 0013 8000" not in redacted["nested"]["message"]


def test_preserves_non_sensitive_trace_data() -> None:
    trace = {"state": "listening", "latency_ms": 842, "terms": ["tool call"]}
    assert redact_trace(trace) == trace

