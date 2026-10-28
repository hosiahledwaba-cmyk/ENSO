from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrastructure.local.devctl import (
    DevctlError,
    _safe_rmtree,
    build_env,
    build_spec,
    clear_state,
    parse_env_file,
    read_port,
    read_state,
    render_make_help,
    running_pid,
    select_services,
    tail,
    write_state,
)


def test_parse_env_file_missing(tmp_path: Path) -> None:
    assert parse_env_file(tmp_path / "nonexistent.env") == {}


def test_parse_env_file_valid(tmp_path: Path) -> None:
    content = """
    # Comment line
    ENSO_ENV=test
    export API_PORT="8000"
    SINGLE_QUOTES='hello'
    EMPTY=
    """
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    parsed = parse_env_file(env_file)
    assert parsed["ENSO_ENV"] == "test"
    assert parsed["API_PORT"] == "8000"
    assert parsed["SINGLE_QUOTES"] == "hello"
    assert parsed["EMPTY"] == ""


def test_parse_env_file_invalid(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("invalid line without equals", encoding="utf-8")
    with pytest.raises(DevctlError, match="expected KEY=VALUE"):
        parse_env_file(env_file)


def test_build_env_overrides(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENSO_ENV=from_file\nENSO_API_PORT=9000", encoding="utf-8")
    base_env = {"ENSO_ENV": "from_process"}

    merged = build_env(base=base_env, env_file=env_file, debug=False)
    assert merged["ENSO_ENV"] == "from_process"
    assert merged["ENSO_API_PORT"] == "9000"
    assert merged["PYTHONUNBUFFERED"] == "1"

    debug_merged = build_env(base=base_env, env_file=env_file, debug=True)
    assert debug_merged["ENSO_LOG_LEVEL"] == "DEBUG"


def test_read_port() -> None:
    assert read_port({"PORT": "3000"}, "PORT", 8000) == 3000
    assert read_port({}, "PORT", 8000) == 8000

    with pytest.raises(DevctlError, match="must be an integer"):
        read_port({"PORT": "abc"}, "PORT", 8000)

    with pytest.raises(DevctlError, match="between 1 and 65535"):
        read_port({"PORT": "70000"}, "PORT", 8000)

    with pytest.raises(DevctlError, match="between 1 and 65535"):
        read_port({"PORT": "0"}, "PORT", 8000)


def test_select_services() -> None:
    assert select_services("all") == ["api", "web"]
    assert select_services("api") == ["api"]
    assert select_services("web") == ["web"]

    with pytest.raises(DevctlError, match="Unknown service 'invalid'"):
        select_services("invalid")


def test_build_spec_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "infrastructure.local.devctl.venv_python",
        lambda: tmp_path / "python.exe",
    )
    (tmp_path / "python.exe").touch()

    spec = build_spec("api", {"ENSO_API_PORT": "8100"}, debug=True)
    assert spec.name == "api"
    assert spec.port == 8100
    assert "--reload" in spec.command
    assert "debug" in spec.command
    assert spec.ready_url == "http://127.0.0.1:8100/health"


def test_build_spec_web(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("infrastructure.local.devctl.shutil.which", lambda cmd: "/usr/bin/node")
    vite_bin = tmp_path / "vite.js"
    vite_bin.touch()
    monkeypatch.setattr(
        "infrastructure.local.devctl.WEB_DIR",
        tmp_path,
    )
    (tmp_path / "node_modules" / "vite" / "bin").mkdir(parents=True)
    (tmp_path / "node_modules" / "vite" / "bin" / "vite.js").touch()

    spec = build_spec("web", {"ENSO_WEB_DEV_PORT": "5190"}, debug=False)
    assert spec.name == "web"
    assert spec.port == 5190
    assert "--strictPort" in spec.command


def test_state_lifecycle(tmp_path: Path) -> None:
    rdir = tmp_path / "run"
    assert read_state(rdir, "api") is None

    sample_state: dict[str, Any] = {
        "pid": 99999999,
        "port": 8000,
        "url": "http://localhost:8000",
        "log": str(rdir / "api.log"),
    }
    write_state(rdir, "api", sample_state)
    assert read_state(rdir, "api") == sample_state

    # PID 99999999 is dead, so running_pid should clear state and return None
    assert running_pid(rdir, "api") is None
    assert read_state(rdir, "api") is None

    write_state(rdir, "web", sample_state)
    clear_state(rdir, "web")
    assert read_state(rdir, "web") is None


def test_tail(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    assert tail(log, 10) == []

    log.write_text("\n".join(f"line {i}" for i in range(20)), encoding="utf-8")
    assert tail(log, 5) == [f"line {i}" for i in range(15, 20)]
    assert len(tail(log, 50)) == 20


def test_safe_rmtree_blocks_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    with pytest.raises(DevctlError, match="Refusing to delete outside the repository"):
        _safe_rmtree(outside)


def test_render_make_help(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "##@ Development\nrun: ## Run in foreground\ndebug: ## Run in debug mode\n",
        encoding="utf-8",
    )
    rendered = render_make_help(makefile)
    assert "Development" in rendered
    assert "run" in rendered
    assert "Run in foreground" in rendered
    assert "debug" in rendered
