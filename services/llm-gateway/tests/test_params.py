from app.params import normalize_params


def test_temperature_removed():
    payload = {"model": "m", "messages": [], "temperature": 0.7}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert "temperature" not in result
    assert "dropped:temperature" in notes


def test_top_p_removed():
    payload = {"model": "m", "messages": [], "top_p": 0.9}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert "top_p" not in result
    assert "dropped:top_p" in notes


def test_max_tokens_renamed():
    payload = {"model": "m", "messages": [], "max_tokens": 512}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert "max_tokens" not in result
    assert result["max_completion_tokens"] == 512
    assert "renamed:max_tokens->max_completion_tokens" in notes


def test_max_tokens_dropped_when_completion_already_set():
    payload = {"model": "m", "messages": [], "max_tokens": 512, "max_completion_tokens": 256}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert result["max_completion_tokens"] == 256
    assert "max_tokens" not in result
    assert any(n.startswith("dropped:max_tokens") for n in notes)


def test_reasoning_effort_injected_when_missing():
    payload = {"model": "m", "messages": []}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert result["reasoning_effort"] == "low"
    assert "injected:reasoning_effort=low" in notes


def test_reasoning_effort_preserved_when_present():
    payload = {"model": "m", "messages": [], "reasoning_effort": "high"}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert result["reasoning_effort"] == "high"
    assert not any(n.startswith("injected:reasoning_effort") for n in notes)


def test_unknown_params_pass_through():
    payload = {"model": "m", "messages": [], "response_format": {"type": "json_object"}}
    result, _ = normalize_params(payload, default_reasoning_effort="low")
    assert result["response_format"] == {"type": "json_object"}


def test_input_payload_not_mutated():
    payload = {"model": "m", "messages": [], "temperature": 0.7}
    normalize_params(payload, default_reasoning_effort="low")
    assert payload["temperature"] == 0.7


def test_clean_payload_produces_no_notes_except_injection():
    payload = {"model": "m", "messages": [], "reasoning_effort": "low"}
    _, notes = normalize_params(payload, default_reasoning_effort="low")
    assert notes == []
