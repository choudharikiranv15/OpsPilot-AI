"""Redis-based memory system for OpsPilot with user isolation."""

import json
import hashlib
import time
import os
from typing import Dict, List, Optional
from datetime import datetime

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisMemory:
    """Redis-based memory with automatic TTL and user isolation."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ttl_days: Optional[int] = None
    ):
        """
        Initialize Redis connection.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
            ttl_days: Days to keep incidents (default: from env or 30)
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package not installed. Install with: pip install redis"
            )

        self.redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True
        )

        # TTL from environment variable or default
        if ttl_days is None:
            ttl_days = int(os.getenv("OPSPILOT_REDIS_TTL_DAYS", "30"))

        self.ttl_seconds = ttl_days * 24 * 60 * 60

    @staticmethod
    def _get_project_hash(project_root: str) -> str:
        """
        Generate unique hash for project (user isolation).

        Args:
            project_root: Absolute path to project

        Returns:
            16-character hash
        """
        return hashlib.sha256(project_root.encode()).hexdigest()[:16]

    def save_incident(
        self,
        project_root: str,
        hypothesis: str,
        confidence: float,
        severity: str,
        error_patterns: Dict,
        evidence: Dict,
        remediation: Optional[Dict] = None
    ) -> str:
        """
        Save incident analysis to Redis with TTL.

        Args:
            project_root: Project path (for user isolation)
            hypothesis: Root cause hypothesis
            confidence: Confidence score (0.0 - 1.0)
            severity: P0/P1/P2/P3
            error_patterns: Detected error patterns
            evidence: Collected evidence
            remediation: Remediation plan (optional)

        Returns:
            incident_key: Unique key for this incident
        """
        project_hash = self._get_project_hash(project_root)
        timestamp = int(time.time())

        # Create incident data
        incident_data = {
            "project": project_root,
            "hypothesis": hypothesis,
            "confidence": confidence,
            "severity": severity,
            "error_patterns": error_patterns,
            "evidence": evidence,
            "remediation": remediation,
            "timestamp": timestamp,
            "created_at": datetime.fromtimestamp(timestamp).isoformat()
        }

        # Generate incident key
        incident_key = f"incident:{project_hash}:{timestamp}"

        # Store incident with TTL
        self.redis_client.setex(
            incident_key,
            self.ttl_seconds,
            json.dumps(incident_data)
        )

        # Add to similarity index (sorted set by confidence)
        similarity_key = f"incidents:similar:{project_hash}"
        self.redis_client.zadd(
            similarity_key,
            {incident_key: confidence}
        )
        self.redis_client.expire(similarity_key, self.ttl_seconds)

        # Add to severity index
        severity_key = f"incidents:severity:{project_hash}:{severity}"
        self.redis_client.sadd(severity_key, incident_key)
        self.redis_client.expire(severity_key, self.ttl_seconds)

        return incident_key

    def find_similar_issues(
        self,
        project_root: str,
        min_confidence: float = 0.6,
        limit: int = 5
    ) -> List[Dict]:
        """
        Find similar incidents for a project (user-isolated).

        Args:
            project_root: Project path
            min_confidence: Minimum confidence threshold
            limit: Max number of results

        Returns:
            List of similar incidents, sorted by confidence (desc)
        """
        project_hash = self._get_project_hash(project_root)
        similarity_key = f"incidents:similar:{project_hash}"

        # Get top incidents by confidence (sorted set)
        incident_keys = self.redis_client.zrevrangebyscore(
            similarity_key,
            max=1.0,
            min=min_confidence,
            start=0,
            num=limit
        )

        # Fetch incident data
        incidents = []
        for key in incident_keys:
            data = self.redis_client.get(key)
            if data:
                incidents.append(json.loads(data))

        return incidents

    def get_incidents_by_severity(
        self,
        project_root: str,
        severity: str
    ) -> List[Dict]:
        """
        Get all incidents of a specific severity.

        Args:
            project_root: Project path
            severity: P0/P1/P2/P3

        Returns:
            List of incidents
        """
        project_hash = self._get_project_hash(project_root)
        severity_key = f"incidents:severity:{project_hash}:{severity}"

        incident_keys = self.redis_client.smembers(severity_key)

        incidents = []
        for key in incident_keys:
            data = self.redis_client.get(key)
            if data:
                incidents.append(json.loads(data))

        return incidents

    def record_llm_metrics(
        self,
        provider: str,
        success: bool,
        latency_ms: float
    ):
        """
        Record LLM provider performance metrics.

        Args:
            provider: Provider name (OllamaProvider, OpenRouterProvider, etc.)
            success: Whether call succeeded
            latency_ms: Response time in milliseconds
        """
        metrics_key = f"llm:health:{provider}"

        if success:
            self.redis_client.hincrby(metrics_key, "success_count", 1)
            self.redis_client.hset(metrics_key, "last_success", int(time.time()))
        else:
            self.redis_client.hincrby(metrics_key, "failure_count", 1)

        # Update average latency (moving average)
        current_avg = float(self.redis_client.hget(metrics_key, "avg_latency_ms") or 0)
        total_calls = int(self.redis_client.hget(metrics_key, "success_count") or 0)

        if total_calls > 0:
            new_avg = ((current_avg * (total_calls - 1)) + latency_ms) / total_calls
            self.redis_client.hset(metrics_key, "avg_latency_ms", new_avg)

        # Set TTL (refresh metrics every hour)
        self.redis_client.expire(metrics_key, 3600)

    def get_llm_health(self, provider: str) -> Dict:
        """
        Get health metrics for LLM provider.

        Args:
            provider: Provider name

        Returns:
            Dict with success_count, failure_count, avg_latency_ms
        """
        metrics_key = f"llm:health:{provider}"
        metrics = self.redis_client.hgetall(metrics_key)

        return {
            "success_count": int(metrics.get("success_count", 0)),
            "failure_count": int(metrics.get("failure_count", 0)),
            "avg_latency_ms": float(metrics.get("avg_latency_ms", 0)),
            "last_success": int(metrics.get("last_success", 0))
        }

    def clear_project_memory(self, project_root: str):
        """
        Clear all incidents for a project (useful for testing).

        Args:
            project_root: Project path
        """
        project_hash = self._get_project_hash(project_root)

        # Delete similarity index
        self.redis_client.delete(f"incidents:similar:{project_hash}")

        # Delete severity indexes
        for severity in ["P0", "P1", "P2", "P3"]:
            severity_key = f"incidents:severity:{project_hash}:{severity}"
            incident_keys = self.redis_client.smembers(severity_key)

            # Delete individual incidents
            for key in incident_keys:
                self.redis_client.delete(key)

            # Delete severity index
            self.redis_client.delete(severity_key)

    def health_check(self) -> bool:
        """
        Check if Redis is available.

        Returns:
            True if Redis is reachable
        """
        try:
            return self.redis_client.ping()
        except Exception:
            return False


# Fallback to file-based memory if Redis unavailable
def get_memory_backend(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    fallback_to_file: bool = True
):
    """
    Get memory backend (Redis or file-based fallback).

    Args:
        redis_host: Redis host
        redis_port: Redis port
        fallback_to_file: Use file-based storage if Redis unavailable

    Returns:
        Memory backend instance
    """
    if REDIS_AVAILABLE:
        try:
            memory = RedisMemory(host=redis_host, port=redis_port)
            if memory.health_check():
                return memory
        except Exception as e:
            print(f"[WARNING] Redis unavailable: {e}")

    if fallback_to_file:
        print("[INFO] Using file-based memory (Redis unavailable)")
        from opspilot.memory import load_memory, save_memory
        return None  # Use existing file-based system

    raise RuntimeError("Redis unavailable and fallback disabled")
