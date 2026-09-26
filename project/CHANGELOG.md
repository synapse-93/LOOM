# ITERATION CHANGELOG — VIDEO2PRINT

This log records chronological development iterations. Every agent completing meaningful work must add an entry following this format.

---

## Iteration 000 — Project Bootstrap & Agent Operating System
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Project Bootstrap
- **Changes Implemented**:
  - Inspected repository state (clean git working tree on branch `main`, Python 3.10.11 registered in `py` launcher but binary missing on disk; active host Python is 3.14.7).
  - Created project constitution [`AGENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/AGENTS.md) with core directives, mandatory iteration workflow, and context update protocols.
  - Created architectural rules in [`.agents/rules/architecture.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/architecture.md) detailing pipeline stages, interfaces, and backend replaceability.
  - Created Python standards in [`.agents/rules/python.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/python.md) specifying Python 3.10.11 runtime, lean dependency policy, and logging/path conventions.
  - Created 3D reconstruction rules in [`.agents/rules/reconstruction.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/reconstruction.md) detailing subprocess adapter pattern, monocular scale ambiguity, and ArUco marker scaling.
  - Created testing philosophy in [`.agents/rules/testing.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/testing.md) establishing independent testability and synthetic test fixtures.
  - Created research integrity rules in [`.agents/rules/research.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/research.md) enforcing zero fabrication of measurements or results.
  - Created current state snapshot in [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md).
  - Created 11-phase staged development plan in [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md).
  - Documented four initial Architecture Decision Records in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md) (ADR-001 through ADR-004).
  - Established schema and empirical logging rules in [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md).
  - Recorded initial discoveries, limitations, and research questions in [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md).
- **Verification**:
  - Validated all 12 project governance and rule files created.
  - Verified no implementation code was falsely marked complete.
  - Verified internal consistency across rules, roadmap, ADRs, and issues.
- **Next Step**:
  - Begin Phase 1: Initialize `.venv` with Python 3.10.11, pin core dependencies in `requirements.txt`, and implement video ingest / frame extraction module with unit tests.
