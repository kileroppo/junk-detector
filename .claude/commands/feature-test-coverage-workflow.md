---
name: feature-test-coverage-workflow
description: Workflow command scaffold for feature-test-coverage-workflow in junk-detector.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /feature-test-coverage-workflow

Use this workflow when working on **feature-test-coverage-workflow** in `junk-detector`.

## Goal

Add comprehensive tests for a module or set of modules, track coverage, and mark the related feature as completed.

## Common Files

- `tests/test_*.py`
- `.agents/tasks/task-coverage-75/features/FEAT-*.json`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Write or update test files for the target module(s) in tests/
- Optionally update or create a feature JSON file in .agents/tasks/task-coverage-75/features/ (e.g., FEAT-003.json, FEAT-004.json, FEAT-006.json)
- Commit test files and feature JSON together
- In a subsequent commit, mark the feature as completed by updating the same feature JSON file

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.