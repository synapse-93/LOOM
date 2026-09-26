# VIDEO2PRINT — AGENT CONSTITUTION & OPERATING SYSTEM

**Project**: VIDEO2PRINT (Smartphone Video → Metrically Scaled → Validated → 3D Printable Object)  
**Repository Source of Truth**: This repository is the definitive project state. Never rely on LLM context memory or conversational chat history across sessions.

---

## 1. Core Directives for All Agents

Every Antigravity / Gemini agent working on this codebase must adhere strictly to these principles:

1. **Read State First**: Always read [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md) before performing any meaningful work.
2. **Inspect Existing Code**: Always inspect the existing filesystem, code, and configurations before modifying or proposing changes. Never write blind replacements.
3. **Follow the Architecture**: Adhere strictly to the modular architectural boundaries defined in [`.agents/rules/architecture.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/architecture.md).
4. **Avoid Unnecessary Dependencies**: Adhere to [`.agents/rules/python.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/python.md). Do not introduce heavyweight dependencies (PyTorch, NeRFs, SAM, Depth Anything, CUDA toolchains) unless explicitly justified by an approved decision.
5. **Verify Compatibility**: Ensure all code runs on Python 3.10.11 and functions properly on the target host environment.
6. **Zero Hallucinated Results**: Adhere strictly to [`.agents/rules/research.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/research.md). Never invent numerical results, accuracy figures, error tolerances, or citations. All numbers must come from empirical execution.
7. **Test Every Change**: Follow [`.agents/rules/testing.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/testing.md). Every module must have verifiable tests. Never fake test passes or mock away what needs to be verified.
8. **Preserve Working Functionality**: Existing functional pipelines and passing tests must never be broken by new iterations.
9. **Isolate External Reconstruction**: Treat 3D reconstruction engines as external interchangeable backends behind strict adapter interfaces ([`.agents/rules/reconstruction.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/reconstruction.md)).
10. **Never Claim Completion Without Verification**: If code hasn't been executed and verified, state that it is implemented but unverified. Do not mark items complete prematurely.
11. **Do Not Blindly Trust Previous Agents**: Verify claims against actual code, logs, and artifacts in the repository.

---

## 2. Mandatory Iteration Workflow

Every agent invocation that plans, edits, or adds code must execute this sequential workflow:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  READ STATE  │ ──> │   INSPECT    │ ──> │    PLAN      │ ──> │  IMPLEMENT   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                       │
┌──────────────┐     ┌──────────────┐     ┌──────────────┐             │
│    REPORT    │ <── │ UPDATE STATE │ <── │    VERIFY    │ <── ────────┘
└──────────────┘     └──────────────┘     └──────────────┘
                                ▲                │
                                │ (Run Tests)    ▼
                                └───────── (Check Results)
```

1. **READ STATE**:
   - Read [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md) to understand current milestone, verified components, active blockers, and immediate tasks.
   - Review relevant rule files in [`.agents/rules/`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/).
2. **INSPECT**:
   - Inspect existing files, interfaces, and test fixtures related to the task.
   - Check environment state (Python version, installed packages, external tools).
3. **PLAN**:
   - Formulate a minimal, modular design conforming to project rules.
   - If an architectural trade-off is involved, prepare an entry for [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md).
4. **IMPLEMENT**:
   - Write clean, type-annotated, logged Python 3.10 code using `pathlib.Path`.
   - Never hardcode filepaths; use configuration objects.
5. **TEST**:
   - Write or update unit and integration tests covering the new functionality.
   - Execute tests in the isolated environment.
6. **VERIFY**:
   - Confirm tests pass and outputs are valid.
   - Measure real metrics (processing time, mesh statistics, dimensional accuracy) where applicable.
7. **UPDATE STATE** (Context Update Protocol):
   - Update [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md).
   - Add a numbered entry to [`project/CHANGELOG.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CHANGELOG.md).
   - Update [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md) if bugs, limitations, or blockers arose.
   - Update [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md) if an architectural decision was finalized.
   - Update [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md) if empirical experimental data was gathered.
   - Update [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md) only if milestone status genuinely shifted.
8. **REPORT**:
   - Provide a concise summary to the user outlining changes made, verification results, current state, and the next recommended step.

---

## 3. Context Update Protocol

To prevent context drift and stale information:

| File | Update Trigger | Content Rules |
| :--- | :--- | :--- |
| [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md) | **Every meaningful iteration** | Keep concise (< 120 lines). Overwrite stale state. Do not accumulate history here. |
| [`project/CHANGELOG.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CHANGELOG.md) | **Every meaningful iteration** | Add a new chronological `Iteration XXX` entry detailing what was added/fixed. |
| [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md) | When issues are found, resolved, or re-categorized | Categorize: Active Blockers, Known Limitations, Technical Debt, Research Questions, Resolved Issues. |
| [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md) | When architectural or tech stack choices are made | Record ADR: Context, Decision, Reason, Alternatives Considered, Consequences, Status. |
| [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md) | When empirical experiments are executed | Record real measurements, inputs, outputs, errors. No fabricated numbers. |
| [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md) | Only when milestone status genuinely changes | Update phase statuses (Not Started, In Progress, Complete). |

---

## 4. Context Efficiency Rules

- **`CONTEXT.md` must stay small and readable**: It is a quick-loading snapshot for AI agents. Do not dump logs, code snippets, or lengthy histories into it.
- **Historical information belongs in dedicated files**:
  - History of changes → [`project/CHANGELOG.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CHANGELOG.md)
  - Architectural rationale → [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md)
  - Empirical data & logs → [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md)
  - Known bugs & limitations → [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md)
- **Replace, don't hoard**: When updating `CONTEXT.md`, overwrite outdated status lines rather than appending them.

---

## 5. Quick Reference Map

- **Rules**:
  - Architecture: [`.agents/rules/architecture.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/architecture.md)
  - Python standards: [`.agents/rules/python.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/python.md)
  - 3D Reconstruction: [`.agents/rules/reconstruction.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/reconstruction.md)
  - Testing philosophy: [`.agents/rules/testing.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/testing.md)
  - Research integrity: [`.agents/rules/research.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/research.md)
- **Project State**:
  - Current State: [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md)
  - Staged Roadmap: [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md)
  - Architectural Decisions: [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md)
  - Experiment Log: [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md)
  - Issues & Limitations: [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md)
  - Iteration History: [`project/CHANGELOG.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CHANGELOG.md)
