#!/usr/bin/env python3
"""Launcher for the LOOM FastAPI Local GPU Worker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is on sys.path for direct script execution
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="serve_worker.py",
        description="Start the LOOM FastAPI Local GPU Reconstruction Worker (single-GPU FIFO queue).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host interface (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind TCP port (default: 8000).",
    )
    args = parser.parse_args(argv)

    import uvicorn

    print("\n" + "=" * 70)
    print("LOOM LOCAL GPU WORKER (FastAPI + Single-GPU FIFO Queue)")
    print("=" * 70)
    print(f"Python Runtime     : {sys.executable}")
    print("Default Engine     : Masked 2DGS + TSDF (gsplat 1.5.3 / Open3D)")
    print(f"Local API Endpoint : http://{args.host}:{args.port}")
    print(f"Health Probe       : http://localhost:{args.port}/health")
    print(f"OpenAPI Docs       : http://localhost:{args.port}/docs")
    print("-" * 70)
    print("Expose to Vercel frontend (https://loomvidcapture.vercel.app) via HTTPS:")
    print(f"  cloudflared tunnel --url http://localhost:{args.port}")
    print("=" * 70 + "\n")

    uvicorn.run(
        "loom.web.app:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

