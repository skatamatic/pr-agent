"""
Tests for GCP deployment scripts: deploy-gcp.* and build-push-gcp.*.

Run from repo root: pytest scripts/tests/test_gcp_scripts.py -v
These tests invoke the scripts with env that triggers expected failures (missing vars, bad paths).
No GCP or Terraform state is modified.

On Windows, bash scripts are run via WSL when available (prereq: WSL installed).
"""

import os
import shutil
import subprocess
import sys

import pytest

# Repo root (parent of scripts/)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _windows_path_to_wsl(windows_path: str) -> str:
    """Convert Windows path to WSL path (e.g. D:\\Repos\\pr-agent -> /mnt/d/Repos/pr-agent)."""
    path = os.path.normpath(windows_path)
    parts = path.replace("\\", "/").split(":/", 1)
    if len(parts) == 2 and len(parts[0]) == 1:
        return f"/mnt/{parts[0].lower()}/{parts[1].lstrip('/')}"
    if path.startswith("\\\\"):
        pytest.skip("UNC paths not supported for WSL")
    return path.replace("\\", "/")


def _run_bash(script_path: str, env: dict | None = None, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run a bash script. On Windows with WSL, run via wsl bash."""
    env = env or {}
    full_env = {**os.environ, **env}
    if sys.platform == "win32" and shutil.which("wsl"):
        wsl_repo = _windows_path_to_wsl(REPO_ROOT)
        rel_script = os.path.relpath(script_path, REPO_ROOT).replace("\\", "/")
        exports = " ".join(f'export {k}="{str(v).replace(chr(34), chr(92)+chr(34))}"' for k, v in env.items() if v is not None)
        cmd = f"cd {wsl_repo} && {exports} && bash {rel_script}" if exports else f"cd {wsl_repo} && bash {rel_script}"
        return subprocess.run(
            ["wsl", "bash", "-c", cmd],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return subprocess.run(
        ["bash", script_path],
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _pwsh_or_powershell():
    """Prefer pwsh, fallback to powershell (Windows)."""
    return "pwsh" if shutil.which("pwsh") else "powershell"


def _run_powershell(script_path: str, args: list | None = None, env: dict | None = None, timeout: int = 15) -> subprocess.CompletedProcess:
    env = env or {}
    full_env = {**os.environ, **env}
    exe = _pwsh_or_powershell()
    cmd = [exe, "-NoProfile", "-File", script_path] if exe == "pwsh" else [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO_ROOT, "scripts", "deploy-gcp.sh")), reason="deploy-gcp.sh missing")
@pytest.mark.skipif(sys.platform == "win32" and not shutil.which("wsl"), reason="On Windows, WSL is required to run bash scripts")
def test_deploy_gcp_sh_fails_when_terraform_dir_missing():
    """deploy-gcp.sh should exit non-zero when TERRAFORM_DIR points to a dir without main.tf."""
    result = _run_bash(
        os.path.join(REPO_ROOT, "scripts", "deploy-gcp.sh"),
        env={"TERRAFORM_DIR": "scripts/tests"},  # no main.tf here
    )
    assert result.returncode != 0
    assert "not found" in (result.stderr + result.stdout).lower() or "error" in (result.stderr + result.stdout).lower()


@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO_ROOT, "scripts", "build-push-gcp.sh")), reason="build-push-gcp.sh missing")
@pytest.mark.skipif(sys.platform == "win32" and not shutil.which("wsl"), reason="On Windows, WSL is required to run bash scripts")
def test_build_push_gcp_sh_fails_when_project_id_unset():
    """build-push-gcp.sh should exit non-zero when PROJECT_ID and TF_VAR_project_id are unset."""
    # Explicitly unset so the script sees missing PROJECT_ID (works with WSL when we pass only these)
    env = {"PROJECT_ID": "", "TF_VAR_project_id": ""}
    result = _run_bash(
        os.path.join(REPO_ROOT, "scripts", "build-push-gcp.sh"),
        env=env,
    )
    if result.returncode == 127 and "not found" in (result.stderr or "").lower():
        pytest.skip("bash not found in WSL - use a distro with bash (e.g. Ubuntu) or run .ps1 scripts on Windows")
    assert result.returncode != 0
    assert "PROJECT_ID" in (result.stderr + result.stdout)


@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO_ROOT, "scripts", "deploy-gcp.ps1")), reason="deploy-gcp.ps1 missing")
@pytest.mark.skipif(not (shutil.which("pwsh") or (sys.platform == "win32" and shutil.which("powershell"))), reason="pwsh or powershell not on PATH")
def test_deploy_gcp_ps1_fails_when_terraform_dir_missing():
    """deploy-gcp.ps1 should exit non-zero when TerraformDir points to a dir without main.tf."""
    try:
        result = _run_powershell(
            os.path.join(REPO_ROOT, "scripts", "deploy-gcp.ps1"),
            args=["-TerraformDir", "scripts/tests"],
        )
    except FileNotFoundError:
        pytest.skip("pwsh not installed")
        return
    assert result.returncode != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "not found" in combined.lower() or "error" in combined.lower() or "terraform" in combined.lower()


@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO_ROOT, "scripts", "build-push-gcp.ps1")), reason="build-push-gcp.ps1 missing")
@pytest.mark.skipif(not (shutil.which("pwsh") or (sys.platform == "win32" and shutil.which("powershell"))), reason="pwsh or powershell not on PATH")
def test_build_push_gcp_ps1_fails_when_project_id_unset():
    """build-push-gcp.ps1 should exit non-zero when ProjectId and TF_VAR_project_id are unset."""
    env = {k: v for k, v in os.environ.items() if k not in ("TF_VAR_project_id",)}
    try:
        result = _run_powershell(
            os.path.join(REPO_ROOT, "scripts", "build-push-gcp.ps1"),
            env=env,
        )
    except FileNotFoundError:
        pytest.skip("pwsh not installed")
        return
    assert result.returncode != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "project" in combined.lower() or "ProjectId" in combined


def _terraform_available() -> bool:
    """True if terraform is on PATH (or in WSL on Windows)."""
    if sys.platform == "win32" and shutil.which("wsl"):
        r = subprocess.run(["wsl", "which", "terraform"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    return bool(shutil.which("terraform"))


@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO_ROOT, "terraform", "gcp", "validate.sh")), reason="validate.sh missing")
@pytest.mark.skipif(sys.platform == "win32" and not shutil.which("wsl"), reason="On Windows, WSL is required to run validate.sh")
@pytest.mark.skipif(not _terraform_available(), reason="terraform not on PATH (or in WSL on Windows)")
def test_terraform_validate_sh_succeeds():
    """terraform/gcp/validate.sh should run init, validate, and fmt-check successfully (no GCP). Runs via WSL on Windows."""
    result = _run_bash(os.path.join(REPO_ROOT, "terraform", "gcp", "validate.sh"), env={}, timeout=90)
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    assert "validation passed" in (result.stdout or "").lower() or "validate" in (result.stdout or "").lower()


@pytest.mark.skipif(not os.path.isfile(os.path.join(REPO_ROOT, "terraform", "gcp", "validate.ps1")), reason="validate.ps1 missing")
@pytest.mark.skipif(not shutil.which("terraform"), reason="terraform not on PATH")
@pytest.mark.skipif(not (shutil.which("pwsh") or (sys.platform == "win32" and shutil.which("powershell"))), reason="pwsh or powershell not on PATH")
def test_terraform_validate_ps1_succeeds():
    """terraform/gcp/validate.ps1 should run init, validate, and fmt-check successfully (no GCP)."""
    exe = _pwsh_or_powershell()
    validate_ps1 = os.path.join(REPO_ROOT, "terraform", "gcp", "validate.ps1")
    cmd = [exe, "-NoProfile", "-File", validate_ps1] if exe == "pwsh" else [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", validate_ps1]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    assert "validation passed" in (result.stdout or "").lower() or "validate" in (result.stdout or "").lower()
