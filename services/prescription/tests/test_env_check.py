import pytest

from env_check import require_env


def test_passes_when_all_present(monkeypatch):
    monkeypatch.setenv("FOO_A", "1")
    monkeypatch.setenv("FOO_B", "2")
    require_env(["FOO_A", "FOO_B"])


def test_exits_when_missing(monkeypatch, capsys):
    monkeypatch.delenv("FOO_MISSING", raising=False)
    with pytest.raises(SystemExit) as exc:
        require_env(["FOO_MISSING"])
    assert exc.value.code == 1
    assert "FOO_MISSING" in capsys.readouterr().err


def test_exits_when_blank(monkeypatch, capsys):
    monkeypatch.setenv("FOO_BLANK", "   ")
    with pytest.raises(SystemExit) as exc:
        require_env(["FOO_BLANK"])
    assert exc.value.code == 1
    assert "FOO_BLANK" in capsys.readouterr().err
