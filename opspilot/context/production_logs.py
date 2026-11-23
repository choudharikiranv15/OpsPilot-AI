"""Fetch logs from an explicit source given with ``--log-source``.

Supported sources:

* local file path (any extension)
* ``http://`` / ``https://`` URL
* ``s3://bucket/key`` (requires the AWS CLI)
* ``k8s://namespace/pod[/container]`` (requires kubectl)
* ``cw://LOG_GROUP::LOG_STREAM`` (requires the AWS CLI). The legacy form
  ``cw://group/stream`` is still accepted when the group has no ``/``.

Every source is bounded to ``MAX_FETCH_BYTES`` (the most recent part is
kept), identifiers are validated before being passed to external CLIs, and
failures raise ``LogSourceError`` with an actionable message.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from collections import deque
from pathlib import Path

import requests

from opspilot.context.logs import read_tail
from opspilot.exceptions import OpsPilotError

log = logging.getLogger("opspilot.logs")

MAX_FETCH_BYTES = 5 * 1024 * 1024
HTTP_TIMEOUT = 30
CLI_TIMEOUT = 60
K8S_TAIL_LINES = 2000
CW_EVENT_LIMIT = 2000

_K8S_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
_S3_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
_CW_GROUP = re.compile(r"^[A-Za-z0-9_./#\-]{1,512}$")
_CW_STREAM = re.compile(r"^[^:*]{1,512}$")


class LogSourceError(OpsPilotError):
    """A log source could not be parsed or fetched."""


def fetch_logs_from_file(path: str) -> str:
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise LogSourceError(f"Log file not found: {path}")
    try:
        return read_tail(file_path, MAX_FETCH_BYTES)
    except OSError as e:
        raise LogSourceError(f"Cannot read log file {path}", str(e)) from e


def fetch_logs_from_url(url: str, timeout: int = HTTP_TIMEOUT) -> str:
    if url.startswith("http://"):
        log.warning("Fetching logs over unencrypted http://")
    try:
        with requests.get(url, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            return _tail_of_stream(response.iter_content(chunk_size=64 * 1024))
    except requests.RequestException as e:
        raise LogSourceError(f"Failed to fetch logs from {url}", str(e)) from e


def fetch_logs_from_s3(bucket: str, key: str, profile: str | None = None) -> str:
    if not _S3_BUCKET.match(bucket) or not key or key.startswith("-"):
        raise LogSourceError(f"Invalid S3 location: s3://{bucket}/{key}")
    cmd = ["aws", "s3", "cp", f"s3://{bucket}/{key}", "-"]
    if profile:
        cmd += ["--profile", profile]
    return _run_cli(cmd, "AWS CLI", "https://aws.amazon.com/cli/")


def fetch_logs_from_kubectl(
    namespace: str, pod: str, container: str | None = None, tail: int = K8S_TAIL_LINES
) -> str:
    for label, value in (
        ("namespace", namespace),
        ("pod", pod),
        ("container", container),
    ):
        if value is not None and not _K8S_NAME.match(value):
            raise LogSourceError(f"Invalid Kubernetes {label} name: {value!r}")
    cmd = ["kubectl", "logs", "-n", namespace, f"--tail={tail}"]
    if container:
        cmd += ["-c", container]
    cmd += ["--", pod]
    return _run_cli(cmd, "kubectl", "https://kubernetes.io/docs/tasks/tools/")


def fetch_logs_from_cloudwatch(
    log_group: str,
    log_stream: str,
    profile: str | None = None,
    limit: int = CW_EVENT_LIMIT,
) -> str:
    if not _CW_GROUP.match(log_group) or log_group.startswith("-"):
        raise LogSourceError(f"Invalid CloudWatch log group: {log_group!r}")
    if not _CW_STREAM.match(log_stream) or log_stream.startswith("-"):
        raise LogSourceError(f"Invalid CloudWatch log stream: {log_stream!r}")
    cmd = [
        "aws",
        "logs",
        "get-log-events",
        f"--log-group-name={log_group}",
        f"--log-stream-name={log_stream}",
        "--limit",
        str(limit),
        "--output",
        "text",
        "--query",
        "events[*].message",
    ]
    if profile:
        cmd += ["--profile", profile]
    return _run_cli(cmd, "AWS CLI", "https://aws.amazon.com/cli/")


def parse_cloudwatch_source(spec: str) -> tuple[str, str]:
    """Split the part after ``cw://`` into (group, stream)."""
    if "::" in spec:
        group, stream = spec.split("::", 1)
    elif "/" in spec:
        group, stream = spec.split("/", 1)
    else:
        group, stream = spec, ""
    if not group or not stream:
        raise LogSourceError(
            f"Invalid CloudWatch source: cw://{spec}",
            "use cw://LOG_GROUP::LOG_STREAM (e.g. cw:///aws/lambda/fn::2026/01/01/abc)",
        )
    return group, stream


def auto_detect_and_fetch(source: str) -> str:
    """Fetch logs from ``source``; raises LogSourceError on any failure."""
    source = source.strip()
    if source.startswith(("http://", "https://")):
        return fetch_logs_from_url(source)
    if source.startswith("s3://"):
        bucket, _, key = source[5:].partition("/")
        return fetch_logs_from_s3(bucket, key)
    if source.startswith("k8s://"):
        parts = source[6:].split("/")
        if len(parts) not in (2, 3) or not all(parts):
            raise LogSourceError(
                f"Invalid Kubernetes source: {source}",
                "use k8s://NAMESPACE/POD or k8s://NAMESPACE/POD/CONTAINER",
            )
        return fetch_logs_from_kubectl(*parts)
    if source.startswith("cw://"):
        return fetch_logs_from_cloudwatch(*parse_cloudwatch_source(source[5:]))
    return fetch_logs_from_file(source)


def _tail_of_stream(chunks) -> str:
    kept: deque[bytes] = deque()
    size = 0
    for chunk in chunks:
        if not chunk:
            continue
        kept.append(chunk)
        size += len(chunk)
        while size - len(kept[0]) >= MAX_FETCH_BYTES:
            size -= len(kept.popleft())
    data = b"".join(kept)[-MAX_FETCH_BYTES:]
    return data.decode("utf-8", errors="replace")


def _run_cli(cmd: list[str], tool: str, install_url: str) -> str:
    """Run an external CLI; stream stdout keeping only the last MAX_FETCH_BYTES."""
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise LogSourceError(
            f"{tool} not found", f"install it from {install_url}"
        ) from None

    result: dict[str, object] = {}
    stderr_head: list[bytes] = []

    def pump_stdout() -> None:
        result["stdout"] = _tail_of_stream(
            iter(lambda: process.stdout.read(64 * 1024), b"")
        )

    def pump_stderr() -> None:
        for chunk in iter(lambda: process.stderr.read(64 * 1024), b""):
            if sum(map(len, stderr_head)) < 64 * 1024:
                stderr_head.append(chunk)

    readers = [
        threading.Thread(target=pump_stdout, daemon=True),
        threading.Thread(target=pump_stderr, daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=CLI_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise LogSourceError(f"{tool} timed out after {CLI_TIMEOUT}s") from None
    finally:
        for reader in readers:
            reader.join(timeout=5)
    if process.returncode != 0:
        message = b"".join(stderr_head).decode("utf-8", errors="replace").strip()
        raise LogSourceError(
            f"{tool} failed (exit {process.returncode})", message[:500]
        )
    return str(result.get("stdout", ""))
