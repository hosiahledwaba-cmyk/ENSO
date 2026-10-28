#!/usr/bin/env python3
"""ENSO Shield local process manager (standard library only).

Used by the root Makefile to run and manage the API and web applications:

* ``run``       foreground dev mode (keeps the terminal, prefixed output, Ctrl+C stops all)
* ``start``     background mode (detached, logs to files, PID state in the run dir)
* ``stop``      stop background services cleanly
* ``restart``   restart background services
* ``status``    show status, PIDs, URLs, and real HTTP health
* ``logs``      show/tail logs of background services
* ``health``    HTTP health check of api and web
* ``install``   install virtualenv and node dependencies
* ``test``      run pytest and vitest
* ``lint``      run ruff check and eslint
* ``format``    run ruff format
* ``typecheck`` run mypy and tsc -b
* ``check``     run all static checks and tests (lint, typecheck, test)
* ``build``     build web production assets
* ``clean``     remove caches and build output (``--all`` also removes deps)
* ``make-help`` render ``make help`` from ``##`` comments in the Makefile
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "services" / "api"
WEB_DIR = REPO_ROOT / "apps" / "web"
IS_WINDOWS = os.name == "nt"
SERVICES: tuple[str, ...] = ("api", "web")
DEFAULT_API_PORT = 8000
DEFAULT_WEB_DEV_PORT = 5173
DEFAULT_DOCKER_WEB_PORT = 8080
READY_TIMEOUT_S = 45.0
STOP_TIMEOUT_S = 5.0

_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COLOURS = {"api": "\033[36m", "web": "\033[35m"}
_RESET = "\033[0m"


class DevctlError(Exception):
    """User-facing error; printed without a traceback."""


# --------------------------------------------------------------------------- config


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple dotenv file: ``KEY=VALUE`` lines, ``#`` comments, optional quotes."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _ENV_KEY.match(key):
            raise DevctlError(f"{path}:{lineno}: expected KEY=VALUE")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def build_env(
    base: dict[str, str] | None = None, env_file: Path | None = None, *, debug: bool = False
) -> dict[str, str]:
    """Merge ``.env`` values under the process environment (process env wins)."""
    env = parse_env_file(env_file if env_file is not None else REPO_ROOT / ".env")
    env.update(base if base is not None else os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    if debug:
        env["ENSO_LOG_LEVEL"] = "DEBUG"
    return env


def read_port(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise DevctlError(f"{key} must be an integer, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise DevctlError(f"{key} must be between 1 and 65535, got {port}")
    return port


def run_dir(env: dict[str, str]) -> Path:
    raw = env.get("ENSO_RUN_DIR", "").strip()
    return Path(raw).resolve() if raw else REPO_ROOT / ".run"


# --------------------------------------------------------------------------- services


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    command: list[str]
    cwd: Path
    port: int
    ready_url: str
    public_url: str


def venv_python() -> Path:
    sub = ("Scripts", "python.exe") if IS_WINDOWS else ("bin", "python")
    return API_DIR.joinpath(".venv", *sub)


def find_npm() -> str:
    npm = shutil.which("npm.cmd") if IS_WINDOWS else shutil.which("npm")
    if npm is None:
        npm = shutil.which("npm")
    if npm is None:
        raise DevctlError("`npm` not found on PATH. Please install Node.js.")
    return npm


def build_spec(name: str, env: dict[str, str], *, debug: bool = False) -> ServiceSpec:
    if name == "api":
        port = read_port(env, "ENSO_API_PORT", DEFAULT_API_PORT)
        python = venv_python()
        if not python.is_file():
            raise DevctlError(f"API virtualenv not found at {python}. Run `make install`.")
        log_level = "debug" if debug else env.get("ENSO_LOG_LEVEL", "INFO").strip().lower()
        command = [
            str(python), "-m", "uvicorn", "enso_api.main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--reload", "--reload-dir", "src",
            "--log-level", log_level or "info",
        ]  # fmt: skip
        return ServiceSpec(
            name="api",
            command=command,
            cwd=API_DIR,
            port=port,
            ready_url=f"http://127.0.0.1:{port}/health",
            public_url=f"http://localhost:{port}",
        )
    if name == "web":
        port = read_port(env, "ENSO_WEB_DEV_PORT", DEFAULT_WEB_DEV_PORT)
        node = shutil.which("node")
        if node is None:
            raise DevctlError("Node.js (`node`) not found on PATH.")
        vite = WEB_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite.is_file():
            raise DevctlError(f"Vite not found at {vite}. Run `make install`.")
        command = [node, str(vite), "--host", "127.0.0.1", "--port", str(port), "--strictPort"]
        return ServiceSpec(
            name="web",
            command=command,
            cwd=WEB_DIR,
            port=port,
            ready_url=f"http://127.0.0.1:{port}/",
            public_url=f"http://localhost:{port}",
        )
    raise DevctlError(f"Unknown service {name!r}; expected one of {', '.join(SERVICES)}")


def select_services(target: str) -> list[str]:
    if target == "all":
        return list(SERVICES)
    if target not in SERVICES:
        raise DevctlError(f"Unknown service {target!r}; expected all, {', '.join(SERVICES)}")
    return [target]


# --------------------------------------------------------------------------- processes


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def http_ok(url: str, timeout: float = 2.0) -> bool:
    if not url.startswith(("http://", "https://")):
        raise DevctlError(f"Refusing non-http URL: {url!r}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return bool(resp.status == 200)
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kill_tree(pid: int) -> None:
    """Terminate a process and all of its children."""
    if not is_alive(pid):
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            return
        sender: Callable[[int], None]
        if pgid == pid:

            def sender(sig: int) -> None:
                os.killpg(pgid, sig)
        else:

            def sender(sig: int) -> None:
                os.kill(pid, sig)

        with contextlib.suppress(ProcessLookupError):
            sender(signal.SIGTERM)
        deadline = time.monotonic() + STOP_TIMEOUT_S
        while time.monotonic() < deadline and is_alive(pid):
            time.sleep(0.1)
        with contextlib.suppress(ProcessLookupError):
            if is_alive(pid):
                sender(signal.SIGKILL)
    deadline = time.monotonic() + STOP_TIMEOUT_S
    while time.monotonic() < deadline and is_alive(pid):
        time.sleep(0.1)


def detach_kwargs() -> dict[str, Any]:
    if IS_WINDOWS:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        return {"creationflags": flags}
    return {"start_new_session": True}


# --------------------------------------------------------------------------- state


def state_path(rdir: Path, name: str) -> Path:
    return rdir / f"{name}.json"


def log_path(rdir: Path, name: str) -> Path:
    return rdir / "logs" / f"{name}.log"


def read_state(rdir: Path, name: str) -> dict[str, Any] | None:
    path = state_path(rdir, name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("pid"), int) else None


def write_state(rdir: Path, name: str, data: dict[str, Any]) -> None:
    rdir.mkdir(parents=True, exist_ok=True)
    state_path(rdir, name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_state(rdir: Path, name: str) -> None:
    state_path(rdir, name).unlink(missing_ok=True)


def running_pid(rdir: Path, name: str) -> int | None:
    """PID of a live background service; removes stale state files."""
    state = read_state(rdir, name)
    if state is None:
        clear_state(rdir, name)
        return None
    pid = int(state["pid"])
    if is_alive(pid):
        return pid
    clear_state(rdir, name)
    return None


def tail(path: Path, lines: int) -> list[str]:
    if not path.is_file():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:] if lines > 0 else content


# --------------------------------------------------------------------------- commands


def wait_ready(spec: ServiceSpec, proc: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if http_ok(spec.ready_url, timeout=1.0):
            return True
        time.sleep(0.4)
    return False


def ensure_port_free(spec: ServiceSpec) -> None:
    if port_in_use(spec.port):
        raise DevctlError(
            f"Port {spec.port} for {spec.name} is already in use. "
            "Is it already running (`make status`) or is the Docker stack up (`make down`)?"
        )


def cmd_start(names: Sequence[str], env: dict[str, str], timeout: float) -> int:
    rdir = run_dir(env)
    specs = [build_spec(n, env) for n in names]
    for spec in specs:
        pid = running_pid(rdir, spec.name)
        if pid is not None:
            print(f"{spec.name}: already running (pid {pid}) at {spec.public_url}")
            continue
        ensure_port_free(spec)
        log = log_path(rdir, spec.name)
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists():
            log.replace(log.with_suffix(".prev.log"))
        with log.open("wb") as log_file:
            proc = subprocess.Popen(
                spec.command,
                cwd=spec.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **detach_kwargs(),
            )
        write_state(
            rdir,
            spec.name,
            {
                "pid": proc.pid,
                "port": spec.port,
                "url": spec.public_url,
                "log": str(log),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        )
        if not wait_ready(spec, proc, timeout):
            kill_tree(proc.pid)
            clear_state(rdir, spec.name)
            print(f"{spec.name}: failed to become ready. Last log lines ({log}):", file=sys.stderr)
            for line in tail(log, 30):
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"{spec.name}: running at {spec.public_url} (pid {proc.pid}, log {log})")
    return 0


def cmd_stop(names: Sequence[str], env: dict[str, str]) -> int:
    rdir = run_dir(env)
    for name in names:
        pid = running_pid(rdir, name)
        if pid is None:
            print(f"{name}: not running")
            continue
        kill_tree(pid)
        if is_alive(pid):
            print(f"{name}: failed to stop pid {pid}", file=sys.stderr)
            return 1
        clear_state(rdir, name)
        print(f"{name}: stopped (pid {pid})")
    return 0


def cmd_status(env: dict[str, str]) -> int:
    rdir = run_dir(env)
    print(f"{'SERVICE':<8} {'STATE':<9} {'PID':<8} {'HEALTHY':<8} URL")
    for name in SERVICES:
        state = read_state(rdir, name)
        pid = running_pid(rdir, name)
        if pid is None or state is None:
            print(f"{name:<8} {'stopped':<9} {'-':<8} {'-':<8} -")
            continue
        port = int(state.get("port", 0))
        ready = f"http://127.0.0.1:{port}/health" if name == "api" else f"http://127.0.0.1:{port}/"
        healthy = "yes" if http_ok(ready, timeout=1.0) else "no"
        print(f"{name:<8} {'running':<9} {pid:<8} {healthy:<8} {state.get('url', '-')}")
    return 0


def _emit(prefix: str, text: str, colour: bool) -> None:
    label = f"{_COLOURS.get(prefix, '')}[{prefix}]{_RESET}" if colour else f"[{prefix}]"
    sys.stdout.write(f"{label} {text}\n")
    sys.stdout.flush()


def cmd_logs(names: Sequence[str], env: dict[str, str], lines: int, follow: bool) -> int:
    rdir = run_dir(env)
    colour = sys.stdout.isatty()
    files = {name: log_path(rdir, name) for name in names}
    for name, path in files.items():
        if not path.is_file():
            _emit(name, f"(no log yet at {path})", colour)
            continue
        for line in tail(path, lines):
            _emit(name, line, colour)
    if not follow:
        return 0
    offsets = {n: (p.stat().st_size if p.is_file() else 0) for n, p in files.items()}
    try:
        while True:
            for name, path in files.items():
                if not path.is_file():
                    continue
                size = path.stat().st_size
                if size < offsets[name]:
                    offsets[name] = 0
                if size > offsets[name]:
                    with path.open("rb") as fh:
                        fh.seek(offsets[name])
                        chunk = fh.read()
                    offsets[name] += len(chunk)
                    for line in chunk.decode("utf-8", errors="replace").splitlines():
                        _emit(name, line, colour)
            time.sleep(0.3)
    except KeyboardInterrupt:
        return 0


def _pump(name: str, stream: IO[bytes], colour: bool) -> None:
    for raw in iter(stream.readline, b""):
        _emit(name, raw.decode("utf-8", errors="replace").rstrip("\r\n"), colour)


def cmd_run(names: Sequence[str], env: dict[str, str], debug: bool) -> int:
    specs = [build_spec(n, env, debug=debug) for n in names]
    rdir = run_dir(env)
    for spec in specs:
        if running_pid(rdir, spec.name) is not None:
            raise DevctlError(f"{spec.name} is running in the background; run `make stop` first.")
        ensure_port_free(spec)

    colour = sys.stdout.isatty()
    procs: dict[str, subprocess.Popen[bytes]] = {}
    exit_code = 0
    try:
        for spec in specs:
            proc = subprocess.Popen(
                spec.command,
                cwd=spec.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            procs[spec.name] = proc
            assert proc.stdout is not None
            threading.Thread(
                target=_pump, args=(spec.name, proc.stdout, colour), daemon=True
            ).start()
            _emit(spec.name, f"starting on {spec.public_url} (pid {proc.pid})", colour)
        mode = "debug" if debug else "normal"
        print(f"Foreground {mode} mode. Press Ctrl+C to stop.", flush=True)
        while True:
            for name, proc in procs.items():
                code = proc.poll()
                if code is not None:
                    _emit(name, f"exited with code {code}; stopping the others", colour)
                    exit_code = code or 1
                    raise StopIteration
            time.sleep(0.25)
    except (KeyboardInterrupt, StopIteration):
        pass
    finally:
        for proc in procs.values():
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=STOP_TIMEOUT_S)
            kill_tree(proc.pid)
        print("All foreground services stopped.", flush=True)
    return exit_code


def cmd_health(env: dict[str, str], target: str) -> int:
    api_port = read_port(env, "ENSO_API_PORT", DEFAULT_API_PORT)
    if target == "docker":
        web_port = read_port(env, "ENSO_WEB_PORT", DEFAULT_DOCKER_WEB_PORT)
    else:
        web_port = read_port(env, "ENSO_WEB_DEV_PORT", DEFAULT_WEB_DEV_PORT)
    checks = {
        "api": f"http://127.0.0.1:{api_port}/health",
        "web": f"http://127.0.0.1:{web_port}/",
    }
    failed = False
    for name, url in checks.items():
        ok = http_ok(url)
        failed |= not ok
        print(f"{name:<4} {'OK  ' if ok else 'FAIL'} {url}")
    return 1 if failed else 0


# --------------------------------------------------------------------------- tooling


def cmd_install(target: str) -> int:
    targets = select_services(target)
    if "api" in targets:
        vdir = API_DIR / ".venv"
        if not vdir.is_dir():
            print(f"Creating Python virtual environment at {vdir}...")
            subprocess.run([sys.executable, "-m", "venv", str(vdir)], check=True)
        py = venv_python()
        print(f"Upgrading pip in {vdir}...")
        subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        print("Installing API dependencies (editable mode with dev dependencies)...")
        subprocess.run([str(py), "-m", "pip", "install", "-e", ".[dev]"], cwd=API_DIR, check=True)
    if "web" in targets:
        npm = find_npm()
        print("Installing Web frontend dependencies via npm...")
        subprocess.run([npm, "install"], cwd=WEB_DIR, check=True)
    print("Dependencies successfully installed.")
    return 0


def cmd_test(target: str) -> int:
    targets = select_services(target)
    code = 0
    if "api" in targets:
        py = venv_python()
        if not py.is_file():
            raise DevctlError("API virtualenv not found. Run `make install`.")
        print("\n=== [api/ml] Running pytest ===")
        env = dict(os.environ)
        pythonpath = f"{REPO_ROOT}{os.pathsep}{API_DIR / 'src'}"
        if "PYTHONPATH" in env:
            pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
        env["PYTHONPATH"] = pythonpath
        res = subprocess.run(
            [str(py), "-m", "pytest", "-c", str(REPO_ROOT / "pyproject.toml")],
            cwd=REPO_ROOT,
            env=env,
        )
        if res.returncode != 0:
            code = res.returncode
    if "web" in targets:
        npm = find_npm()
        print("\n=== [web] Running vitest ===")
        res = subprocess.run([npm, "test"], cwd=WEB_DIR)
        if res.returncode != 0 and code == 0:
            code = res.returncode
    return code


def cmd_lint(target: str) -> int:
    targets = select_services(target)
    code = 0
    if "api" in targets:
        py = venv_python()
        if not py.is_file():
            raise DevctlError("API virtualenv not found. Run `make install`.")
        print("\n=== [api/ml] Running ruff check ===")
        res = subprocess.run([str(py), "-m", "ruff", "check", "."], cwd=REPO_ROOT)
        if res.returncode != 0:
            code = res.returncode
    if "web" in targets:
        npm = find_npm()
        print("\n=== [web] Running eslint ===")
        res = subprocess.run([npm, "run", "lint"], cwd=WEB_DIR)
        if res.returncode != 0 and code == 0:
            code = res.returncode
    return code


def cmd_format(target: str) -> int:
    targets = select_services(target)
    if "api" in targets:
        py = venv_python()
        if not py.is_file():
            raise DevctlError("API virtualenv not found. Run `make install`.")
        print("\n=== [api/ml] Running ruff format ===")
        res = subprocess.run([str(py), "-m", "ruff", "format", "."], cwd=REPO_ROOT)
        if res.returncode != 0:
            return res.returncode
    return 0


def cmd_typecheck(target: str) -> int:
    targets = select_services(target)
    code = 0
    if "api" in targets:
        py = venv_python()
        if not py.is_file():
            raise DevctlError("API virtualenv not found. Run `make install`.")
        print("\n=== [api/ml] Running mypy ===")
        res = subprocess.run(
            [str(py), "-m", "mypy", "--config-file", str(REPO_ROOT / "pyproject.toml")],
            cwd=REPO_ROOT,
        )
        if res.returncode != 0:
            code = res.returncode
    if "web" in targets:
        npm = find_npm()
        print("\n=== [web] Running tsc ===")
        res = subprocess.run([npm, "run", "typecheck"], cwd=WEB_DIR)
        if res.returncode != 0 and code == 0:
            code = res.returncode
    return code


def cmd_build(target: str) -> int:
    targets = select_services(target)
    if "web" in targets:
        npm = find_npm()
        print("\n=== [web] Building production bundle ===")
        res = subprocess.run([npm, "run", "build"], cwd=WEB_DIR)
        if res.returncode != 0:
            return res.returncode
    return 0


def cmd_check(target: str) -> int:
    print("--- Step 1/3: Linting ---")
    if code := cmd_lint(target):
        return code
    print("\n--- Step 2/3: Typechecking ---")
    if code := cmd_typecheck(target):
        return code
    print("\n--- Step 3/3: Automated Tests ---")
    if code := cmd_test(target):
        return code
    print("\nAll quality checks and tests passed successfully!")
    return 0


# --------------------------------------------------------------------------- clean


CLEAN_PATHS = (
    "services/api/.pytest_cache",
    "services/api/.mypy_cache",
    "services/api/.ruff_cache",
    "services/api/build",
    "apps/web/dist",
    "apps/web/node_modules/.tmp",
    "apps/web/node_modules/.vite",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)
DEPENDENCY_PATHS = ("services/api/.venv", "apps/web/node_modules")
_SKIP_DIRS = {".venv", "node_modules", ".git"}


def _on_rm_error(func: Callable[..., Any], path: str, _exc: BaseException) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _safe_rmtree(path: Path) -> bool:
    resolved = path.resolve()
    if not resolved.is_relative_to(REPO_ROOT) or resolved == REPO_ROOT:
        raise DevctlError(f"Refusing to delete outside the repository: {resolved}")
    if not resolved.exists():
        return False
    if resolved.is_dir():
        shutil.rmtree(resolved, onexc=_on_rm_error)
    else:
        resolved.unlink()
    return True


def iter_pycache(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")
            yield Path(dirpath) / "__pycache__"
        for d in [d for d in dirnames if d.endswith(".egg-info")]:
            dirnames.remove(d)
            yield Path(dirpath) / d


def cmd_clean(env: dict[str, str], include_deps: bool) -> int:
    rdir = run_dir(env)
    active = [n for n in SERVICES if running_pid(rdir, n) is not None]
    if active:
        raise DevctlError(f"Stop running services first (`make stop`): {', '.join(active)}")
    targets = [REPO_ROOT / p for p in CLEAN_PATHS]
    targets += list(iter_pycache(REPO_ROOT))
    if rdir.is_relative_to(REPO_ROOT):
        targets.append(rdir)
    if include_deps:
        targets += [REPO_ROOT / p for p in DEPENDENCY_PATHS]
    for target in targets:
        if _safe_rmtree(target):
            print(f"removed {target.relative_to(REPO_ROOT)}")
    return 0


# --------------------------------------------------------------------------- make help

_SECTION = re.compile(r"^##@\s*(.+)$")
_TARGET = re.compile(r"^([A-Za-z0-9_.-]+):[^=]*?##\s*(.+)$")


def render_make_help(makefile: Path) -> str:
    out = ["Usage: make <target> [SVC=all|api|web]", ""]
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if m := _SECTION.match(line):
            out += ["", m.group(1)]
        elif m := _TARGET.match(line):
            out.append(f"  {m.group(1):<16} {m.group(2).strip()}")
    return "\n".join(out).replace("\n\n\n", "\n\n").strip() + "\n"


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devctl", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="run services in the foreground")
    p.add_argument("target", nargs="?", default="all")
    p.add_argument("--debug", action="store_true", help="verbose logging")

    p = sub.add_parser("start", help="start services in the background")
    p.add_argument("target", nargs="?", default="all")
    p.add_argument("--timeout", type=float, default=READY_TIMEOUT_S)

    for name in ("stop", "restart"):
        p = sub.add_parser(name, help=f"{name} background services")
        p.add_argument("target", nargs="?", default="all")

    sub.add_parser("status", help="show background service status")

    p = sub.add_parser("logs", help="show background service logs")
    p.add_argument("target", nargs="?", default="all")
    p.add_argument("-n", "--lines", type=int, default=100)
    p.add_argument("-f", "--follow", action="store_true")

    p = sub.add_parser("health", help="HTTP health check of api and web")
    p.add_argument("--target", choices=("local", "docker"), default="local")

    p = sub.add_parser("install", help="install python and node dependencies")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("test", help="run automated tests")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("lint", help="run linters")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("format", help="format code")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("typecheck", help="run static type checkers")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("build", help="build production assets")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("check", help="run all linters, type checks, and tests")
    p.add_argument("target", nargs="?", default="all")

    p = sub.add_parser("clean", help="remove caches and build output")
    p.add_argument("--all", action="store_true", help="also remove .venv and node_modules")

    p = sub.add_parser("make-help", help="render Makefile help")
    p.add_argument("makefile", type=Path)

    p = sub.add_parser("touch", help="create/update a stamp file")
    p.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "make-help":
            sys.stdout.write(render_make_help(args.makefile))
            return 0
        if args.command == "touch":
            touch(args.path)
            return 0
        if args.command == "install":
            return cmd_install(args.target)
        if args.command == "test":
            return cmd_test(args.target)
        if args.command == "lint":
            return cmd_lint(args.target)
        if args.command == "format":
            return cmd_format(args.target)
        if args.command == "typecheck":
            return cmd_typecheck(args.target)
        if args.command == "build":
            return cmd_build(args.target)
        if args.command == "check":
            return cmd_check(args.target)

        env = build_env(debug=getattr(args, "debug", False))
        if args.command == "run":
            return cmd_run(select_services(args.target), env, args.debug)
        if args.command == "start":
            return cmd_start(select_services(args.target), env, args.timeout)
        if args.command == "stop":
            return cmd_stop(select_services(args.target), env)
        if args.command == "restart":
            names = select_services(args.target)
            return cmd_stop(names, env) or cmd_start(names, env, READY_TIMEOUT_S)
        if args.command == "status":
            return cmd_status(env)
        if args.command == "logs":
            return cmd_logs(select_services(args.target), env, args.lines, args.follow)
        if args.command == "health":
            return cmd_health(env, args.target)
        if args.command == "clean":
            return cmd_clean(env, args.all)
    except DevctlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
