"""Safe subprocess execution helper for external tools."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

logger = logging.getLogger(__name__)

CUDA_LIB_DIR = Path("/opt/cuda/lib64")


def _build_subprocess_env(
    env: Optional[Mapping[str, str]] = None,
    cuda_lib_dir: Path = CUDA_LIB_DIR,
) -> dict[str, str]:
    """Construct subprocess environment ensuring CUDA libraries are on LD_LIBRARY_PATH."""
    run_env = dict(os.environ if env is None else env)
    if cuda_lib_dir.is_dir():
        cuda_dir_str = str(cuda_lib_dir)
        existing = run_env.get("LD_LIBRARY_PATH", "")
        parts = [p for p in existing.split(os.pathsep) if p]
        if not parts or parts[0] != cuda_dir_str:
            filtered = [p for p in parts if p != cuda_dir_str]
            run_env["LD_LIBRARY_PATH"] = os.pathsep.join([cuda_dir_str, *filtered])
    return run_env


def run_subprocess(
    command: Sequence[Union[str, Path]],
    cwd: Union[str, Path, None] = None,
    timeout: int = 1800,
    check: bool = True,
    stream_output: bool = True,
    env: Optional[Mapping[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    """Execute an external command in an isolated subprocess with optional live streaming.

    Automatically prepends ``/opt/cuda/lib64`` to ``LD_LIBRARY_PATH`` when present on the
    host so CUDA-linked binaries (e.g. ``/usr/bin/colmap``) resolve ``libcudart``.

    Args:
        command: List of command arguments.
        cwd: Optional working directory.
        timeout: Execution timeout in seconds (default 1800s / 30m).
        check: If True, raises subprocess.CalledProcessError on non-zero exit.
        stream_output: If True, streams stdout and stderr live to terminal while collecting.
        env: Optional environment mapping overriding ``os.environ``.

    Returns:
        subprocess.CompletedProcess with captured text output.

    Raises:
        subprocess.TimeoutExpired: When command execution exceeds timeout.
        subprocess.CalledProcessError: When command exits non-zero and check is True.
        FileNotFoundError: When executable is not found.
    """
    cmd_str_list = [str(arg) for arg in command]
    working_dir = Path(cwd).resolve() if cwd is not None else None
    run_env = _build_subprocess_env(env=env)

    logger.debug("Executing command: %s (cwd: %s)", " ".join(cmd_str_list), working_dir)

    if not stream_output:
        try:
            return subprocess.run(
                cmd_str_list,
                cwd=working_dir,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error("Command timed out after %ds: %s", timeout, cmd_str_list[0])
            raise
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Command failed with exit code %d: %s\nStderr: %s",
                exc.returncode,
                cmd_str_list[0],
                exc.stderr,
            )
            raise

    # Streaming mode via Popen with background pipe readers
    process = subprocess.Popen(
        cmd_str_list,
        cwd=working_dir,
        env=run_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def reader(pipe, collector, stream):
        if pipe is None:
            return
        for line in iter(pipe.readline, ""):
            collector.append(line)
            try:
                stream.write(line)
                stream.flush()
            except Exception:
                pass
        pipe.close()

    t_out = threading.Thread(target=reader, args=(process.stdout, stdout_lines, sys.stdout), daemon=True)
    t_err = threading.Thread(target=reader, args=(process.stderr, stderr_lines, sys.stderr), daemon=True)
    t_out.start()
    t_err.start()

    try:
        retcode = process.wait(timeout=timeout)
        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)
        logger.error("Command timed out after %ds: %s", timeout, cmd_str_list[0])
        raise

    full_stdout = "".join(stdout_lines)
    full_stderr = "".join(stderr_lines)

    if check and retcode != 0:
        logger.error(
            "Command failed with exit code %d: %s\nStderr: %s",
            retcode,
            cmd_str_list[0],
            full_stderr,
        )
        raise subprocess.CalledProcessError(retcode, cmd_str_list, output=full_stdout, stderr=full_stderr)

    return subprocess.CompletedProcess(cmd_str_list, retcode, stdout=full_stdout, stderr=full_stderr)

