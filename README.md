# OpsPilot 🤖

> An intelligent agentic AI CLI tool for automated incident analysis and error resolution

OpsPilot is your AI-powered Site Reliability Engineer that analyzes your projects, identifies runtime issues, and suggests safe fixes—all through a simple command-line interface.

---

## 🎯 What is OpsPilot?

OpsPilot uses a **multi-agent AI architecture** to understand your project's context, form hypotheses about runtime issues, and provide evidence-based fix recommendations. Think of it as having an experienced SRE on your team, available 24/7.

### Key Capabilities

- **🔍 Intelligent Context Gathering** - Automatically analyzes logs, environment variables, Docker configs, dependencies, and project structure
- **🧠 Multi-Agent Architecture** - 4 specialized agents (Planner, Verifier, Fixer, Remediation) working collaboratively
- **🌐 Multi-Provider LLM Support** - Automatic fallback across Ollama, OpenRouter, Gemini, and HuggingFace
- **✅ Evidence-Based Verification** - Validates hypotheses with collected evidence and confidence scoring
- **🛠️ Safe Fix Suggestions** - Provides dry-run suggestions with detailed rationale (never auto-applies changes)
- **💾 Redis-Based Memory** - Auto-expiring incident history with user isolation and sub-second lookups
- **🚨 Severity Classification** - Automatic P0/P1/P2/P3 incident prioritization
- **☁️ Production Log Fetching** - S3, Kubernetes, CloudWatch, and HTTP endpoint support
- **📊 Deployment Correlation** - Links incidents to recent Git deployments for faster root cause analysis

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- At least ONE of the following LLM providers:
  - [Ollama](https://ollama.ai/) (local, free, recommended)
  - Google Gemini API key (free tier)
  - OpenRouter API key (free models available)
  - HuggingFace API token (free tier)

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/opspilot.git
cd opspilot

# Basic installation
pip install -e .

# With Redis support (recommended for production)
pip install -e ".[redis]"

# With all integrations (Redis + AWS + Kubernetes)
pip install -e ".[all]"
```

### LLM Setup

**Option 1: Ollama (Recommended - Local & Free)**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull Llama 3 model
ollama pull llama3
```

**Option 2: Cloud Providers (FREE tiers)**
```bash
# Copy environment template
cp .env.example .env

# Add your API keys to .env
# GOOGLE_API_KEY=your-key-here
# OPENROUTER_API_KEY=your-key-here
# HUGGINGFACE_API_KEY=your-key-here
```

See [FREE_LLM_SETUP.md](FREE_LLM_SETUP.md) for detailed setup instructions.

### Usage

Navigate to your project directory and run:

```bash
# Basic analysis
opspilot analyze

# Analyze with production logs from S3
opspilot analyze --log-source s3://my-bucket/logs/app.log

# Analyze with deployment correlation
opspilot analyze --deployment-analysis --since-hours 48

# JSON output for automation
opspilot analyze --json --mode quick

# Verbose output for debugging
opspilot analyze --verbose --debug
```

**Example Output:**

```
Similar issues detected from past runs:
- Redis connection issue caused by network or Redis server downtime (confidence 0.8)

OpsPilot initialized
Project detected: /your/project

Planner Agent reasoning...
Hypothesis: Redis connection issue
Confidence: 0.9

Evidence collected:
{'log_errors': {'ERROR': 1, 'Timeout': 1}, 'uses_redis': True}

Verifying hypothesis...
Supported: True
Confidence: 0.8
Reason: The presence of Redis connection-related errors (Timeout) and the system's use of Redis support the hypothesis.

Generating safe fix suggestions (dry-run)...

File: .env
Increase Redis timeout to reduce transient timeout errors under load.
--- a/.env
+++ b/.env
@@
-REDIS_TIMEOUT=1
+REDIS_TIMEOUT=5

File: app/config/redis.py
Enable connection pooling and reasonable timeouts to improve reliability.
--- a/app/config/redis.py
+++ b/app/config/redis.py
@@
-redis.Redis(host=host, port=port)
+redis.Redis(host=host, port=port, socket_timeout=5, max_connections=20)
```

---

## 🏗️ Architecture

OpsPilot implements a **multi-agent agentic architecture** with four specialized agents:

1. **Planner Agent** - Analyzes project context and forms hypotheses about root causes
2. **Verifier Agent** - Collects evidence and validates hypotheses with confidence scoring
3. **Fixer Agent** - Generates safe, actionable fix suggestions
4. **Remediation Agent** - Creates 3-tier action plans (immediate, short-term, long-term)

**Multi-Provider LLM System:**
- Automatic fallback routing across 4 providers
- Connection pooling for high availability
- Provider health metrics and monitoring

**Redis-Based Memory:**
- User-isolated incident storage with SHA-256 project hashing
- Automatic TTL expiration (configurable, default 30 days)
- Sub-second similarity search with sorted sets
- Severity-based indexing (P0/P1/P2/P3)

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.

---

## 🧩 How It Works

### 1. Context Collection
OpsPilot gathers information from multiple sources:
- **Logs**: Recent error logs and exceptions
- **Environment**: Environment variables and configurations
- **Dependencies**: Project dependencies (requirements.txt, package.json)
- **Docker**: Dockerfile and docker-compose configurations
- **Structure**: Project file tree and organization

### 2. Hypothesis Generation
The Planner agent uses LLM reasoning to:
- Analyze collected context
- Identify patterns and anomalies
- Form hypotheses about root causes
- Assign confidence scores (0.0 - 1.0)

### 3. Evidence-Based Verification
The Verifier agent:
- Collects concrete evidence (log errors, missing configs, etc.)
- Cross-references with the hypothesis
- Updates confidence based on evidence strength
- Provides reasoning for the verdict

### 4. Safe Fix Suggestions
If confidence ≥ 0.6, the Fixer agent:
- Generates actionable fix suggestions as diffs
- Explains the rationale for each fix
- Provides domain-specific solutions (e.g., Redis timeout fixes)
- **Never auto-applies changes** (dry-run only for safety)

### 5. Learning from History
OpsPilot maintains Redis-based memory of past issues:
- Stores hypotheses, confidence scores, and evidence with automatic TTL
- User-isolated storage using project path hashing
- Detects similar issues in future runs with sub-second lookups
- Automatic expiration prevents stale incident data
- Falls back to file-based storage if Redis unavailable

---

## 🎓 Technology Stack

- **LLM Integration**: Multi-provider system (Ollama, OpenRouter, Gemini, HuggingFace) with automatic fallback
- **Memory Layer**: Redis (with file-based fallback) for incident history and similarity detection
- **CLI Framework**: Typer + Rich (professional terminal output)
- **Cloud Integration**: AWS (S3, CloudWatch), Kubernetes, HTTP endpoints
- **AI Pattern**: Multi-agent agentic architecture with 4 specialized agents
- **Reasoning**: Evidence-based decision making with P0/P1/P2/P3 severity classification
- **Prompt Engineering**: Robust JSON extraction with retry logic and safe parsing
- **Testing**: pytest with 45+ unit tests and integration test coverage

---

## 📋 Project Structure

```
opspilot/
├── agents/                    # Four specialized AI agents
│   ├── planner.py            # Hypothesis generation
│   ├── verifier.py           # Evidence-based verification
│   ├── fixer.py              # Safe fix suggestions
│   └── remediation.py        # 3-tier remediation plans
├── context/                   # Context gathering modules
│   ├── logs.py               # Log analysis
│   ├── env.py                # Environment variables
│   ├── deps.py               # Dependency detection
│   ├── docker.py             # Docker configuration
│   ├── project.py            # Project structure
│   ├── production_logs.py    # Multi-source log fetching (S3, K8s, CloudWatch)
│   ├── deployment_history.py # Git-based deployment correlation
│   └── pattern_analysis.py   # Error pattern detection & severity classification
├── utils/                     # Shared utilities
│   ├── llm_providers.py      # Multi-provider LLM router with fallback
│   └── llm.py                # Backward-compatible LLM wrapper
├── tools/                     # Evidence collection utilities
│   ├── log_tools.py          # Log error analysis
│   ├── env_tools.py          # Environment validation
│   └── dep_tools.py          # Dependency checking
├── diffs/                     # Domain-specific fix templates
├── memory.py                  # File-based memory (fallback)
├── memory_redis.py            # Redis-based memory with user isolation
├── tests/                     # Comprehensive test suite (45+ tests)
│   ├── test_pattern_analysis.py
│   ├── test_production_logs.py
│   ├── test_remediation.py
│   └── test_llm_providers.py
└── cli.py                     # Command-line interface
```

---

## 🔒 Safety & Design Principles

- **Dry-Run Only**: Never automatically applies changes to your code
- **Evidence-Based**: All suggestions backed by concrete evidence
- **Confidence Scoring**: Transparent about certainty levels (0.0 - 1.0)
- **Privacy-Focused**: Prefers local LLM (Ollama) with automatic fallback to cloud
- **User Isolation**: Redis memory uses SHA-256 project hashing for complete data separation
- **Auto-Expiring Data**: Incidents automatically expire after configurable TTL (default 30 days)
- **High Availability**: Multi-provider LLM system with automatic failover
- **Modular Design**: Easy to extend with new agents, providers, or context sources
- **Production-Ready**: Comprehensive test coverage, error handling, and graceful degradation

---

## 🛠️ Development

### Running from Source

```bash
# Install in development mode
pip install -e .

# Run the CLI
opspilot analyze
```

### Requirements

- Python 3.8+
- At least one LLM provider (see Quick Start)
- Optional: Redis for production incident memory

### Running Tests

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=opspilot tests/

# Run specific test file
pytest tests/test_llm_providers.py
```

---

## 🗺️ Roadmap

- [x] Multi-provider LLM support with automatic fallback
- [x] Comprehensive test coverage (45+ tests)
- [x] Redis-based memory with user isolation
- [x] Production log fetching (S3, K8s, CloudWatch)
- [x] Deployment correlation analysis
- [x] Severity classification (P0/P1/P2/P3)
- [ ] Plugin system for custom agents
- [ ] Web API for remote usage
- [ ] More domain-specific fix templates (PostgreSQL, MongoDB, etc.)
- [ ] Real-time metrics dashboard
- [ ] Slack/PagerDuty integration for incident alerts

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🤝 Contributing

Contributions are welcome! This project is under active development. Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

For major changes, please open an issue first to discuss your ideas.

---

## 📧 Contact

For questions or feedback, please open an issue on GitHub.

---

**Built with ❤️ using agentic AI principles**
