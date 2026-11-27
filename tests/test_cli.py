"""CLI-level tests that never touch the network."""
from __future__ import annotations

import json

import pytest

from sklavenitis_cli import cli


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "sklavenitis-cli" in capsys.readouterr().out


def test_add_without_address_is_a_json_error(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    code = cli.main(["cart", "add", "1709870", "--json"])
    assert code == 2
    payload = json.loads(capsys.readouterr().err)
    assert "address" in payload["error"]


def test_zero_quantity_is_a_usage_error(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SKLAVENITIS_CONFIG_DIR", str(tmp_path))
    code = cli.main(["cart", "set", "1709870", "-q", "0", "--json"])
    assert code == 2
    assert "remove" in json.loads(capsys.readouterr().err)["error"]
