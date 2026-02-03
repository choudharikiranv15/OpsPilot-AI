# OpsPilot-AI Deployment Guide

## 🎯 Deployment Options

OpsPilot-AI can be deployed in 3 ways depending on your use case.

---

## Option 1: PyPI Package (Recommended for End Users)

### For Users to Install

```bash
# Install from PyPI
pip install opspilot-ai

# Install Ollama (required for LLM)
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Windows
# Download from https://ollama.ai/download

# Pull the LLM model
ollama pull llama3

# Verify installation
opspilot --help
```

### Usage Examples

```bash
# Analyze local project
cd /path/to/your/project
opspilot analyze

# Analyze production logs from S3
opspilot analyze --log-source "s3://my-bucket/logs/app.log"

# Analyze with deployment correlation
opspilot analyze --log-source "s3://prod-logs/api.log" --deployment-analysis --since-hours 24

# Analyze Kubernetes pod logs
opspilot analyze --log-source "k8s://production/api-server"

# Analyze CloudWatch logs
opspilot analyze --log-source "cw://prod-app/stream-1"

# Analyze from URL
opspilot analyze --log-source "https://logs.example.com/app.log"
```

---

## Option 2: Docker Container (For CI/CD Pipelines)

### Build Docker Image

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install Ollama
RUN apt-get update && apt-get install -y curl git && \
    curl -fsSL https://ollama.ai/install.sh | sh

# Install OpsPilot
COPY . /app
WORKDIR /app
RUN pip install -e .

# Pull LLM model
RUN ollama serve & sleep 5 && ollama pull llama3

ENTRYPOINT ["opspilot"]
CMD ["--help"]
```

### Build and Run

```bash
# Build image
docker build -t opspilot:latest .

# Run analysis
docker run -v $(pwd):/workspace opspilot:latest analyze

# Run with production logs (mount credentials)
docker run \
  -v ~/.aws:/root/.aws \
  -v $(pwd):/workspace \
  opspilot:latest analyze --log-source "s3://prod-logs/app.log"
```

### Use in CI/CD (GitHub Actions)

```yaml
# .github/workflows/incident-analysis.yml
name: Auto-Diagnose Production Incidents

on:
  schedule:
    - cron: '*/15 * * * *'  # Run every 15 minutes
  workflow_dispatch:

jobs:
  diagnose:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Run OpsPilot
        uses: docker://ghcr.io/yourusername/opspilot:latest
        with:
          args: |
            analyze
            --log-source "s3://prod-logs/app-${{ github.run_number }}.log"
            --deployment-analysis
            --json

      - name: Post to Slack if P0/P1
        if: steps.diagnose.outputs.severity == 'P0' || steps.diagnose.outputs.severity == 'P1'
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "🚨 ${{ steps.diagnose.outputs.severity }} Incident Detected",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Hypothesis:* ${{ steps.diagnose.outputs.hypothesis }}"
                  }
                }
              ]
            }
```

---

## Option 3: SaaS Web Dashboard (Advanced)

### Architecture

```
┌─────────────┐
│   Frontend  │ (React)
│  Dashboard  │
└──────┬──────┘
       │
       v
┌─────────────┐
│   Backend   │ (FastAPI)
│   API       │
└──────┬──────┘
       │
       v
┌─────────────┐
│  OpsPilot   │ (CLI as Library)
│   Engine    │
└──────┬──────┘
       │
       v
┌─────────────┐
│   Ollama    │ (LLM Server)
│   Service   │
└─────────────┘
```

### Backend API (FastAPI)

```python
# api/main.py
from fastapi import FastAPI, BackgroundTasks
from opspilot.agents.planner import plan
from opspilot.agents.verifier import verify
from opspilot.agents.remediation import generate_remediation_plan
from opspilot.tools import collect_evidence
from opspilot.context.production_logs import auto_detect_and_fetch

app = FastAPI()

@app.post("/api/v1/analyze")
async def analyze_incident(
    log_source: str,
    deployment_analysis: bool = False,
    background_tasks: BackgroundTasks = None
):
    """Analyze production incident from logs."""

    # Fetch logs
    logs = auto_detect_and_fetch(log_source)

    # Collect evidence
    context = {"logs": logs}
    evidence = collect_evidence(context)

    # Generate hypothesis
    plan_result = plan(context)

    # Verify hypothesis
    verdict = verify(plan_result["hypothesis"], evidence)

    # Generate remediation plan
    remediation = generate_remediation_plan(
        plan_result["hypothesis"],
        evidence,
        []  # suggestions from fixer agent
    )

    return {
        "severity": evidence.get("severity"),
        "hypothesis": plan_result["hypothesis"],
        "confidence": verdict["confidence"],
        "remediation_plan": remediation,
        "evidence": evidence
    }
```

### Deploy to Cloud

```bash
# Deploy to Google Cloud Run
gcloud run deploy opspilot-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2

# Deploy to AWS Lambda (with Docker)
aws ecr create-repository --repository-name opspilot
docker tag opspilot:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/opspilot:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/opspilot:latest

# Create Lambda function
aws lambda create-function \
  --function-name opspilot-analyzer \
  --package-type Image \
  --code ImageUri=123456789.dkr.ecr.us-east-1.amazonaws.com/opspilot:latest \
  --role arn:aws:iam::123456789:role/lambda-execution \
  --timeout 300 \
  --memory-size 2048
```

---

## 🔒 Security Considerations

### 1. AWS Credentials (for S3/CloudWatch)

```bash
# Users should configure AWS CLI
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

### 2. Kubernetes Access (for kubectl)

```bash
# Users need kubeconfig
export KUBECONFIG=~/.kube/config

# Or use service account
kubectl create serviceaccount opspilot
kubectl create clusterrolebinding opspilot --clusterrole=view --serviceaccount=default:opspilot
```

### 3. Ollama API Access

```bash
# For remote Ollama server
export OLLAMA_HOST="http://ollama-server:11434"
```

---

## 📊 Monitoring OpsPilot Usage

### Log Analysis Metrics

```python
# Add to cli.py for telemetry
import json
import time

def log_usage(event_type, metadata):
    """Log usage metrics for analytics."""
    with open("~/.opspilot/usage.jsonl", "a") as f:
        f.write(json.dumps({
            "timestamp": time.time(),
            "event": event_type,
            "metadata": metadata
        }) + "\n")

# Usage
log_usage("analysis_complete", {
    "severity": evidence.get("severity"),
    "confidence": verdict.get("confidence"),
    "duration_seconds": analysis_duration
})
```

---

## 🚀 Publishing to PyPI

### Step 1: Prepare Package

```bash
# Install build tools
pip install build twine

# Build package
python -m build

# Test with TestPyPI first
twine upload --repository testpypi dist/*

# Install from TestPyPI to test
pip install --index-url https://test.pypi.org/simple/ opspilot
```

### Step 2: Publish to PyPI

```bash
# Upload to production PyPI
twine upload dist/*

# Users can now install
pip install opspilot
```

---

## 📖 User Documentation

Create these files for users:

1. **README.md** - Quick start guide
2. **ARCHITECTURE.md** - How it works internally
3. **EXAMPLES.md** - Real-world usage examples
4. **API.md** - For SaaS deployment
5. **TROUBLESHOOTING.md** - Common issues

---

## 🎯 Target Audiences

### 1. Individual Developers
- Install via pip
- Use locally for their projects
- Quick incident diagnosis

### 2. Small Teams (5-20 engineers)
- Docker container in CI/CD
- Automated incident detection
- Slack/email notifications

### 3. Large Organizations (100+ engineers)
- SaaS deployment with web dashboard
- Centralized incident analysis
- Multi-team access with RBAC

---

## 📈 Growth Strategy

### Phase 1: Open Source Release (Month 1-2)
- Publish to GitHub
- Publish to PyPI
- Create demo video
- Post on Hacker News, Reddit r/devops

### Phase 2: Community Building (Month 3-6)
- Add GitHub Actions integration
- Support more log sources (Datadog, Splunk)
- Add more LLM providers (OpenAI, Anthropic)
- Create plugins for IDEs (VSCode, JetBrains)

### Phase 3: Enterprise Features (Month 6-12)
- Web dashboard (React + FastAPI)
- Team collaboration features
- SSO/RBAC integration
- Custom model fine-tuning
- SLA guarantees

---

## 💰 Monetization Options (Future)

### Free Tier
- Local CLI usage
- Up to 100 analyses/month
- Community support

### Pro Tier ($29/month)
- Unlimited analyses
- Priority support
- Advanced LLM models
- Custom integrations

### Enterprise Tier ($499/month)
- Self-hosted option
- SLA guarantees
- Custom model training
- Dedicated support
- Multi-region deployment

---

## 🛠️ Next Steps

1. **Immediate** (This Week):
   - ✅ Create setup.py
   - ✅ Write deployment documentation
   - ☐ Add unit tests
   - ☐ Create demo video

2. **Short-term** (Next 2 Weeks):
   - ☐ Publish to PyPI
   - ☐ Create GitHub repository (public)
   - ☐ Write comprehensive README
   - ☐ Add CI/CD for automated testing

3. **Long-term** (Next 2 Months):
   - ☐ Build web dashboard
   - ☐ Add more LLM providers
   - ☐ Create VSCode extension
   - ☐ Support more log sources
