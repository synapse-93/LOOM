"""Safe subprocess execution helper for external tools."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Sequence, Union

logger = logging.getLogger(__name__)


def run_subprocess(
    command: Sequence[Union[str, Path]],
    cwd: Union[str, Path, None] = None,
    timeout: int = 1800,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute an external command in an isolated subprocess.

    Args:
        command: List of command arguments.
        cwd: Optional working directory.
        timeout: Execution timeout in seconds (default 1800s / 30m).
        check: If True, raises subprocess.CalledProcessError on non-zero exit.

    Returns:
        subprocess.CompletedProcess with captured text output.

    Raises:
        subprocess.TimeoutExpired: When command execution exceeds timeout.
        subprocess.CalledProcessError: When command exits non-zero and check is True.
        FileNotFoundError: When executable is not found.
    """
    cmd_str_list = [str(arg) for arg in command]
    working_dir = Path(cwd).resolve() if cwd is not None else None

    logger.debug("Executing command: %s (cwd: %s)", " ".join(cmd_str_list), working_dir)

    try:
        result = subprocess.run(
            cmd_str_list,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
        return result
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
