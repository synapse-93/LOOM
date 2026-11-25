#!/usr/bin/env bash
set -euo pipefail

# 1. Resolve repository root
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
LOOM_PORT="${LOOM_PORT:-8000}"
PYTHON_BIN="${REPO_ROOT}/.venv312/bin/python"

WORKER_PID=""
TUNNEL_PID=""

cleanup() {
  echo ""
  echo "[LOOM] Shutting down production worker and tunnel cleanly..."
  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
    kill -TERM "${TUNNEL_PID}" 2>/dev/null || true
    wait "${TUNNEL_PID}" 2>/dev/null || true
  fi
  if [[ -n "${WORKER_PID}" ]] && kill -0 "${WORKER_PID}" 2>/dev/null; then
    kill -TERM "${WORKER_PID}" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "${WORKER_PID}" 2>/dev/null || break
      sleep 0.5
    done
    if kill -0 "${WORKER_PID}" 2>/dev/null; then
      kill -KILL "${WORKER_PID}" 2>/dev/null || true
    fi
    wait "${WORKER_PID}" 2>/dev/null || true
  fi
  echo "[LOOM] Shutdown complete (zero orphan processes)."
}

trap cleanup INT TERM EXIT

# 2. Verify .venv312 and CUDA availability
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[ERROR] Missing Python 3.12 virtual environment at ${PYTHON_BIN}" >&2
  exit 1
fi

GPU_NAME="$("${PYTHON_BIN}" -c "import torch; assert torch.cuda.is_available(), 'CUDA GPU unavailable'; print(torch.cuda.get_device_name(0))")"
echo "[LOOM] Verified runtime: ${PYTHON_BIN} | CUDA GPU: ${GPU_NAME}"

# 3. Start FastAPI GPU worker in background
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/serve_worker.py" --host 0.0.0.0 --port "${LOOM_PORT}" &
WORKER_PID=$!

# 4. Poll /api/health until HTTP 200 (timeout 20s)
HEALTH_URL="http://127.0.0.1:${LOOM_PORT}/api/health"
echo "[LOOM] Waiting for worker health check at ${HEALTH_URL} (timeout 20s)..."
READY=0
for _ in $(seq 1 40); do
  if ! kill -0 "${WORKER_PID}" 2>/dev/null; then
    echo "[ERROR] Worker process exited prematurely." >&2
    exit 1
  fi
  if command -v curl >/dev/null 2>&1; then
    if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
      READY=1
      break
    fi
  else
    if "${PYTHON_BIN}" -c "import urllib.request; urllib.request.urlopen('${HEALTH_URL}', timeout=1)" >/dev/null 2>&1; then
      READY=1
      break
    fi
  fi
  sleep 0.5
done

if [[ "${READY}" -ne 1 ]]; then
  echo "[ERROR] Timed out waiting for ${HEALTH_URL} after 20s." >&2
  exit 1
fi
echo "[LOOM] Worker is READY at http://127.0.0.1:${LOOM_PORT}"

# 5. Detect cloudflared and launch HTTPS tunnel if installed
CLOUDFLARED_BIN="$(command -v cloudflared || true)"
if [[ -z "${CLOUDFLARED_BIN}" && -x "${HOME}/.local/bin/cloudflared" ]]; then
  CLOUDFLARED_BIN="${HOME}/.local/bin/cloudflared"
fi

if [[ -n "${CLOUDFLARED_BIN}" ]]; then
  echo "[LOOM] Starting Cloudflare Quick Tunnel via ${CLOUDFLARED_BIN}..."
  TUNNEL_LOG="$(mktemp)"
  "${CLOUDFLARED_BIN}" tunnel --url "http://127.0.0.1:${LOOM_PORT}" >"${TUNNEL_LOG}" 2>&1 &
  TUNNEL_PID=$!

  LIVE_URL=""
  for _ in $(seq 1 30); do
    if ! kill -0 "${TUNNEL_PID}" 2>/dev/null; then
      echo "[WARNING] cloudflared exited unexpectedly; check log:" >&2
      cat "${TUNNEL_LOG}" >&2
      break
    fi
    LIVE_URL="$(grep -Eo 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "${TUNNEL_LOG}" | head -n 1 || true)"
    if [[ -n "${LIVE_URL}" ]]; then
      break
    fi
    sleep 0.5
  done

  if [[ -n "${LIVE_URL}" ]]; then
    echo "======================================================================"
    echo "LOOM LIVE HTTPS TUNNEL URL : ${LIVE_URL}"
    echo "Paste into Vercel Frontend : https://loomvidcapture.vercel.app"
    echo "Press Ctrl+C to stop both cloudflared and the LOOM GPU worker."
    echo "======================================================================"
  else
    echo "[LOOM] Tunnel running (PID ${TUNNEL_PID}); inspect logs for URL."
  fi
  rm -f "${TUNNEL_LOG}"
  wait "${WORKER_PID}"
else
  echo "======================================================================"
  echo "[LOOM] cloudflared not found on PATH or ~/.local/bin/cloudflared."
  echo "[LOOM] Running in LOCAL-ONLY mode at http://127.0.0.1:${LOOM_PORT}"
  echo "Press Ctrl+C to stop the LOOM GPU worker."
  echo "======================================================================"
  wait "${WORKER_PID}"
fi

