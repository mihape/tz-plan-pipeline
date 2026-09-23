# TZ Plan Pipeline

**AI-assisted construction drawing analysis and quantity takeoff system** designed for Hungarian general contractors (residential construction, facade thermal insulation systems, masonry, plastering, and floor/wall finishes).

---

## Architectural Principles

1. **AI Interprets, Deterministic Python Calculates**: AI models assist in document interpretation and callout recognition, but all final quantities and takeoff equations are calculated by deterministic, testable Python code.
2. **Absolute Source Lineage**: Every measurement links to its source document revision, page number, and canonical PDF bounding box.
3. **Missing Data is Never Silently Zero**: Missing data is represented as `None`. Zero (`0.0`) is preserved when domain-valid. Missing required inputs raise `MissingDataError`.
4. **Strict Separation of Origin & Verification**: `ValueOrigin` (`EXTRACTED`, `INFERRED`, `MANUAL_INPUT`, `MANUALLY_CORRECTED`, `AI_HYPOTHESIS`) is strictly decoupled from `VerificationStatus` (`UNVERIFIED`, `AUTO_VERIFIED`, `REVIEW_REQUIRED`, `HUMAN_APPROVED`, `REJECTED`). AI confidence is never treated as verification.
5. **Domain-Level Human Approval Boundary**: Only authenticated human reviewers (`ActorRole.HUMAN_REVIEWER`) can authoritatively approve review items; AI agents and automated rules cannot simulate approval.
6. **Canonical PDF Coordinates & Scale Calibration**: Canonical PDF points ($1\text{ pt} = \frac{1}{72}\text{ in}$) are preserved. Declared printed scale labels (e.g. `1:50`) must be calibrated against dimension evidence before producing authoritative real-world measurements.
7. **Document Immutability**: All original drawings are verified with SHA-256 hashes and kept immutable.
8. **Git Drawing & Customer Privacy**: Private construction drawings, customer data, and databases are strictly excluded from Git.

See [AGENTS.md](AGENTS.md) for full architectural guidelines.

---

## Installation

### Prerequisites
- Python 3.12 or newer
- Git

### Setup
```bash
# Clone the repository
git clone <repo-url> TZ_pipeline
cd TZ_pipeline

# Create and activate virtual environment
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install the package in editable mode with development dependencies
pip install -e ".[dev]"
```

---

## CLI Usage

The pipeline provides a Typer-powered command-line interface executable via `tz` or `python -m tz_plan_pipeline.cli.main`.

### Check Version & System Info
```bash
tz version
# Or:
python -m tz_plan_pipeline version
```

### Validate Configuration
```bash
tz config validate --config configs/default_config.yaml
```

### Display Configuration
```bash
tz config show --config configs/default_config.yaml
```

### Create a New Project
```bash
tz project create "Családi Ház Budapest" --code "TZ-2026-BP-001" --desc "Homlokzati hőszigetelés és felületképzés"
```

### List Projects
```bash
tz project list
```

### View Project Info
```bash
tz project info TZ-2026-BP-001
```

---

## Running Automated Tests

Run the full pytest test suite:
```bash
python -m pytest tests/ -v
```

Run specific test modules:
```bash
# Test domain models
python -m pytest tests/test_models.py -v

# Test negative cases and safety boundaries
python -m pytest tests/test_negative.py -v

# Test coordinates, scale calibration, and SI unit conversions
python -m pytest tests/test_coordinates_and_units.py -v

# Test SQLite storage and migrations
python -m pytest tests/test_storage.py -v

# Test AI provider interface
python -m pytest tests/test_ai_provider.py -v

# Test CLI
python -m pytest tests/test_cli.py -v
```

---

## Project Structure

```
TZ_pipeline/
├── .gitignore                      # Strict drawing & database exclusion with test fixture whitelisting
├── pyproject.toml                  # Python 3.12 package definition & CLI entry points
├── README.md                       # Installation and usage instructions
├── AGENTS.md                       # Architectural and safety standards
├── configs/
│   ├── default_config.yaml         # Base application configuration
│   └── sample_project_config.yaml  # Sample Hungarian residential project configuration
├── src/
│   └── tz_plan_pipeline/
│       ├── __init__.py
│       ├── __main__.py             # python -m tz_plan_pipeline entrypoint
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── provider.py         # Abstract AIProvider interface and registry
│       │   └── mock_provider.py    # Zero-dependency deterministic mock provider
│       ├── cli/
│       │   ├── __init__.py
│       │   └── main.py             # Typer CLI application (tz command)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py           # YAML configuration loader and Pydantic validator
│       │   ├── coordinates.py      # Canonical PDF coordinates & scale calibration
│       │   ├── db.py               # SQLite WAL persistence and schema migrations
│       │   ├── errors.py           # Domain exception hierarchy
│       │   ├── logging.py          # Structured logging setup
│       │   └── units.py            # Internal SI unit conversion engine
│       └── models/
│           ├── __init__.py         # Core domain model exports
│           ├── audit.py            # AuditFinding and ReviewDecision
│           ├── common.py           # BoundingBox, Point2D, ActorInfo boundary
│           ├── document.py         # Document, DocumentRevision, Page
│           ├── element.py          # BuildingElement with revision-stable key
│           ├── enums.py            # Domain enumerations (ValueOrigin, VerificationStatus, etc.)
│           ├── evidence.py         # Evidence with coordinate and source lineage
│           ├── measurement.py      # Measurement with provenance and correction history
│           ├── project.py          # Project model
│           └── quantity.py         # Deterministic Quantity and input snapshots
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Pytest fixtures and synthetic test generators
    ├── fixtures/
    │   └── synthetic_sample.json   # Synthetic test drawing fixture
    ├── test_ai_provider.py         # AI provider interface compliance tests
    ├── test_cli.py                 # Typer CLI command tests
    ├── test_config.py              # Configuration loading and validation tests
    ├── test_coordinates_and_units.py # Coordinate, scale, and SI conversion tests
    ├── test_models.py              # Domain models serialization and validation tests
    ├── test_negative.py            # Negative tests (missing data, unauthorized approvals, etc.)
    └── test_storage.py             # SQLite migration and repository tests
```
