def redis_timeout_diff():
    return {
        "file": ".env",
        "diff": """--- a/.env
+++ b/.env
@@
-REDIS_TIMEOUT=1
+REDIS_TIMEOUT=5
""",
        "rationale": "Increase Redis timeout to reduce transient timeout errors under load."
    }

def redis_pooling_diff():
    return {
        "file": "app/config/redis.py",
        "diff": """--- a/app/config/redis.py
+++ b/app/config/redis.py
@@
-redis.Redis(host=host, port=port)
+redis.Redis(host=host, port=port, socket_timeout=5, max_connections=20)
""",
        "rationale": "Enable connection pooling and reasonable timeouts to improve reliability."
    }
