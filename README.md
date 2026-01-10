# OpsPilot 🤖

> An intelligent agentic AI CLI tool for automated incident analysis and error resolution

OpsPilot is your AI-powered Site Reliability Engineer that analyzes your projects, identifies runtime issues, and suggests safe fixes—all through a simple command-line interface.

---

## 🎯 What is OpsPilot?

OpsPilot uses a **multi-agent AI architecture** to understand your project's context, form hypotheses about runtime issues, and provide evidence-based fix recommendations. Think of it as having an experienced SRE on your team, available 24/7.

### Key Capabilities

- **🔍 Intelligent Context Gathering** - Automatically analyzes logs, environment variables, Docker configs, dependencies, and project structure
- **🧠 Hypothesis Generation** - Uses LLM-powered reasoning to form hypotheses about root causes
- **✅ Evidence-Based Verification** - Validates hypotheses with collected evidence and confidence scoring
- **🛠️ Safe Fix Suggestions** - Provides dry-run suggestions with detailed rationale (never auto-applies changes)
- **💾 Learning from History** - Remembers past issues to speed up future diagnoses

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- [Ollama](https://ollama.ai/) installed locally with Llama 3 model

### Installation

```bash
# Install from source
git clone https://github.com/yourusername/opspilot.git
cd opspilot
pip install -e .
```

### Usage

Navigate to your project directory and run:

```bash
opspilot analyze
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

OpsPilot implements a **multi-agent agentic architecture** with three specialized agents:

1. **Planner Agent** - Analyzes project context and forms hypotheses about root causes
2. **Verifier Agent** - Collects evidence and validates hypotheses with confidence scoring
3. **Fixer Agent** - Generates safe, actionable fix suggestions

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
OpsPilot maintains a memory of past issues:
- Stores hypotheses, confidence scores, and evidence
- Detects similar issues in future runs
- Speeds up diagnosis for recurring problems

---

## 🎓 Technology Stack

- **LLM Integration**: Ollama (local Llama 3 model)
- **CLI Framework**: Typer + Rich (professional terminal output)
- **AI Pattern**: Multi-agent agentic architecture with state management
- **Reasoning**: Evidence-based decision making with confidence scoring
- **Prompt Engineering**: Robust JSON extraction with error handling

---

## 📋 Project Structure

```
opspilot/
├── agents/           # Three specialized AI agents
│   ├── planner.py    # Hypothesis generation
│   ├── verifier.py   # Evidence-based verification
│   └── fixer.py      # Safe fix suggestions
├── context/          # Context gathering modules
│   ├── logs.py       # Log analysis
│   ├── env.py        # Environment variables
│   ├── deps.py       # Dependency detection
│   ├── docker.py     # Docker configuration
│   └── project.py    # Project structure
├── graph/            # Workflow orchestration
│   ├── engine.py     # Agent execution engine
│   └── nodes.py      # State transformation nodes
├── tools/            # Evidence collection utilities
├── diffs/            # Domain-specific fix templates
├── memory.py         # Learning and persistence
└── cli.py            # Command-line interface
```

---

## 🔒 Safety & Design Principles

- **Dry-Run Only**: Never automatically applies changes to your code
- **Evidence-Based**: All suggestions backed by concrete evidence
- **Confidence Scoring**: Transparent about certainty levels (0.0 - 1.0)
- **Local-First**: Uses local LLM (Ollama) - no data sent to cloud
- **Modular Design**: Easy to extend with new agents or context sources

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

- Python 3.10+
- Ollama installed and running
- Llama 3 model downloaded (`ollama pull llama3`)

---

## 🗺️ Roadmap

- [ ] Add comprehensive test coverage
- [ ] Support multiple LLM providers (OpenAI, Anthropic, etc.)
- [ ] Plugin system for custom agents
- [ ] Web API for remote usage
- [ ] More domain-specific fix templates (PostgreSQL, MongoDB, etc.)
- [ ] Metrics and monitoring dashboard

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
