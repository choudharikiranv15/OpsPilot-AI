"""Bounded subprocess execution (no shell, capped output, hard timeout)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

DEFAULT_MAX_BYTES = 5 * 1024 * 1024


@dataclass
class ProcResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


def tail_bytes(chunks: Iterable[bytes], max_bytes: int) -> bytes:
    """Consume ``chunks`` keeping only the last ``max_bytes`` bytes."""
    kept: deque[bytes] = deque()
    size = 0
    for chunk in chunks:
        if not chunk:
            continue
        kept.append(chunk)
        size += len(chunk)
        while kept and size - len(kept[0]) >= max_bytes:
            size -= len(kept.popleft())
    return b"".join(kept)[-max_bytes:]


def run_bounded(
    cmd: list[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    merge_stderr: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ProcResult:
    """
    Run ``cmd`` without a shell, streaming output and keeping only the tail.

    On timeout the process is killed and the output captured so far is kept.
    Raises FileNotFoundError if the executable does not exist.
    """
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
    )
    captured: dict[str, bytes] = {}

    def pump(name: str, stream) -> None:
        captured[name] = tail_bytes(
            iter(lambda: stream.read(64 * 1024), b""), max_bytes
        )

    readers = [threading.Thread(target=pump, args=("out", process.stdout), daemon=True)]
    if not merge_stderr:
        readers.append(
            threading.Thread(target=pump, args=("err", process.stderr), daemon=True)
        )
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for reader in readers:
        reader.join(timeout=5)

    def decode(name: str) -> str:
        return captured.get(name, b"").decode("utf-8", errors="replace")

    return ProcResult(
        returncode=None if timed_out else process.returncode,
        stdout=decode("out"),
        stderr=decode("err"),
        timed_out=timed_out,
    )


def split_command(command: str) -> list[str]:
    """
    Split a command line into argv without invoking a shell.

    On Windows, backslashes in paths are preserved and the executable is
    resolved through PATH/PATHEXT so ``npm``/``ng`` (.cmd shims) work.
    """
    if os.name == "nt":
        args = [_unquote(a) for a in shlex.split(command, posix=False)]
    else:
        args = shlex.split(command)
    if not args:
        raise ValueError("empty command")
    resolved = shutil.which(args[0])
    if resolved:
        args[0] = resolved
    return args


def _unquote(arg: str) -> str:
    if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'":
        return arg[1:-1]
    return arg
