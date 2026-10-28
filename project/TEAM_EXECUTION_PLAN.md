# LOOM / VIDEO2PRINT — Three-Person Team Execution Plan

> **Purpose:** Keep the team aligned on scope, ownership, dependencies, evidence, and Git workflow. Treat this as the shared working plan. Update it when a decision materially changes; do not silently work around it.
>
> **Team:** Contributor A (you: project owner/integration lead), Contributor B (geometry validation, printability, STL export), Contributor C (capture quality, benchmarking, physical validation).
>
> **Source of truth:** This plan supplements, and does not replace, the repository's ROADMAP.md, CONTEXT.md, ISSUES.md, EXPERIMENTS.md, AGENTS.md, and the rules under .agents/rules/.

---

## 1. Project goal and definition of success

LOOM / VIDEO2PRINT should turn smartphone video of a real object into a dimensionally scaled, validated 3D-printable STL, with reproducible reports and evidence.

**Target workflow:**

Physical object → smartphone video → video/frame ingestion → capture assessment → photogrammetry reconstruction → mesh cleanup → metric scaling → geometry validation → printability analysis → STL export → slicer → physical print (if hardware is available).

The project is not complete merely because modules exist or an STL file is written. Distinguish these levels:

1. **Unit-tested functionality** — validated using isolated functions or synthetic fixtures.
2. **Integration-tested functionality** — multiple stages work together, possibly with mocked external tools.
3. **Real reconstruction** — a real capture was processed by an actual photogrammetry backend.
4. **Physical accuracy validation** — reconstructed dimensions were compared with known measurements.
5. **Physical print validation** — an exported model was printed and the resulting part was measured.

Never describe one level as evidence for a higher level.

## 2. Baseline understanding of the repository

The repository documentation describes the following state. These are documented claims to verify, not a substitute for a fresh test run.

| Area | Documented state | Required follow-up |
|---|---|---|
| Bootstrap and project rules | Established | Follow existing rules and update context documents when needed |
| Video ingestion and frame selection | Implemented | Verify against real smartphone captures and existing tests |
| Capture quality and guidance | Partly implemented | Improve coverage/quality warnings and validate usefulness |
| Reconstruction | Adapter and pipeline integration implemented; live execution documented as blocked | Configure a real backend and complete a live reconstruction |
| Mesh cleanup | Implemented and synthetic-fixture-tested | Test with real reconstructed output |
| Metric scaling | Implemented and synthetic-tested | Demonstrate a defensible marker-to-3D scale measurement and compare against physical dimensions |
| Geometry validation | Some modules scaffolded/incomplete | Implement dimensions and ground-truth comparisons |
| Printability analysis | Scaffolded/incomplete | Implement and test checks, reports, and limitations |
| STL export | Scaffolded/incomplete | Implement export and reload verification |
| Benchmarks | Not complete | Record repeatable runs and measured outcomes |
| Physical printing | Not verified | Print and measure a model if a suitable printer is available |
| Final demo/report | Not complete | Package reproducible setup, outputs, results, and limitations |

### Known blockers and technical cautions

- ISSUES.md documents a missing Meshroom/AliceVision executable on the development host. Verify the current machine before assuming this is still true.
- The repository documents Python 3.10.11 as the expected environment. On Windows, the documented setup is \u0060py -3.10 -m venv .venv\u0060; do not blindly use a newer system Python.
- Monocular structure-from-motion has arbitrary scale unless a valid metric reference is established.
- Detecting a 2D ArUco marker in an image does **not**, by itself, prove that the marker's corresponding 3D extent can be measured reliably in the reconstructed mesh.
- Repository documentation has reported test counts in the past. Run the current test suite and report the actual count/results instead of repeating a stale number.

Before implementation begins, inspect the current code and run the existing tests. If the actual state differs from this summary, update this plan and the relevant project documents.

---

## 3. Team roles and file ownership

Ownership is designed to allow parallel work while avoiding simultaneous edits to the same files. The named owner is responsible for implementation and tests in that area; shared interfaces still require coordination.

### Contributor A — You: integration, reconstruction, and end-to-end pipeline

**Owns**
- src/loom/reconstruction/
- src/loom/pipeline/
- src/loom/__main__.py
- Reconstruction smoke-test scripts and environment diagnostics
- tests/integration/reconstruction/
- tests/integration/full_pipeline/
- Other integration tests that connect the full workflow

**Responsibilities**
1. Establish and maintain the verified test baseline.
2. Resolve the real reconstruction backend blocker, starting with the existing adapter.
3. Run real smartphone footage through the actual backend and inspect its artifacts.
4. Verify the reconstruction-to-cleanup handoff.
5. Integrate scaling, validation, printability, and export through agreed interfaces.
6. Keep the CLI backward-compatible where practical and report stage status, warnings, output paths, and errors clearly.
7. Own the final end-to-end test and demonstration instructions.
8. Coordinate shared interfaces and decide integration order with the other contributors.

**Definition of done:** A real capture has been processed by an actual reconstruction backend; outputs can be handed to downstream stages; integration tests and error paths are verified; and the demo is reproducible.

**Do not:** Independently rewrite Contributor B's validation, printability, or export modules. Do not call a mocked reconstruction a real reconstruction or claim physical accuracy without measurements.

### Contributor B — Geometry validation, printability, and STL export

**Owns**
- src/loom/validation/
- src/loom/printability/
- src/loom/export/
- tests/unit/validation/
- tests/unit/printability/
- Export-specific unit tests (create a fitting test location if needed)

**Responsibilities**
1. Implement mesh dimensions/bounding-box measurements and clearly documented units.
2. Implement comparison against supplied ground-truth dimensions, absolute error, percentage error, and safe handling of invalid/zero reference values.
3. Add useful geometry-comparison metrics if feasible and document their limitations.
4. Implement appropriate checks for watertightness, supported manifold/topology properties, normal consistency, minimum wall thickness, and overhangs.
5. Implement binary STL export and reload verification.
6. Ensure export does not silently change mesh scale.
7. Produce meaningful machine-readable and human-readable reports/manifests.
8. Test known-good, known-bad, empty, and intentionally defective synthetic meshes.

**Definition of done:** Known synthetic meshes produce expected measurements; deliberately defective meshes trigger findings; a valid mesh exports to a readable STL without silent scale changes; reports contain computed values; limitations are documented.

**Do not:** Independently edit src/loom/pipeline/runner.py or src/loom/__main__.py. Coordinate interfaces with Contributor A before integration. Do not equate watertightness or successful export with printability.

### Contributor C — Capture quality, benchmarking, and physical validation

**Owns**
- src/loom/capture/
- tests/unit/capture/
- Capture documentation, including docs/capture/
- project/EXPERIMENTS.md
- Benchmark/capture-evaluation utilities, coordinating before editing shared scripts

**Responsibilities**
1. Review current capture-quality and coverage metrics before adding new ones.
2. Improve actionable warnings for blur, lighting, low texture, viewpoint diversity, and likely missing views where evidence supports them.
3. Distinguish measured problems from heuristic warnings; do not promise reconstruction success based on a score.
4. Establish a repeatable physical-capture protocol.
5. Select a small set of objects with measurable dimensions and record caliper measurements.
6. Plan captures with a correctly configured, known-size ArUco reference marker.
7. Record capture settings, frame counts, reconstruction status/runtime, dimensional errors, mesh findings, export status, and failures.
8. Maintain a benchmark log with actual observations only.
9. Conduct physical print validation if a suitable printer is available; otherwise document it as unverified/blocked.

**Definition of done:** Capture assessment has tests; a reproducible measurement protocol exists; benchmark results are recorded when runs are possible; and unavailable experiments/hardware are explicitly identified.

**Do not:** Independently edit src/loom/pipeline/runner.py or src/loom/__main__.py. Do not fabricate measurements or claim 2D marker detection alone supplies a valid 3D measurement.

---

## 4. Work waves and dependencies

No speculative dates are assigned. Complete the waves in order, but allow independent tasks within a wave to proceed in parallel.

### Wave 1 — Baseline and interface agreement

**All three contributors. Contributor A coordinates.**

- **A:** Inspect repository rules, run the current test suite, verify Python environment and CLI, map the reconstruction/pipeline interfaces, inspect the backend blocker.
- **B:** Inspect validation, printability, and export modules and tests; list incomplete implementations; propose minimal function signatures and report schemas.
- **C:** Inspect capture modules and tests; draft the physical test protocol and benchmark record format.

**Required outputs**
- Actual test baseline and environment notes.
- A concise interface agreement covering mesh input representation, units/scale state, stage outputs, validation inputs, export behavior, and error/report conventions.
- Updated list of blockers in project/ISSUES.md if the current findings differ.

Do not let interface discussions stall the work. Agree on the minimum viable contract, implement against it, and revise through explicit coordination when needed.

### Wave 2 — Parallel implementation

- **A:** Configure/test the reconstruction backend; run the first real reconstruction; verify the reconstruction-to-cleanup handoff; improve pipeline stage/error reporting.
- **B:** Implement geometry validation, printability checks, STL export, reports, and synthetic-mesh unit tests.
- **C:** Improve capture assessment, write capture guidance, build benchmark recording utilities, and prepare measured reference objects/captures.

**Dependency:** B can progress with synthetic meshes while A resolves reconstruction. C can prepare experiments before a live backend is available.

### Wave 3 — Integration and physical verification

- **A:** Connect downstream modules; run end-to-end integration; resolve pipeline/CLI failures.
- **B:** Fix issues in owned modules; verify report contents, STL readability, and scale preservation.
- **C:** Run capture experiments when possible; compare output dimensions with ground truth; record runtimes, failures, and limitations.

**Key milestone:** One successful run from real smartphone video through a real reconstruction backend to an exported STL. Separately report whether metric accuracy has been physically verified.

### Wave 4 — Final verification and demo

- **A:** Own the full workflow demonstration and reproducible setup instructions.
- **B:** Explain validation/printability/export methods, results, and limitations.
- **C:** Present the experimental protocol, benchmark results, dimensional errors, and physical-print results if available.
- **All:** Review the acceptance checklist in Section 8, rerun relevant tests after integration, and ensure claims in the demo match recorded evidence.

---

## 5. Technical implementation order

### Milestone 1 — Establish a trustworthy baseline

1. Read AGENTS.md and relevant .agents/rules/ documents.
2. Create/activate the expected Python 3.10 environment according to repository instructions.
3. Install dependencies as documented.
4. Run the full existing test suite and record the exact command, environment, pass/fail count, and warnings.
5. Check the current CLI and configuration behavior.
6. Verify existing video-processing and synthetic mesh/scaling workflows.
7. Record failures and environment blockers without masking them.

**Exit condition:** The team knows what currently passes, what fails, and what requires an external tool or physical experiment.

### Milestone 2 — Obtain a real reconstructed mesh (critical path)

1. Inspect the existing reconstruction adapter and smoke-test script.
2. Verify whether Meshroom/AliceVision is available and correctly configured.
3. If unavailable or impractical, evaluate the existing COLMAP adapter before introducing a new backend.
4. Run a real smartphone capture through the selected backend.
5. Save logs and identify the actual output artifacts.
6. Inspect the result and pass it through mesh diagnostics/cleanup.
7. Record runtime, warnings, failures, and the environment used.

**Exit condition:** A real backend has produced a mesh/point-cloud artifact from real capture data, and the handoff is documented. Mocked tests alone do not satisfy this condition.

### Milestone 3 — Validate metric scaling against physical dimensions (critical path)

1. Choose an object with measurable dimensions and measure it with calipers.
2. Capture the object with the known-size ArUco reference marker visible and configured correctly.
3. Reconstruct the scene.
4. Determine how the known marker dimension maps to the reconstructed geometry.
5. Calculate and apply the scale factor using an explicit, defensible measurement.
6. Compare scaled dimensions with physical ground truth.
7. Record absolute and percentage errors, including method and uncertainty/limitations where known.

**Exit condition:** Scaling is demonstrated on a real reconstruction and compared with ground truth. If the marker cannot be measured reliably in 3D, record the issue and resolve it; do not substitute a guessed measurement while claiming automatic scaling.

### Milestone 4 — Finish validation, printability, and export

1. Implement dimensional measurements and ground-truth comparison.
2. Implement printability checks and documented angle/unit conventions.
3. Implement STL export and reload verification.
4. Verify scale preservation and output-path/error handling.
5. Test valid, invalid, empty, and intentionally defective meshes.
6. Agree on report fields with Contributor A and integrate only after the unit-level contracts are stable.

**Exit condition:** Unit tests demonstrate expected results on synthetic geometry, and the downstream modules can process a real pipeline artifact when available.

### Milestone 5 — Capture evaluation and benchmarking

Record, for each run where available:
- Object ID and capture ID.
- Reference dimensions and measurement method.
- Video resolution, duration, and capture conditions.
- Extracted/selected frame counts.
- Backend and configuration.
- Reconstruction status and runtime.
- Scaling method and status.
- Reconstructed dimensions and absolute/percentage errors.
- Geometry/printability findings.
- STL export status and output size.
- Warnings, failures, and limitations.

Start with a calibration object, a textured object, and a more challenging object. Record failed runs too; do not omit them to make results appear better.

**Exit condition:** project/EXPERIMENTS.md contains reproducible procedures and actual results, or clearly labels tests that remain blocked/not run.

### Milestone 6 — Slicer and physical print validation

1. Open a validated STL in a slicer.
2. Inspect scale, orientation, and model defects.
3. Record slicer and print settings.
4. Print at least one suitable model if printer access is available.
5. Measure the printed part and compare it with both the source object and the reconstructed mesh.
6. Document tolerances and limitations.

**Exit condition:** Physical print claims are supported by recorded measurements. If hardware is unavailable, mark physical printing as unverified and present the software-side evidence accurately.

---

## 6. Shared interfaces and engineering rules

Before integrating, agree on these minimum contracts:

1. **Mesh representation:** Reuse the project's existing mesh representation and accepted formats where possible. Document supported formats rather than inventing incompatible representations in separate modules.
2. **Scale/units state:** Track whether scale is unknown/arbitrary or calibrated. Do not label arbitrary mesh coordinates as millimetres.
3. **Stage result:** Each stage should make success/failure, output artifacts, warnings, and errors discoverable through existing project conventions.
4. **Ground truth:** Specify how reference dimensions are supplied, which axes/dimensions they correspond to, and which units are used.
5. **Printability:** Report individual checks and findings. A single “printable” boolean must not hide which checks ran or which were skipped.
6. **Export:** Verify the exported STL can be reloaded and that its dimensions/scale are preserved within a defined tolerance.
7. **Reports:** Use consistent paths and machine-readable formats compatible with existing artifact/report conventions.
8. **Error honesty:** Missing backends, incomplete reconstruction, missing measurements, and skipped checks must be explicit; never silently turn a failed stage into success.

Keep shared interfaces small. Coordinate any change to a common model, config schema, dependency list, or pipeline contract before implementing it in parallel.

---

## 7. Shared-branch Git workflow

All contributors work on the **same shared branch** unless the project owner explicitly instructs otherwise.

### Before editing

1. Check git status.
2. Check the current branch and recent commits.
3. Fetch/pull the latest shared changes using the team's agreed workflow.
4. Inspect the files you will modify and any relevant rules.
5. Announce intended changes if they touch a shared interface or a file owned by another contributor.

### While editing

- Respect the ownership table in Section 3.
- Do not reset, revert, or overwrite another contributor's uncommitted work.
- Make focused changes and small commits.
- Do not independently change shared dependency/configuration files without coordination.
- Keep generated workspaces, frame dumps, large reconstruction artifacts, secrets, personal data, and other non-source outputs out of Git unless the team explicitly agrees otherwise.
- Update relevant docs and tests with the implementation.

### Before committing

1. Stage explicit paths; do not blindly use git add .
2. Inspect git diff --cached.
3. Run the relevant tests.
4. Commit with a descriptive message, e.g.:
   - docs: add team execution plan
   - feat(validation): implement dimensional error metrics
   - feat(printability): add topology checks
   - feat(export): implement binary STL export
   - test(capture): add coverage assessment cases
   - fix(reconstruction): improve artifact discovery

### Before pushing

1. Fetch and integrate the latest remote changes.
2. Resolve conflicts carefully and rerun affected tests.
3. Push normally; **never force-push** to overwrite shared history.
4. Confirm the commit is present on the shared branch and tell the team what changed.

Example commands (replace main if the shared branch has another name):

    git status
    git branch --show-current
    git log -5 --oneline
    git fetch origin
    git pull --rebase origin main
    # edit files and run relevant tests
    git add src/loom/validation tests/unit/validation
    git diff --cached
    git commit -m "feat(validation): implement dimensional validation"
    git push origin main

### Shared workspace caution

A shared branch and a shared working directory are different things. If all agents edit the **same physical working directory**, do not run overlapping edit sessions that may write to the same files or Git index. Use coordinated/sequential edits for that workspace. Parallel work is safer when contributors have isolated working directories, but changes still need disciplined integration on the shared branch.

### End-of-session handoff

Each contributor reports:
- Files changed.
- Commit hash and whether it is pushed.
- Tests run and actual results.
- Artifacts produced (if any).
- Blockers/decisions needed from the team.
- Next intended task.

---

## 8. Final acceptance checklist

Do not mark a row complete without the corresponding evidence.

| Requirement | Evidence required | Owner lead |
|---|---|---|
| Video ingestion | Successful run on real video and generated reports | A / C |
| Frame selection | Extracted/selected counts and capture report | C |
| Reconstruction | Successful run using a real backend with logs/artifacts | A |
| Mesh cleanup | Real reconstructed mesh processed and inspected | A |
| Metric scaling | Known physical reference and measured dimensional error | A / C |
| Geometry validation | Expected synthetic tests plus ground-truth comparison report | B |
| Printability checks | Findings on test meshes, with methods/limitations documented | B |
| STL export | Binary STL successfully reloaded and scale preserved | B |
| End-to-end pipeline | One reproducible run connecting available stages | A |
| Benchmarking | Recorded real measurements, runtimes, and failures | C |
| Physical printing | Printed part and measurements, or explicitly marked unverified | C |
| Test suite | Fresh test results after final integration | A coordinates; all contribute |
| Documentation | Setup, usage, outputs, limitations, and demo steps | All; A coordinates |
| Git history | Intended changes committed and pushed, no accidental generated artifacts | All |

---

## 9. Required project documentation updates

When a milestone changes the verified state, update the appropriate source-of-truth document instead of leaving stale claims:

- project/ROADMAP.md — phase status and acceptance criteria.
- project/ISSUES.md — active blockers, resolved issues, and technical debt.
- project/EXPERIMENTS.md — actual capture procedures, measurements, metrics, runtimes, and failures.
- project/CONTEXT.md — concise current state and next actions, following the repository's context-update protocol.
- project/CHANGELOG.md — meaningful completed changes.
- docs/ — algorithms, CLI usage, environment setup, and limitations.
- This file — team ownership, sequencing, and coordination changes.

Do not update documentation to claim a result before it has been observed and recorded.

---

## 10. Contributor prompts

Use these prompts when delegating work to an AI coding agent. Always provide the repository's own AGENTS.md and .agents/rules/ instructions as governing rules.

### Prompt A — Integration and reconstruction

You are Contributor A and integration owner for LOOM / VIDEO2PRINT. Read AGENTS.md, relevant .agents/rules/, project/CONTEXT.md, project/ROADMAP.md, and project/ISSUES.md. Inspect Git status and recent commits; run the current tests and record actual results. Own src/loom/reconstruction/, src/loom/pipeline/, src/loom/__main__.py, reconstruction smoke tests, and integration tests. Resolve/configure a real reconstruction backend, run real smartphone footage, verify the reconstruction-to-cleanup handoff, and integrate the other modules through agreed interfaces. Preserve existing CLI behavior where practical. Do not independently rewrite validation/printability/export. Coordinate shared contracts and dependencies. Do not overwrite uncommitted work, do not force-push, and never claim mock results are real reconstruction or physical accuracy. At completion report files, commit hash, tests/results, backend, artifacts, and blockers.

### Prompt B — Validation, printability, and export

You are Contributor B for LOOM / VIDEO2PRINT. Read AGENTS.md, relevant .agents/rules/, architecture/testing rules, and the current validation/printability/export implementations. Inspect Git status and recent commits. Own src/loom/validation/, src/loom/printability/, src/loom/export/, and their unit tests. Implement dimensions, ground-truth error metrics, appropriate mesh checks, useful reports, binary STL export, reload verification, and scale-preservation checks. Test known-good, invalid, empty, and defective synthetic meshes. Agree interfaces with Contributor A. Do not independently edit src/loom/pipeline/runner.py or src/loom/__main__.py. Do not hard-code pass results or equate watertightness/export success with printability. Respect the shared branch and never force-push. At completion report files, commit hash, tests/results, methods, and limitations.

### Prompt C — Capture quality and benchmarking

You are Contributor C for LOOM / VIDEO2PRINT. Read AGENTS.md, relevant .agents/rules/, the capture guide, and the project context/roadmap/experiment docs. Inspect Git status and recent commits. Own src/loom/capture/, its unit tests, capture documentation, project/EXPERIMENTS.md, and coordinated benchmark utilities. Improve capture quality/coverage warnings, create a repeatable physical measurement protocol, record ground-truth dimensions and capture conditions, and benchmark real runs when the backend is available. Record failures as well as successes. Do not independently edit the pipeline runner or CLI, fabricate measurements, or claim 2D marker detection alone establishes 3D scale. Respect the shared branch and never force-push. At completion report files, commit hash, tests/results, experiments, measured results, and blockers.

---

## 11. Immediate next actions

1. **Contributor A:** Run the current test suite and establish the real baseline; verify Python 3.10 and inspect the live reconstruction blocker.
2. **Contributor B:** Inspect the current validation/printability/export scaffolds, write the minimal interfaces/tests, and begin implementation with synthetic meshes.
3. **Contributor C:** Inspect capture modules, prepare the physical-object/ArUco measurement protocol, and establish the benchmark record format.
4. **All three:** Agree on units, mesh representation, stage results, and report schemas before integration.
5. **Contributor A:** Keep this plan and the roadmap aligned as verified milestones are completed.

**Priority rule:** If time becomes limited, prioritize a truthful, reproducible real-video-to-STL workflow and measured accuracy evidence over adding extra features. Clearly document any stage that remains blocked or unverified.
