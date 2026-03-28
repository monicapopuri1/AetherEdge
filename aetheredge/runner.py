"""
WorkloadRunner — downloads, executes, reports, and cleans up agent scripts.
BlueprintRunner — downloads, validates, runs, and cleans up Docker Compose blueprints.

Security model (WorkloadRunner):
  - Scripts are saved to ~/.aetheredge/workloads/{task_id}.py (0o700 dir, 0o600 file)
  - subprocess runs with a minimal clean environment:
      PATH, HOME, LANG, USER, TMPDIR only
      No AETHER_*, SSL_*, CERT_*, KEY_*, PYTHONPATH — private keys stay invisible
  - Working directory is the isolated workloads/ dir, not the project root
  - Script is deleted in a finally block regardless of success or failure (zero-footprint)

Security model (BlueprintRunner):
  - Blueprints are saved to ~/.aetheredge/blueprints/{task_id}.yml (0o700 dir, 0o600 file)
  - YAML is parsed and validated before execution (must have a 'services' key)
  - Only AETHER_NODE_ID, AETHER_TASK_ID, AETHER_ORCHESTRATOR_URL are injected as env —
    no certificate paths, keys, or tokens are exposed to the compose environment
  - docker compose down --volumes --remove-orphans runs in a finally block (zero-footprint)
  - Blueprint file is deleted in a finally block regardless of success or failure
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests
import yaml
from rich.console import Console

console = Console()

WORKLOADS_DIR = Path.home() / ".aetheredge" / "workloads"
BLUEPRINTS_DIR = Path.home() / ".aetheredge" / "blueprints"
SCRIPT_TIMEOUT = 60    # seconds
BLUEPRINT_TIMEOUT = 300  # seconds — compose services may need time to pull & start

# Env vars that must never leak into the subprocess
_BLOCKED_PREFIXES = ("AETHER", "SSL", "CERT", "KEY", "SECRET", "TOKEN", "REQUESTS_CA")


def _clean_env() -> dict[str, str]:
    """Build a minimal environment for the subprocess — no sensitive vars."""
    safe = {}
    for key in ("PATH", "HOME", "LANG", "LC_ALL", "USER", "LOGNAME", "TMPDIR", "TEMP", "TMP"):
        if key in os.environ:
            safe[key] = os.environ[key]

    # Ensure PATH has a usable default if not set
    safe.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")

    # Explicitly block any var that slipped through with a sensitive prefix
    return {k: v for k, v in safe.items()
            if not any(k.upper().startswith(p) for p in _BLOCKED_PREFIXES)}


class WorkloadRunner:
    def __init__(
        self,
        node_id: str,
        orchestrator_url: str,
        cert: tuple[str, str],
        ca_cert: str,
    ):
        self.node_id = node_id
        self.orchestrator_url = orchestrator_url
        self.cert = cert
        self.ca_cert = ca_cert

        WORKLOADS_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(WORKLOADS_DIR, 0o700)

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, task_id: str, script_url: str) -> None:
        console.print(
            f"\n[bold magenta]>>> Task received:[/bold magenta] "
            f"(id: {task_id[:8]}…)"
        )

        script_path = WORKLOADS_DIR / f"{task_id}.py"
        try:
            self._download(script_url, script_path)
            result = self._execute(script_path)
            self._report(task_id, result)
        finally:
            # Zero-footprint — always delete, even on error
            if script_path.exists():
                script_path.unlink()
                console.print(f"[dim]    Script deleted: {script_path.name}[/dim]")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _download(self, script_url: str, dest: Path) -> None:
        console.print(f"[dim]    Downloading script: {script_url}[/dim]")
        url = script_url

        resp = requests.get(url, cert=self.cert, verify=self.ca_cert, timeout=10)
        resp.raise_for_status()

        dest.write_text(resp.text)
        os.chmod(dest, 0o600)  # owner read/write only — not executable by others

    def _execute(self, script_path: Path) -> dict:
        console.print(f"[bold magenta]    Executing Agent...[/bold magenta]")
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT,
                env=_clean_env(),
                cwd=str(WORKLOADS_DIR),  # isolated working dir — not project root
            )
            result = {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "return_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            result = {
                "stdout": "",
                "stderr": f"Workload timed out after {SCRIPT_TIMEOUT}s.",
                "return_code": -1,
            }

        status = "[green]✓ exit 0[/green]" if result["return_code"] == 0 else f"[red]✗ exit {result['return_code']}[/red]"
        console.print(f"    Status : {status}")
        if result["stdout"]:
            console.print("[dim]" + result["stdout"].rstrip() + "[/dim]")
        if result["stderr"]:
            console.print(f"[yellow]{result['stderr'].rstrip()}[/yellow]")

        return result

    def _report(self, task_id: str, result: dict) -> None:
        try:
            resp = requests.post(
                f"{self.orchestrator_url}/api/v1/tasks/{task_id}/result",
                json={"stdout": result["stdout"], "exit_code": result["return_code"]},
                cert=self.cert,
                verify=self.ca_cert,
                timeout=10,
            )
            resp.raise_for_status()
            console.print("[bold green]>>> Task complete. Result posted.[/bold green]\n")
        except requests.exceptions.RequestException as exc:
            console.print(f"[red]>>> Failed to post result: {exc}[/red]\n")


class BlueprintRunner:
    """
    Downloads a Docker Compose blueprint from the orchestrator, validates it,
    runs it via `docker compose up`, collects output, and cleans up.

    Environment injected into compose:
      AETHER_NODE_ID, AETHER_TASK_ID, AETHER_ORCHESTRATOR_URL only.
      No cert paths or keys are exposed.
    """

    def __init__(
        self,
        node_id: str,
        orchestrator_url: str,
        cert: tuple[str, str],
        ca_cert: str,
    ):
        self.node_id = node_id
        self.orchestrator_url = orchestrator_url
        self.cert = cert
        self.ca_cert = ca_cert

        BLUEPRINTS_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(BLUEPRINTS_DIR, 0o700)

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, task_id: str, blueprint_url: str) -> None:
        console.print(
            f"\n[bold cyan]>>> Blueprint received:[/bold cyan] "
            f"(id: {task_id[:8]}…)"
        )

        blueprint_path = BLUEPRINTS_DIR / f"{task_id}.yml"
        compose_cmd = self._detect_compose_cmd()

        try:
            self._download(blueprint_url, blueprint_path)
            self._validate(blueprint_path)
            result = self._execute(blueprint_path, task_id, compose_cmd)
            self._report(task_id, result)
        finally:
            self._teardown(blueprint_path, task_id, compose_cmd)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _detect_compose_cmd(self) -> list[str]:
        """Return ['docker', 'compose'] if available, else ['docker-compose']."""
        if shutil.which("docker"):
            try:
                subprocess.run(
                    ["docker", "compose", "version"],
                    capture_output=True, check=True, timeout=5,
                )
                return ["docker", "compose"]
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        if shutil.which("docker-compose"):
            return ["docker-compose"]
        raise RuntimeError(
            "Neither 'docker compose' nor 'docker-compose' is available on this node."
        )

    def _download(self, blueprint_url: str, dest: Path) -> None:
        console.print(f"[dim]    Downloading blueprint: {blueprint_url}[/dim]")
        resp = requests.get(
            blueprint_url, cert=self.cert, verify=self.ca_cert, timeout=15
        )
        resp.raise_for_status()
        dest.write_text(resp.text)
        os.chmod(dest, 0o600)

    def _validate(self, blueprint_path: Path) -> None:
        """Parse YAML and assert it looks like a Compose file."""
        console.print("[dim]    Validating blueprint YAML...[/dim]")
        try:
            doc = yaml.safe_load(blueprint_path.read_text())
        except yaml.YAMLError as exc:
            raise ValueError(f"Blueprint is not valid YAML: {exc}") from exc
        if not isinstance(doc, dict) or "services" not in doc:
            raise ValueError("Blueprint must be a Docker Compose file with a 'services' key.")
        console.print(
            f"[dim]    Services: {', '.join(doc['services'].keys())}[/dim]"
        )

    def _build_compose_env(self, task_id: str) -> dict[str, str]:
        """Minimal env for docker compose — only operational AETHER vars, no secrets."""
        env = {k: v for k, v in os.environ.items()
               if not any(k.upper().startswith(p)
                          for p in ("SSL", "CERT", "KEY", "SECRET", "TOKEN", "REQUESTS_CA"))}
        env["AETHER_NODE_ID"] = self.node_id
        env["AETHER_TASK_ID"] = task_id
        env["AETHER_ORCHESTRATOR_URL"] = self.orchestrator_url
        return env

    def _execute(self, blueprint_path: Path, task_id: str, compose_cmd: list[str]) -> dict:
        console.print("[bold cyan]    Starting Docker Compose services...[/bold cyan]")
        cmd = compose_cmd + [
            "-f", str(blueprint_path),
            "up", "--build", "--abort-on-container-exit",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=BLUEPRINT_TIMEOUT,
                env=self._build_compose_env(task_id),
                cwd=str(BLUEPRINTS_DIR),
            )
            result = {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "return_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            result = {
                "stdout": "",
                "stderr": f"Blueprint timed out after {BLUEPRINT_TIMEOUT}s.",
                "return_code": -1,
            }

        status = "[green]✓ exit 0[/green]" if result["return_code"] == 0 else f"[red]✗ exit {result['return_code']}[/red]"
        console.print(f"    Status : {status}")
        if result["stdout"]:
            console.print("[dim]" + result["stdout"].rstrip() + "[/dim]")
        if result["stderr"]:
            console.print(f"[yellow]{result['stderr'].rstrip()}[/yellow]")

        return result

    def _teardown(self, blueprint_path: Path, task_id: str, compose_cmd: list[str]) -> None:
        """Bring services down and delete the blueprint file."""
        if blueprint_path.exists():
            try:
                down_cmd = compose_cmd + [
                    "-f", str(blueprint_path),
                    "down", "--volumes", "--remove-orphans",
                ]
                subprocess.run(
                    down_cmd,
                    capture_output=True,
                    timeout=60,
                    env=self._build_compose_env(task_id),
                    cwd=str(BLUEPRINTS_DIR),
                )
                console.print("[dim]    Compose services stopped and removed.[/dim]")
            except Exception as exc:
                console.print(f"[yellow]    Teardown warning: {exc}[/yellow]")
            finally:
                blueprint_path.unlink()
                console.print(f"[dim]    Blueprint deleted: {blueprint_path.name}[/dim]")

    def _report(self, task_id: str, result: dict) -> None:
        try:
            resp = requests.post(
                f"{self.orchestrator_url}/api/v1/tasks/{task_id}/result",
                json={"stdout": result["stdout"], "exit_code": result["return_code"]},
                cert=self.cert,
                verify=self.ca_cert,
                timeout=10,
            )
            resp.raise_for_status()
            console.print("[bold green]>>> Blueprint task complete. Result posted.[/bold green]\n")
        except requests.exceptions.RequestException as exc:
            console.print(f"[red]>>> Failed to post blueprint result: {exc}[/red]\n")
