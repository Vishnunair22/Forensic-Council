# Forensic Council

**Multi-Agent Forensic Evidence Analysis System**

A production-grade, court-admissible, AI-powered forensic evidence analysis platform that deploys a deliberative council of five specialist AI agents.

## Overview

Forensic Council analyzes digital evidence through a structured ReAct reasoning loop. Each agent independently investigates uploaded evidence, and their findings are synthesized by a Council Arbiter that moderates disagreements and generates a cryptographically signed, court-admissible forensic report.

## Features

- **Multi-Modal Coverage**: Image, audio, video, object, and metadata forensics in a single pipeline
- **Court Admissibility**: Every finding traced through a logged, signed, stepwise reasoning chain
- **Deliberative Synthesis**: Contested findings challenged, re-examined, or escalated — never silently resolved
- **Human Oversight**: Mandatory HITL checkpoints at defined severity and uncertainty thresholds
- **Chain of Custody**: Every action, artifact, and intervention cryptographically signed and immutably stored

## Architecture

### Five Specialist Agents

1. **Agent 1 - Image Integrity**: Pixel-level forensic expert detecting manipulation, splicing, and GAN artifacts
2. **Agent 2 - Audio & Multimedia**: Audio authenticity and multimedia consistency expert
3. **Agent 3 - Object & Weapon**: Object identification and contextual validation specialist
4. **Agent 4 - Temporal Video**: Temporal consistency and video integrity expert
5. **Agent 5 - Metadata & Context**: Digital footprint and provenance analyst

### Core Components

- **ReAct Loop Engine**: THOUGHT → ACTION → OBSERVATION cycles
- **Dual-Layer Memory**: Working memory (Redis) + Episodic memory (Qdrant)
- **Human-in-the-Loop (HITL)**: Mandatory checkpoints at severity thresholds
- **Chain of Custody Logger**: Cryptographically signed audit trail
- **Confidence Calibration**: Benchmark-calibrated confidence scores
- **Council Arbiter**: Cross-agent deliberation and report synthesis

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- uv (Python package manager)

### Installation

1. **Clone the repository**
   ```bash
   cd backend
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Start infrastructure services**
   ```bash
   docker compose -f ../docker-compose.infra.yml up -d
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Initialize the database**
   ```bash
   uv run python scripts/init_db.py
   ```

6. **Run tests**
   ```bash
   uv run pytest tests/ -v
   ```

## Project Structure

```
backend/
├── core/                   # Core modules
│   ├── config.py          # Configuration management
│   ├── logging.py         # Structured JSON logging
│   ├── exceptions.py      # Exception hierarchy
│   ├── signing.py         # Cryptographic signing
│   └── custody_logger.py  # Chain-of-custody logging
├── infra/                  # Infrastructure clients
│   ├── redis_client.py    # Redis client wrapper
│   ├── qdrant_client.py   # Qdrant vector DB client
│   ├── postgres_client.py # PostgreSQL client wrapper
│   └── storage.py         # Evidence storage backend
├── agents/                 # Specialist agents
│   ├── base_agent.py      # Base agent class
│   ├── agent1_image.py    # Image integrity agent
│   ├── agent2_audio.py    # Audio forensics agent
│   ├── agent3_object.py   # Object detection agent
│   ├── agent4_video.py    # Video analysis agent
│   └── agent5_metadata.py # Metadata analysis agent
├── tools/                  # Forensic tools
│   ├── image_tools.py     # Image analysis tools
│   ├── audio_tools.py     # Audio analysis tools
│   ├── video_tools.py     # Video analysis tools
│   └── metadata_tools.py  # Metadata analysis tools
├── orchestration/          # Pipeline orchestration
│   ├── pipeline.py        # Main investigation pipeline
│   └── session_manager.py # Session management
├── reports/                # Report generation
│   └── report_renderer.py # Report rendering
├── tests/                  # Test suite
│   ├── conftest.py        # Pytest fixtures
│   ├── test_core/         # Core module tests
│   ├── test_infra/        # Infrastructure tests
│   ├── test_agents/       # Agent tests
│   └── test_tools/        # Tool tests
├── scripts/                # Utility scripts
│   └── init_db.py         # Database initialization
├── pyproject.toml          # Python project config
└── .env.example            # Environment template
```

## Configuration

Configuration is managed via environment variables. See `.env.example` for all available options.

Key configuration areas:
- **Redis**: Working memory and caching
- **Qdrant**: Episodic memory (vector storage)
- **PostgreSQL**: Chain-of-custody logging
- **OpenAI**: LLM integration for agent reasoning
- **Storage**: Evidence file storage path

## Development

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=. --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_infra/test_redis.py -v
```

### Code Style

This project follows Python best practices:
- Type hints for all function signatures
- Docstrings for all public modules, classes, and functions
- Pydantic models for data validation
- Async/await for I/O operations

## License

MIT License

## Acknowledgments

This is an academic project demonstrating multi-agent AI systems for forensic evidence analysis.
