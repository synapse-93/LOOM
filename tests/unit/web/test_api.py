"""Unit tests for LOOM FastAPI Local GPU Worker & SSE Bridge (src/loom/web/)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from loom.web.app import create_app
from loom.web.manager import ReconstructionJobManager


class _FakeStdout:
    """Async line reader backed by an asyncio.Queue for deterministic subprocess mocking."""

    def __init__(self, lines: list[str], gate: Optional[asyncio.Event] = None) -> None:
        self._lines = list(lines)
        self._idx = 0
        self._gate = gate
        self._closed = False

    async def readline(self) -> bytes:
        if self._closed:
            return b""
        if self._idx < len(self._lines):
            line = self._lines[self._idx]
            self._idx += 1
            await asyncio.sleep(0.01)
            return (line + "\n").encode("utf-8")
        if self._gate is not None:
            await self._gate.wait()
        return b""

    def close(self) -> None:
        self._closed = True
        if self._gate is not None:
            self._gate.set()


class _FakeAsyncProcess:
    """Mock asyncio.subprocess.Process supporting streaming stdout, wait, terminate, and kill."""

    def __init__(
        self,
        lines: list[str],
        returncode: int = 0,
        on_finish: Optional[Any] = None,
        hold_gate: Optional[asyncio.Event] = None,
    ) -> None:
        self.stdout = _FakeStdout(lines, gate=hold_gate)
        self._target_rc = returncode
        self.returncode: Optional[int] = None
        self._on_finish = on_finish
        self._hold_gate = hold_gate
        self._done_event = asyncio.Event()
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        if self._hold_gate is not None:
            await self._hold_gate.wait()
        if self.returncode is None:
            if not self.terminated and not self.killed and self._on_finish is not None:
                self._on_finish()
            self.returncode = -15 if self.terminated else (-9 if self.killed else self._target_rc)
        self._done_event.set()
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self.stdout.close()
        self._done_event.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.stdout.close()
        self._done_event.set()


def _extract_arg_value(args: tuple[Any, ...], flag: str) -> Optional[str]:
    str_args = [str(a) for a in args]
    if flag in str_args:
        idx = str_args.index(flag)
        if idx + 1 < len(str_args):
            return str_args[idx + 1]
    return None


def _make_success_factory(
    stl_bytes: bytes,
    manifest_payload: dict[str, Any],
    log_lines: Optional[list[str]] = None,
    captured_envs: Optional[list[dict[str, str]]] = None,
):
    lines = log_lines or [
        "VIDEO2PRINT: End-to-End COLMAP 3D Reconstruction Demo",
        "Extracted 68 frames from 'input.mp4'",
        "Executing COLMAP stage 'feature_extractor'",
        "Executing COLMAP stage 'sequential_matcher'",
        "Executing COLMAP stage 'mapper'",
        "SfM registered 68 / 68 views (100.0%)",
        "Executing COLMAP stage 'image_undistorter'",
        "Executing COLMAP stage 'patch_match_stereo'",
        "Executing COLMAP stage 'stereo_fusion'",
        "Support plane alignment normalized point cloud: inliers=5000",
        "Foreground segmentation produced fused_isolated.ply",
        "Executing COLMAP stage 'poisson_mesher'",
        "Poisson meshing succeeded with 42000 vertices.",
        "Running Phase 3 mesh cleaning",
        "Applying target-length uniform scaling: target maximum dimension = 200.00 mm",
        "Validated metric binary STL exported: cleaned_metric.stl",
    ]

    async def _factory(*args: Any, **kwargs: Any) -> _FakeAsyncProcess:
        if captured_envs is not None and "env" in kwargs:
            captured_envs.append(dict(kwargs["env"]))

        stl_dir_str = _extract_arg_value(args, "--stl-dir")
        out_dir_str = _extract_arg_value(args, "--output-dir")
        target_dir = Path(stl_dir_str or out_dir_str or ".")

        def _write_artifacts() -> None:
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "loom_output.stl").write_bytes(stl_bytes)
            (target_dir / "printability_manifest.json").write_text(
                json.dumps(manifest_payload),
                encoding="utf-8",
            )

        return _FakeAsyncProcess(lines=lines, returncode=0, on_finish=_write_artifacts)

    return _factory


def test_health_schema_and_cors_headers(tmp_path: Path) -> None:
    """Verify GET /health schema and CORS headers for https://loomvidcapture.vercel.app."""
    manager = ReconstructionJobManager(jobs_root=tmp_path / "jobs")
    app = create_app(job_manager=manager)

    with (
        patch("loom.web.app._probe_gpu", return_value=("NVIDIA GeForce RTX 4060 Laptop GPU", 8188, 7600)),
        patch("loom.web.app._probe_colmap", return_value="COLMAP 4.2.0 (Commit be5e29168 on 2026-08-31 with CUDA)"),
    ):
        with TestClient(app) as client:
            resp = client.get(
                "/health",
                headers={"Origin": "https://loomvidcapture.vercel.app"},
            )
            assert resp.status_code == 200
            assert resp.headers.get("access-control-allow-origin") == "https://loomvidcapture.vercel.app"

            body = resp.json()
            assert body["status"] == "ok"
            assert body["gpu_name"] == "NVIDIA GeForce RTX 4060 Laptop GPU"
            assert body["vram_total_mib"] == 8188
            assert body["vram_free_mib"] == 7600
            assert "COLMAP 4.2.0" in body["colmap_version"]
            assert body["active_job_id"] is None
            assert body["queue_depth"] == 0
            assert body["ready"] is True

            # Verify Vercel preview deployment regex CORS
            preflight = client.options(
                "/api/reconstruct",
                headers={
                    "Origin": "https://loom-git-feat-preview.vercel.app",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert preflight.status_code == 200
            assert (
                preflight.headers.get("access-control-allow-origin")
                == "https://loom-git-feat-preview.vercel.app"
            )


def test_reconstruct_rejects_invalid_extension_and_oversized_and_accepts_mp4(tmp_path: Path) -> None:
    """Verify POST /api/reconstruct returns 400 for bad extension, 413 for >limit, and 202 for .mp4."""
    stl_bytes = b"LOOM_BINARY_STL_HEADER" + (b"\x00" * 62) + b"\x01\x00\x00\x00" + (b"\x00" * 50)
    manifest = {"triangles": 1, "watertight": True, "scale_factor_applied": 42.5}
    captured_envs: list[dict[str, str]] = []

    manager = ReconstructionJobManager(
        jobs_root=tmp_path / "jobs",
        subprocess_factory=_make_success_factory(stl_bytes, manifest, captured_envs=captured_envs),
        max_upload_bytes=1024,
    )
    app = create_app(job_manager=manager)

    with TestClient(app) as client:
        # 1. Invalid extension -> 400
        bad_resp = client.post(
            "/api/reconstruct",
            files={"file": ("notes.txt", b"not a video", "text/plain")},
            data={"target_length_mm": "200.0", "turbo": "true"},
        )
        assert bad_resp.status_code == 400

        # 2. Oversized upload -> 413
        big_resp = client.post(
            "/api/reconstruct",
            files={"file": ("huge.mp4", b"x" * 2048, "video/mp4")},
            data={"target_length_mm": "200.0", "turbo": "true"},
        )
        assert big_resp.status_code == 413

        # 3. Valid .mp4 -> 202 Accepted
        ok_resp = client.post(
            "/api/reconstruct",
            files={"file": ("scan.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
            data={"target_length_mm": "210.0", "turbo": "true"},
        )
        assert ok_resp.status_code == 202
        created = ok_resp.json()
        job_id = created["job_id"]
        assert created["status"] in ("QUEUED", "RUNNING")
        assert created["queue_position"] >= 1
        assert created["stream_url"] == f"/api/jobs/{job_id}/stream"
        assert created["stl_url"] == f"/api/jobs/{job_id}/stl"
        assert created["manifest_url"] == f"/api/jobs/{job_id}/manifest"

        # Wait via SSE stream for clean completion
        with client.stream("GET", f"/api/jobs/{job_id}/stream") as stream_resp:
            assert stream_resp.status_code == 200
            assert "text/event-stream" in stream_resp.headers["content-type"]
            assert stream_resp.headers.get("cache-control") == "no-cache"
            assert stream_resp.headers.get("x-accel-buffering") == "no"
            raw_sse = "".join(stream_resp.iter_text())

        assert "event: log" in raw_sse
        assert "event: progress" in raw_sse
        assert "event: done" in raw_sse

        # Verify job summary, STL bytes, and manifest JSON
        summary_resp = client.get(f"/api/jobs/{job_id}")
        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["status"] == "COMPLETED"
        assert summary["progress"] == 100
        assert summary["stl_ready"] is True
        assert summary["manifest"] == manifest

        stl_resp = client.get(f"/api/jobs/{job_id}/stl")
        assert stl_resp.status_code == 200
        assert stl_resp.headers["content-type"] == "application/octet-stream"
        assert stl_resp.content == stl_bytes

        manifest_resp = client.get(f"/api/jobs/{job_id}/manifest")
        assert manifest_resp.status_code == 200
        assert manifest_resp.json() == manifest

        # Verify jobs list endpoint
        list_resp = client.get("/api/jobs")
        assert list_resp.status_code == 200
        assert any(j["job_id"] == job_id for j in list_resp.json())

        # Verify subprocess inherited environment
        assert len(captured_envs) == 1


def test_fifo_single_gpu_serialization(tmp_path: Path) -> None:
    """Verify two concurrent uploads execute strictly sequentially (max concurrency == 1)."""

    async def _run() -> None:
        active_count = 0
        max_concurrent = 0
        order_events: list[str] = []
        call_num = 0

        async def _serialized_factory(*args: Any, **kwargs: Any) -> _FakeAsyncProcess:
            nonlocal active_count, max_concurrent, call_num
            call_num += 1
            idx = call_num
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            order_events.append(f"start:{idx}")

            out_dir = Path(_extract_arg_value(args, "--output-dir") or ".")

            def _finish() -> None:
                nonlocal active_count
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "loom_output.stl").write_bytes(b"STL" * 30)
                (out_dir / "printability_manifest.json").write_text(json.dumps({"job_num": idx}), encoding="utf-8")
                order_events.append(f"end:{idx}")
                active_count -= 1

            return _FakeAsyncProcess(
                lines=[f"Extracted 68 frames for job {idx}", "Validated metric binary STL exported"],
                returncode=0,
                on_finish=_finish,
            )

        manager = ReconstructionJobManager(
            jobs_root=tmp_path / "fifo_jobs",
            subprocess_factory=_serialized_factory,
        )
        app = create_app(job_manager=manager)
        manager.start()
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                r1, r2 = await asyncio.gather(
                    client.post(
                        "/api/reconstruct",
                        files={"file": ("first.mp4", b"video-one", "video/mp4")},
                    ),
                    client.post(
                        "/api/reconstruct",
                        files={"file": ("second.mp4", b"video-two", "video/mp4")},
                    ),
                )
                assert r1.status_code == 202
                assert r2.status_code == 202
                id1 = r1.json()["job_id"]
                id2 = r2.json()["job_id"]

                # Wait for both to reach COMPLETED
                for _ in range(100):
                    s1 = (await client.get(f"/api/jobs/{id1}")).json()["status"]
                    s2 = (await client.get(f"/api/jobs/{id2}")).json()["status"]
                    if s1 == "COMPLETED" and s2 == "COMPLETED":
                        break
                    await asyncio.sleep(0.02)

                assert s1 == "COMPLETED"
                assert s2 == "COMPLETED"
                assert max_concurrent == 1
                assert order_events == ["start:1", "end:1", "start:2", "end:2"]
        finally:
            await manager.stop()

    asyncio.run(_run())


def test_sse_live_streaming_and_active_cancellation(tmp_path: Path) -> None:
    """Verify SSE streams live logs, STL returns 409 while running, and DELETE cancels cleanly."""

    async def _run() -> None:
        hold_gate = asyncio.Event()
        started_event = asyncio.Event()
        spawned_procs: list[_FakeAsyncProcess] = []

        async def _blocking_factory(*args: Any, **kwargs: Any) -> _FakeAsyncProcess:
            proc = _FakeAsyncProcess(
                lines=[
                    "VIDEO2PRINT: End-to-End COLMAP 3D Reconstruction Demo",
                    "Executing COLMAP stage 'patch_match_stereo'",
                ],
                returncode=0,
                hold_gate=hold_gate,
            )
            spawned_procs.append(proc)
            started_event.set()
            return proc

        manager = ReconstructionJobManager(
            jobs_root=tmp_path / "cancel_jobs",
            subprocess_factory=_blocking_factory,
            heartbeat_interval=0.2,
        )
        app = create_app(job_manager=manager)
        manager.start()
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/reconstruct",
                    files={"file": ("long_scan.mp4", b"fake-mp4-data", "video/mp4")},
                )
                assert resp.status_code == 202
                job_id = resp.json()["job_id"]

                await asyncio.wait_for(started_event.wait(), timeout=2.0)

                # While running, STL and manifest must return 409 Conflict
                assert (await client.get(f"/api/jobs/{job_id}/stl")).status_code == 409
                assert (await client.get(f"/api/jobs/{job_id}/manifest")).status_code == 409

                # Open SSE stream concurrently, then cancel the active job
                received_chunks: list[str] = []

                async def _consume_sse() -> None:
                    async with client.stream("GET", f"/api/jobs/{job_id}/stream") as sse_resp:
                        assert sse_resp.status_code == 200
                        async for chunk in sse_resp.aiter_text():
                            received_chunks.append(chunk)

                sse_task = asyncio.create_task(_consume_sse())
                await asyncio.sleep(0.08)

                del_resp = await client.delete(f"/api/jobs/{job_id}")
                assert del_resp.status_code == 200
                assert del_resp.json()["status"] == "CANCELLED"
                assert len(spawned_procs) == 1
                assert spawned_procs[0].terminated is True

                await asyncio.wait_for(sse_task, timeout=2.0)
                full_stream = "".join(received_chunks)
                assert "patch_match_stereo" in full_stream
                assert "event: done" in full_stream
                assert '"status": "CANCELLED"' in full_stream

                # Deleting a terminal record removes it cleanly -> subsequent GET returns 404
                remove_resp = await client.delete(f"/api/jobs/{job_id}")
                assert remove_resp.status_code == 200
                assert (await client.get(f"/api/jobs/{job_id}")).status_code == 404
        finally:
            hold_gate.set()
            await manager.stop()

    asyncio.run(_run())


def test_webm_remux_and_failed_job_captures_tail_logs(tmp_path: Path) -> None:
    """Verify .webm remux fallback when ffmpeg is absent and non-zero exit captures last 15 lines."""
    invoked_cmds: list[list[str]] = []

    async def _failing_factory(*args: Any, **kwargs: Any) -> _FakeAsyncProcess:
        invoked_cmds.append([str(a) for a in args])
        lines = [f"stage log line {i}" for i in range(1, 21)]
        return _FakeAsyncProcess(lines=lines, returncode=1)

    manager = ReconstructionJobManager(
        jobs_root=tmp_path / "fail_jobs",
        subprocess_factory=_failing_factory,
    )
    app = create_app(job_manager=manager)

    with patch("loom.web.manager.shutil.which", return_value=None):
        with TestClient(app) as client:
            resp = client.post(
                "/api/reconstruct",
                files={"file": ("capture.webm", b"fake-webm-bytes", "video/webm")},
                data={"target_length_mm": "180.0", "turbo": "false"},
            )
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]

            with client.stream("GET", f"/api/jobs/{job_id}/stream") as stream_resp:
                raw_sse = "".join(stream_resp.iter_text())

            assert "ffmpeg not found on PATH" in raw_sse
            assert "event: done" in raw_sse

            summary = client.get(f"/api/jobs/{job_id}").json()
            assert summary["status"] == "FAILED"
            assert summary["stl_ready"] is False
            assert summary["error"] is not None
            error_lines = summary["error"].splitlines()
            assert len(error_lines) == 15
            assert error_lines[-1] == "stage log line 20"

            # Verify non-turbo passed --engine 2dgs --export-stl (no --turbo) and passed .webm directly
            assert len(invoked_cmds) == 1
            assert "--engine" in invoked_cmds[0]
            assert "2dgs" in invoked_cmds[0]
            assert "--export-stl" in invoked_cmds[0]
            assert "--turbo" not in invoked_cmds[0]
            assert any(arg.endswith("input.webm") for arg in invoked_cmds[0])


def test_infer_stage_and_progress_tracks_2dgs_markers() -> None:
    """Verify SSE progress parser recognizes [MASK], [VISUAL_HULL], [2DGS] Step X/Y, [TSDF], and [EXPORT]."""
    from loom.web.manager import infer_stage_and_progress

    p, stage = infer_stage_and_progress("[MASK] Segmenting 68 undistorted frames", 38, "Phase 2")
    assert p == 42
    assert "Masking" in stage

    p, stage = infer_stage_and_progress("[VISUAL_HULL] 20002 -> 11281 core foreground points", p, stage)
    assert p == 47
    assert "Visual-Hull" in stage

    p, stage = infer_stage_and_progress("[2DGS] Step 1750/3500 | loss=0.0412 | surfels=42000", p, stage)
    assert p == 63  # 48 + round(0.5 * 30)
    assert "1750/3500" in stage

    p, stage = infer_stage_and_progress("[2DGS] Step 3500/3500 | loss=0.0210 | surfels=95000", p, stage)
    assert p == 78
    assert "3500/3500" in stage

    p, stage = infer_stage_and_progress("[TSDF] Running Marching Cubes surface extraction...", p, stage)
    assert p == 80
    assert "TSDF" in stage

    p, stage = infer_stage_and_progress("[TSDF] Extracted raw 2DGS mesh -> mesh_2dgs_raw.ply", p, stage)
    assert p == 84

    p, stage = infer_stage_and_progress("[EXPORT] Applied Taubin smoothing (5 iters)", p, stage)
    assert p == 86

    p, stage = infer_stage_and_progress("[EXPORT] PrintabilityGate PASSED | watertight=True", p, stage)
    assert p == 96

    p, stage = infer_stage_and_progress("[EXPORT] Validated metric binary STL exported: loom_output.stl", p, stage)
    assert p == 99


