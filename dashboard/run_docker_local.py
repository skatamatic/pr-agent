#!/usr/bin/env python3
"""
Rebuild and run the PR-Agent Dashboard Docker containers locally.

- Builds backend and frontend images from the repository root.
- Runs backend on port 8000 (SQLite in a volume for persistence).
- Runs frontend on port 3000 (points to http://localhost:8000 for API/WS).

Usage (from repo root):
  python dashboard/run_docker_local.py
  python dashboard/run_docker_local.py --no-rebuild   # run existing images only
  python dashboard/run_docker_local.py --stop         # stop and remove containers only

Requires: Docker. On Windows, run from PowerShell or cmd (or WSL for bash).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


# Image names and container names
BACKEND_IMAGE = "pr-agent-dashboard-backend"
BACKEND_CONTAINER = "pr-agent-dashboard-backend"
FRONTEND_IMAGE = "pr-agent-dashboard-frontend"
FRONTEND_CONTAINER = "pr-agent-dashboard-frontend"
BACKEND_DATA_VOLUME = "pr-agent-dashboard-data"

BACKEND_PORT = 8000
FRONTEND_PORT = 3000


def repo_root() -> Path:
    """Resolve repository root (directory containing dashboard/)."""
    script = Path(__file__).resolve()
    # script is repo/dashboard/run_docker_local.py
    dashboard_dir = script.parent
    root = dashboard_dir.parent
    if not (root / "dashboard" / "backend" / "Dockerfile").exists():
        raise SystemExit("Error: Run this script from the pr-agent repo root or ensure dashboard/backend/Dockerfile exists.")
    return root


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command; exit on failure if check=True."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or None)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result


def docker_available() -> bool:
    try:
        run(["docker", "info"], check=False)
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def stop_containers():
    """Stop and remove existing dashboard containers (and optionally volumes)."""
    for name in (BACKEND_CONTAINER, FRONTEND_CONTAINER):
        run(["docker", "rm", "-f", name], check=False)
    print("Stopped and removed containers.")


def build_and_run(*, rebuild: bool, stop_only: bool):
    root = repo_root()
    os.chdir(root)

    if not docker_available():
        print("Error: Docker is not available. Install Docker and ensure it is running.", file=sys.stderr)
        sys.exit(1)

    if stop_only:
        stop_containers()
        return

    # Stop any existing containers so we can re-run
    stop_containers()

    if rebuild:
        print("Building backend image...")
        run([
            "docker", "build",
            "-f", "dashboard/backend/Dockerfile",
            "-t", BACKEND_IMAGE,
            ".",
        ], cwd=root)

        print("Building frontend image (REACT_APP_API_URL=http://localhost:8000)...")
        run([
            "docker", "build",
            "-f", "dashboard/frontend/Dockerfile",
            "--build-arg", "REACT_APP_API_URL=http://localhost:8000",
            "--build-arg", "REACT_APP_WS_URL=ws://localhost:8000/ws",
            "-t", FRONTEND_IMAGE,
            ".",
        ], cwd=root)

    # Backend: SQLite in a volume so data persists
    print("Starting backend container...")
    run([
        "docker", "run", "-d",
        "--name", BACKEND_CONTAINER,
        "-p", f"{BACKEND_PORT}:8000",
        "-e", "DATABASE_URL=sqlite:///./data/dashboard.db",
        "-e", "PORT=8000",
        "-v", f"{BACKEND_DATA_VOLUME}:/app/data",
        BACKEND_IMAGE,
    ])

    # Frontend: serve on 3000, API/WS point to localhost:8000 (browser talks to host)
    print("Starting frontend container...")
    run([
        "docker", "run", "-d",
        "--name", FRONTEND_CONTAINER,
        "-p", f"{FRONTEND_PORT}:80",
        FRONTEND_IMAGE,
    ])

    print()
    print("Dashboard is running locally:")
    print(f"  Frontend:  http://localhost:{FRONTEND_PORT}")
    print(f"  Backend:   http://localhost:{BACKEND_PORT}")
    print(f"  API docs:  http://localhost:{BACKEND_PORT}/docs")
    print()
    print("To stop:  python dashboard/run_docker_local.py --stop")


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild and run PR-Agent Dashboard Docker containers locally.",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Use existing images; only start containers (fails if images missing).",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop and remove the dashboard containers only.",
    )
    args = parser.parse_args()
    build_and_run(rebuild=not args.no_rebuild, stop_only=args.stop)


if __name__ == "__main__":
    main()
