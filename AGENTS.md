# AGENTS.md – Architectural Standards and Safety Rules

This document establishes the mandatory architectural standards, domain constraints, and safety guidelines for all AI agents and software engineers contributing to **TZ Plan Pipeline**.

---

## 1. Project Mission & Context

TZ Plan Pipeline is an AI-assisted construction drawing analysis and quantity takeoff system built for a Hungarian general contractor. The system analyzes residential construction drawings (vector PDFs exported from CAD tools, and in the future DWG, IFC, and scans) to produce auditable, deterministic bill-of-quantities for:
- Facade insulation systems (EPS Grafit, XPS plinths, mesh, primers, finishes).
- Masonry, plastering, and drywall partitions.
- Interior and exterior floor/wall finishes.

---

## 2. The 12 Non-Negotiable Principles

Every line of code and every future subagent must strictly adhere to these 12 principles:

### Principle 1: AI Interprets, Deterministic Python Calculates
AI models interpret ambiguous text, drawing layouts, and symbol associations. **AI must never serve as the authoritative calculation engine.** All final quantities, areas, volumes, and deduction algorithms must execute in pure, deterministic, unit-tested Python code.

### Principle 2: Deterministic, Testable Math
Formulas must be transparent, testable, and recorded. Every calculated `Quantity` object records its `formula_expression` and an immutable list of `QuantityInput` snapshots.

### Principle 3: Absolute Source Lineage
Every extracted measurement must retain its source lineage:
- Document UUID & filename
- DocumentRevision UUID & file SHA-256 hash
- Page number (1-indexed) & Page UUID
- Canonical PDF coordinate bounding box (`BoundingBox`: `x0`, `y0`, `x1`, `y1`)
- Lineage is tracked via `Measurement.evidence_ids`.

### Principle 4: Separation of Origin and Verification
- **`ValueOrigin`** describes where the data came from:
  - `EXTRACTED`: Direct vector/text CAD extraction.
  - `INFERRED`: Derived deterministically by geometric rules.
  - `MANUAL_INPUT`: Entered by a human user.
  - `MANUALLY_CORRECTED`: User correction replacing an earlier measurement.
  - `AI_HYPOTHESIS`: Candidate proposed by an AI model.
- **`VerificationStatus`** describes the review lifecycle:
  - `UNVERIFIED`: Raw or candidate state.
  - `AUTO_VERIFIED`: Passed automated deterministic cross-check rules.
  - `REVIEW_REQUIRED`: Flagged due to uncertainty or conflict.
  - `HUMAN_APPROVED`: Explicitly approved by an authorized human reviewer.
  - `REJECTED`: Discarded.
- **Rule**: AI confidence scores (e.g. `0.99`) are informational hypotheses and must NEVER be treated as verification.

### Principle 5: Missing Data is Never Silently Zero
Missing measurements must remain `None`. Legitimate `0.0` (such as a floor level offset or flush sill height) and negative coordinates are valid numbers.
- **Anti-Pattern**: `value = measurement.value or 0.0` (STRICTLY FORBIDDEN).
- **Correct Pattern**: `val = measurement.get_required_value()`, which raises `MissingDataError` if the value is `None`.

### Principle 6: Zero Fabrication
The pipeline must never invent dimensions, guess sheet numbers, or fabricate bounding boxes. If a measurement is absent from the drawing, create an `AuditFinding` rather than guessing.

### Principle 7: Conflicting Data Preserves All Sources
When sources conflict (e.g., an architectural floor plan states window width is 150 cm, but the window schedule table states 140 cm):
- Do NOT silently pick a winner.
- Do NOT overwrite the existing measurement.
- Preserve all evidence items in their respective `evidence_ids`.
- Create an `AuditFinding` with severity `FindingSeverity.CONFLICT`.

### Principle 8: AI Provider Independence
The core domain model, persistence layer, and calculation engines must have zero dependencies on external AI SDKs (such as OpenAI, Anthropic, or Google GenAI).
- All AI interaction goes through `AIProvider(ABC)` in `tz_plan_pipeline.ai.provider`.
- Providers are loaded via `AIProviderRegistry`.
- An offline, zero-network `MockAIProvider` is always available for CI and local development.

### Principle 9: Independent Auditing & Recalculation
Quantities track whether their input measurements have changed. When a measurement is superseded or modified:
- `quantity.mark_for_recalculation("Reason")` flags the item.
- Historical snapshots in `QuantityInput` preserve the exact values used at calculation time.

### Principle 10: Non-Simulated Human Approval Boundary
- Only actors with `actor_role == ActorRole.HUMAN_REVIEWER` can execute authoritative review approvals (`ReviewDecision`).
- Any attempt by `ActorRole.AI_AGENT` or `ActorRole.SYSTEM_RULE` to execute an approval raises `ApprovalSimulationError`.
- *Note*: `ActorInfo` serves as the domain-level approval boundary. Full cryptographic user authentication and authorization belong to the future application layer.

### Principle 11: Document Immutability & SHA-256 Verification
Original drawings must never be modified, overwritten, or converted in place.
- All documents require a SHA-256 hash upon ingestion.
- `DocumentRevision.verify_file_content(bytes)` validates the hash before processing. Tampered or modified files raise `DocumentImmutabilityError`.
- `Document.is_immutable` is locked to `True`.

### Principle 12: Private Drawing & Customer Data Protection
Real construction plans, customer personal data, and proprietary client cost estimates must NEVER be committed to Git.
- Strict `.gitignore` rules exclude `*.pdf`, `*.dwg`, `*.dxf`, `*.ifc`, `projects/`, and `*.db`.
- Only explicitly whitelisted synthetic fixtures under `tests/fixtures/` are allowed in the repository.

---

## 3. Coordinate Systems & Scale Semantics

### Canonical PDF Coordinate System
- Coordinate unit: PDF points (`pt`), where $1\text{ pt} = \frac{1}{72}\text{ inch} = 0.352778\text{ mm}$.
- Standard origin: `TOP_LEFT` (PyMuPDF canonical view) or `BOTTOM_LEFT` (native PDF).
- Raster pixel conversion: $\text{pixels} = \text{pt} \times \frac{\text{DPI}}{72.0}$.

### Declared Scale vs. Calibrated Scale
- A printed title block stating `M=1:50` is a **declared** scale (`ScaleStatus.DECLARED`).
- **A declared scale is NOT authoritative geometry.** Print distortion, paper stretching, scanning scaling, and viewport clipping often corrupt printed scales.
- Authoritative real-world conversion requires **calibration** against a verified dimension line (`ScaleStatus.CALIBRATED`).
- `pt_to_real_world_meters(..., require_authoritative=True)` raises `UncalibratedScaleError` if the scale has not been successfully calibrated.

---

## 4. Building Element Identity Across Revisions

Building elements (`BuildingElement`) maintain a `stable_key` (e.g. `GF-WINDOW-NY01`, `FACADE-NORTH-W01`).
When revised drawings are imported (e.g., `rev01` replaced by `rev02`), the building element identity is preserved, allowing measurement delta tracking and revision audits.

---

## 5. Coding Standards for Future Tasks

1. **Python Version**: Python 3.12+ (use modern typing, `StrEnum`, pattern matching).
2. **Pydantic**: Use Pydantic v2 models with explicit field descriptions and validation.
3. **Storage**: SQLite with WAL mode, foreign keys enabled (`PRAGMA foreign_keys = ON;`), and versioned migrations in `schema_migrations`.
4. **Testing**:
   - Write unit tests alongside every new feature.
   - Include negative tests for error paths, missing values, and unauthorized operations.
   - Run `python -m pytest tests/ -v` to ensure 100% test pass rate.
5. **Hungarian Terminology Reference**:
   - Alaprajz = Floor Plan
   - Homlokzat = Elevation / Facade
   - Metszet = Section
   - Nyílászáró = Opening (Door / Window)
   - Lábazat = Plinth / XPS area
   - Hőszigetelés = Thermal insulation
   - Vakolat = Plaster / Render
   - Káva = Reveal
