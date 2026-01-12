"""Production log fetching from various sources."""

import requests
from pathlib import Path
from typing import Optional, List
import subprocess


def fetch_logs_from_url(url: str, timeout: int = 30) -> Optional[str]:
    """
    Fetch logs from HTTP/HTTPS URL.

    Args:
        url: Log file URL
        timeout: Request timeout in seconds

    Returns:
        Log content as string, or None if failed
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Failed to fetch logs from {url}: {e}")
        return None


def fetch_logs_from_s3(bucket: str, key: str, profile: Optional[str] = None) -> Optional[str]:
    """
    Fetch logs from S3 bucket using AWS CLI.

    Args:
        bucket: S3 bucket name
        key: Object key (file path in bucket)
        profile: Optional AWS profile name

    Returns:
        Log content as string, or None if failed
    """
    try:
        cmd = ["aws", "s3", "cp", f"s3://{bucket}/{key}", "-"]

        if profile:
            cmd.extend(["--profile", profile])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Failed to fetch from S3: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print(f"S3 fetch timed out for s3://{bucket}/{key}")
        return None
    except FileNotFoundError:
        print("AWS CLI not found. Install from: https://aws.amazon.com/cli/")
        return None


def fetch_logs_from_file(path: str) -> Optional[str]:
    """
    Read logs from local file.

    Args:
        path: Local file path

    Returns:
        Log content as string, or None if failed
    """
    try:
        file_path = Path(path)
        if not file_path.exists():
            print(f"Log file not found: {path}")
            return None

        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"Failed to read log file {path}: {e}")
        return None


def fetch_logs_from_kubectl(namespace: str, pod: str, container: Optional[str] = None,
                            tail: int = 1000) -> Optional[str]:
    """
    Fetch logs from Kubernetes pod using kubectl.

    Args:
        namespace: Kubernetes namespace
        pod: Pod name
        container: Optional container name (for multi-container pods)
        tail: Number of lines to fetch (default: 1000)

    Returns:
        Log content as string, or None if failed
    """
    try:
        cmd = ["kubectl", "logs", pod, "-n", namespace, f"--tail={tail}"]

        if container:
            cmd.extend(["-c", container])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Failed to fetch kubectl logs: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print(f"kubectl logs fetch timed out for {namespace}/{pod}")
        return None
    except FileNotFoundError:
        print("kubectl not found. Install from: https://kubernetes.io/docs/tasks/tools/")
        return None


def fetch_logs_from_cloudwatch(log_group: str, log_stream: str,
                                profile: Optional[str] = None,
                                limit: int = 1000) -> Optional[str]:
    """
    Fetch logs from AWS CloudWatch using AWS CLI.

    Args:
        log_group: CloudWatch log group name
        log_stream: Log stream name
        profile: Optional AWS profile name
        limit: Max number of log events (default: 1000)

    Returns:
        Log content as string, or None if failed
    """
    try:
        cmd = [
            "aws", "logs", "get-log-events",
            "--log-group-name", log_group,
            "--log-stream-name", log_stream,
            "--limit", str(limit),
            "--output", "text",
            "--query", "events[*].message"
        ]

        if profile:
            cmd.extend(["--profile", profile])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Failed to fetch CloudWatch logs: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print(f"CloudWatch fetch timed out for {log_group}/{log_stream}")
        return None
    except FileNotFoundError:
        print("AWS CLI not found. Install from: https://aws.amazon.com/cli/")
        return None


def auto_detect_and_fetch(source: str) -> Optional[str]:
    """
    Auto-detect log source type and fetch accordingly.

    Supports:
    - HTTP/HTTPS URLs
    - S3 paths (s3://bucket/key)
    - Kubernetes (k8s://namespace/pod or k8s://namespace/pod/container)
    - CloudWatch (cw://log-group/log-stream)
    - Local files

    Args:
        source: Log source string

    Returns:
        Log content as string, or None if failed
    """
    source = source.strip()

    # HTTP/HTTPS URL
    if source.startswith(("http://", "https://")):
        return fetch_logs_from_url(source)

    # S3 path
    if source.startswith("s3://"):
        # Parse s3://bucket/key
        parts = source[5:].split("/", 1)
        if len(parts) == 2:
            return fetch_logs_from_s3(parts[0], parts[1])
        else:
            print(f"Invalid S3 path format: {source}")
            return None

    # Kubernetes
    if source.startswith("k8s://"):
        # Parse k8s://namespace/pod or k8s://namespace/pod/container
        parts = source[6:].split("/")
        if len(parts) == 2:
            return fetch_logs_from_kubectl(parts[0], parts[1])
        elif len(parts) == 3:
            return fetch_logs_from_kubectl(parts[0], parts[1], parts[2])
        else:
            print(f"Invalid k8s path format: {source}")
            return None

    # CloudWatch
    if source.startswith("cw://"):
        # Parse cw://log-group/log-stream
        parts = source[5:].split("/", 1)
        if len(parts) == 2:
            return fetch_logs_from_cloudwatch(parts[0], parts[1])
        else:
            print(f"Invalid CloudWatch path format: {source}")
            return None

    # Local file (default)
    return fetch_logs_from_file(source)


def fetch_multiple_sources(sources: List[str]) -> str:
    """
    Fetch logs from multiple sources and concatenate.

    Args:
        sources: List of log source strings

    Returns:
        Combined log content
    """
    all_logs = []

    for source in sources:
        print(f"Fetching logs from: {source}")
        logs = auto_detect_and_fetch(source)
        if logs:
            all_logs.append(f"\n{'='*60}\n")
            all_logs.append(f"SOURCE: {source}\n")
            all_logs.append(f"{'='*60}\n")
            all_logs.append(logs)
        else:
            print(f"Warning: Could not fetch logs from {source}")

    return "\n".join(all_logs)
