from __future__ import annotations

from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parent.parent / "compose.yaml"


def test_compose_file_exists() -> None:
    assert COMPOSE_FILE.is_file()


def test_compose_declares_required_services() -> None:
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "db:" in content
    assert "api:" in content
    assert "web:" in content
    assert "postgres:16-alpine" in content
    assert "enso_pgdata" in content


def test_compose_security_and_healthchecks() -> None:
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "no-new-privileges:true" in content
    assert "pg_isready" in content
    assert "/health/ready" in content
    assert "condition: service_healthy" in content
