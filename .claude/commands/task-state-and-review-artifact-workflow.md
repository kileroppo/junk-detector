---
name: task-state-and-review-artifact-workflow
description: Workflow command scaffold for task-state-and-review-artifact-workflow in junk-detector.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /task-state-and-review-artifact-workflow

Use this workflow when working on **task-state-and-review-artifact-workflow** in `junk-detector`.

## Goal

Add or update task state and review artifacts for a coverage or feature iteration.

## Common Files

- `.agents/tasks/*/context.json`
- `.agents/tasks/*/task.json`
- `.agents/tasks/*/features/FEAT-*.json`
- `.agents/tasks/*/*-review.md`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Create or update context.json, task.json, and feature JSON files in the relevant .agents/tasks/ subdirectory
- Add or update review artifact markdown files (e.g., 2025-01-15-160000-review.md)
- Commit all related files together

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.