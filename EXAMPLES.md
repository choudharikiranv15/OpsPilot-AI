# OpsPilot Real-World Examples

## 🎯 What OpsPilot Does (In Plain English)

**OpsPilot is like having a senior SRE sitting next to you, analyzing production incidents in real-time.**

---

## 🚨 Scenario 1: API Server Crashed at 3 AM

### The Problem
Junior engineer wakes up to PagerDuty alert:
```
CRITICAL: API server crashed
Status: 503 Service Unavailable
Users affected: 10,000+
```

### Without OpsPilot (Old Way)
```bash
# Engineer manually does:
ssh prod-server-01
tail -f /var/log/app/error.log   # Reads 5000 lines manually
grep "ERROR" | grep "500"         # Finds 200 errors
# Now what? Which error caused the crash?
# Calls senior engineer at 3 AM 😴
# Time to diagnose: 30-60 minutes
```

### With OpsPilot (AI Way)
```bash
# Engineer simply runs:
opspilot analyze --log-source "s3://prod-logs/api-server.log" --deployment-analysis

# Gets in 90 seconds:
```

**Output**:
```
SEVERITY: P0
Total Errors: 347
First Seen: 2026-01-12 03:02:15
Occurrences: 128

Root Cause Hypothesis:
"Redis connection pool exhaustion causing cascading failures"
Confidence: 0.88

DEPLOYMENT CORRELATION DETECTED!
Commit [a7f3c21] deployed at 02:58 AM (4 minutes before errors)
File Changed: app/config/redis.py
Risk: HIGH (connection pool settings modified)

[!] IMMEDIATE ACTIONS (0-5 min):
1. Check Redis connection count
   Command: redis-cli info clients | grep connected_clients
   Risk: LOW | Time: 30 seconds

2. Restart application service
   Command: systemctl restart api-server
   Risk: MEDIUM | Time: 2 minutes
   Why: Clear stale connections and refresh connection pool

[~] SHORT-TERM FIXES (1-24 hours):
1. Update app/config/redis.py
   Change: max_connections=10 → max_connections=50
   Risk: LOW
   Why: Previous deploy reduced pool size, causing exhaustion

[+] LONG-TERM FIXES (1-4 weeks):
1. Implement circuit breaker pattern (2-3 days)
2. Add connection pool monitoring (1 day)
```

**Result**: Engineer fixes issue in 5 minutes, goes back to sleep! ✅

---

## 🔥 Scenario 2: Database Queries Timing Out

### The Problem
PM reports: "Users are complaining about slow checkout - it's timing out!"

### With OpsPilot
```bash
# DevOps engineer runs:
opspilot analyze --log-source "k8s://production/checkout-service"

# Gets diagnosis:
```

**Output**:
```
SEVERITY: P1
Total Errors: 89
First Seen: 2026-01-12 14:23:10

Root Cause Hypothesis:
"Database connection timeout due to missing connection pooling"
Confidence: 0.82

Error Patterns Detected:
- Database errors: psycopg2.OperationalError (45 times)
- Timeout errors: 23 occurrences
- HTTP 503: 21 requests

[!] IMMEDIATE ACTIONS (0-5 min):
1. Check database connection count
   Command: SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
   Risk: LOW | Time: 1 minute

[~] SHORT-TERM FIXES (1-24 hours):
1. Update database.py
   Add: max_overflow=10, pool_size=20, pool_timeout=30
   Why: Current config has no connection pooling

[v] VERIFICATION STEPS:
1. Monitor query response time (should drop below 500ms)
2. Check active connections (should stabilize below 50)
```

**Result**: Engineer adds connection pooling, issue resolved in 15 minutes! ✅

---

## 💾 Scenario 3: Out of Memory Errors

### The Problem
Server keeps restarting with OOM (Out of Memory) errors

### With OpsPilot
```bash
opspilot analyze --log-source "cw://prod-app/stream-2024-01-12"

# Diagnosis:
```

**Output**:
```
SEVERITY: P0
Total Errors: 156
First Seen: 2026-01-12 11:45:23

Root Cause Hypothesis:
"Memory leak in image processing service due to unclosed file handles"
Confidence: 0.91

Error Patterns:
- Memory errors: MemoryError, "out of memory" (12 times)
- HTTP 500: 89 requests
- Process crashes: 3 times

[!] IMMEDIATE ACTIONS (0-5 min):
1. Restart service to free memory
   Command: kubectl rollout restart deployment/image-processor
   Risk: MEDIUM | Time: 2 minutes

2. Increase memory limit temporarily
   Command: kubectl set resources deployment/image-processor --limits=memory=4Gi
   Risk: LOW | Time: 1 minute

[~] SHORT-TERM FIXES (1-24 hours):
1. Update image_processor.py
   Add: with open() context managers to auto-close files
   Why: File handles not being closed, causing memory leak

[+] LONG-TERM FIXES (1-4 weeks):
1. Implement memory profiling (1 day)
2. Add memory usage alerts (1 day)
3. Optimize image processing pipeline (1 week)
```

**Result**: Engineer restarts service, patches code, issue fixed! ✅

---

## 🌐 Scenario 4: Microservices Communication Failure

### The Problem
Service A can't talk to Service B - random 502 errors

### With OpsPilot
```bash
opspilot analyze \
  --log-source "k8s://production/service-a" \
  --deployment-analysis \
  --since-hours 6

# Diagnosis:
```

**Output**:
```
SEVERITY: P1
Total Errors: 234

Root Cause Hypothesis:
"Service mesh configuration error after recent Istio upgrade"
Confidence: 0.79

DEPLOYMENT CORRELATION DETECTED!
Commit [f9d4e12] at 10:15 AM (2 hours before errors)
File Changed: k8s/istio-config.yaml
Risk: HIGH (service mesh routing rules modified)

Error Patterns:
- HTTP 502: 178 requests
- Connection refused: 56 times

[!] IMMEDIATE ACTIONS (0-5 min):
1. Check Istio virtual service config
   Command: kubectl get virtualservice service-b -o yaml
   Risk: LOW | Time: 30 seconds

2. Rollback Istio config
   Command: kubectl rollout undo deployment/istio-proxy
   Risk: MEDIUM | Time: 2 minutes

[~] SHORT-TERM FIXES (1-24 hours):
1. Fix istio-config.yaml
   Change: Fix destination port from 8080 to 8081
   Why: Recent deploy changed service port but not Istio config
```

**Result**: Engineer rolls back config, service restored in 3 minutes! ✅

---

## 📊 Scenario 5: Performance Degradation

### The Problem
API response time went from 200ms to 5 seconds overnight

### With OpsPilot
```bash
opspilot analyze \
  --log-source "https://logs.company.com/api-prod.log" \
  --deployment-analysis

# Diagnosis:
```

**Output**:
```
SEVERITY: P2
Total Errors: 45

Root Cause Hypothesis:
"N+1 query problem introduced in recent ORM code change"
Confidence: 0.86

DEPLOYMENT CORRELATION DETECTED!
Commit [c3a8f56] at 08:30 AM (30 minutes before slowdown)
File Changed: app/models/user.py
Risk: MEDIUM (database query logic modified)

Error Patterns:
- Timeout errors: 45 occurrences
- Slow queries (>1s): detected in logs

[~] SHORT-TERM FIXES (1-24 hours):
1. Update user.py
   Change: Use eager loading (.join()) instead of lazy loading
   Example: User.query.join(Profile).all()
   Why: Current code triggers 1 query per user (N+1 problem)

[+] LONG-TERM FIXES (1-4 weeks):
1. Add query performance monitoring (2 days)
2. Implement query result caching (1 week)
3. Add database query analyzer to CI/CD (3 days)
```

**Result**: Engineer fixes N+1 query, response time back to 200ms! ✅

---

## 🎓 Can a Junior Engineer Use This? YES!

### Junior Engineer Skills Required:
- ✅ Know how to run terminal commands
- ✅ Basic understanding of logs
- ✅ Can read Python/JavaScript (optional)

### What Junior Engineer DOESN'T Need to Know:
- ❌ How to debug complex distributed systems
- ❌ How to read 10,000 lines of logs
- ❌ How to correlate errors with deployments
- ❌ How to identify root causes
- ❌ How to suggest fixes

**OpsPilot does all the hard parts!**

---

## 🤖 How It Works (Under the Hood)

### Multi-Agent AI System

```
1. PLANNER Agent
   ├─ Reads logs, environment, dependencies
   ├─ Forms hypothesis about root cause
   └─ Confidence score: 0.0 - 1.0

2. VERIFIER Agent
   ├─ Collects evidence from multiple sources
   ├─ Tests hypothesis against evidence
   └─ Confirms or rejects hypothesis

3. FIXER Agent
   ├─ Generates code fixes (diffs)
   ├─ Suggests configuration changes
   └─ Provides immediate commands

4. REMEDIATION Agent
   ├─ Creates 3-tier action plan
   ├─ Assesses risk for each action
   └─ Estimates time for each fix
```

### Intelligence Features

**Error Pattern Recognition**:
- Detects HTTP codes (4xx, 5xx)
- Finds exceptions (ConnectionError, TimeoutError, etc.)
- Identifies database errors (psycopg2, redis)
- Spots memory issues (OOM, MemoryError)
- Recognizes timeout patterns

**Severity Classification**:
- **P0**: 10+ 5xx errors OR memory errors
- **P1**: 5+ 5xx errors OR database errors
- **P2**: Some 5xx errors OR 5+ timeouts
- **P3**: Only 4xx errors (client errors)

**Deployment Correlation**:
- Analyzes Git commit history
- Finds commits within ±2 hours of errors
- Identifies high-risk changes (migrations, auth, config)
- Assesses deployment risk level

**Timeline Analysis**:
- Extracts error timestamps
- Tracks first/last occurrence
- Calculates error frequency
- Identifies error clusters

---

## 🎯 Use Cases by Role

### DevOps Engineer
```bash
# Daily incident response
opspilot analyze --log-source "s3://prod-logs/today.log"

# Post-mortem analysis
opspilot analyze --log-source "s3://incident-001.log" --deployment-analysis
```

### SRE (Site Reliability Engineer)
```bash
# Multi-service analysis
opspilot analyze --log-source "k8s://prod/api-gateway"
opspilot analyze --log-source "k8s://prod/payment-service"

# Correlation with recent changes
opspilot analyze --deployment-analysis --since-hours 48
```

### Backend Developer
```bash
# Debug local issues
cd /path/to/my/project
opspilot analyze

# Test production readiness
opspilot analyze --log-source "./logs/load_test.log"
```

### Engineering Manager
```bash
# Get executive summary
opspilot analyze --log-source "s3://prod-logs/incident.log" --json

# Output includes:
# - Severity (P0/P1/P2/P3)
# - Root cause (plain English)
# - Time estimates for fixes
# - Risk assessment
```

---

## 📈 Success Metrics

### Before OpsPilot:
- **Time to diagnose**: 30-60 minutes
- **Requires**: Senior engineer involvement
- **Process**: Manual log reading, guesswork
- **Accuracy**: Variable (depends on engineer experience)

### After OpsPilot:
- **Time to diagnose**: 2-5 minutes ⚡
- **Requires**: Any engineer can use
- **Process**: Automated AI analysis
- **Accuracy**: 80-90% (AI confidence scores)

---

## 🚀 Getting Started

### Installation
```bash
pip install opspilot
ollama pull llama3
```

### First Analysis
```bash
# Analyze your current project
cd /your/project
opspilot analyze

# That's it! 🎉
```

### Advanced Usage
```bash
# Production incident from S3
opspilot analyze --log-source "s3://prod-logs/app.log"

# With deployment correlation
opspilot analyze --log-source "s3://prod-logs/app.log" --deployment-analysis

# From Kubernetes
opspilot analyze --log-source "k8s://production/api-server"

# From CloudWatch
opspilot analyze --log-source "cw://prod-app/log-stream"

# From URL
opspilot analyze --log-source "https://logs.example.com/app.log"
```

---

## 💡 Pro Tips

### 1. Use with CI/CD
```yaml
# GitHub Actions
- name: Auto-diagnose on failure
  if: failure()
  run: |
    opspilot analyze --log-source "./build.log" --json > diagnosis.json
```

### 2. Combine with Monitoring
```bash
# When alert fires, automatically analyze
curl https://api.prod/logs | opspilot analyze --log-source -
```

### 3. Team Knowledge Sharing
```bash
# Save diagnosis for team
opspilot analyze --json > incident-report.json
git add incident-report.json && git commit -m "Post-mortem analysis"
```

---

## 🎓 Learning Resources

1. **Video Tutorial**: [Coming Soon]
2. **Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md)
3. **Blog Post**: [Coming Soon]
4. **Community Discord**: [Coming Soon]

---

## 🤝 Contributing

Want to make OpsPilot better?
- Add support for more log sources
- Improve pattern recognition
- Add more LLM providers
- Translate to other languages

See [CONTRIBUTING.md](CONTRIBUTING.md) for details!
