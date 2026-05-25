```markdown
# junk-detector Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the key development conventions and workflows used in the `junk-detector` Python repository. You'll learn how to structure code, follow commit and file naming standards, manage feature and task coverage, and contribute to the project using established step-by-step workflows. This guide is ideal for contributors seeking to maintain consistency and quality in the codebase.

## Coding Conventions

### File Naming
- Use **snake_case** for all Python files and modules.
  - Example: `junk_detector.py`, `feature_extractor.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import clean_text
    from .models import JunkModel
    ```

### Export Style
- Use **named exports** (explicitly define what is exported).
  - Example:
    ```python
    __all__ = ["JunkDetector", "detect_junk"]
    ```

### Commit Messages
- Follow **Conventional Commits**.
  - Prefixes: `feat`, `chore`
  - Example:
    ```
    feat: add junk detection for HTML email content
    chore: update dependencies and clean up imports
    ```

## Workflows

### Feature Test Coverage Workflow
**Trigger:** When you want to improve test coverage for a feature or module and track its completion.  
**Command:** `/add-feature-tests`

1. Write or update test files for the target module(s) in `tests/`.
2. Optionally, update or create a feature JSON file in `.agents/tasks/task-coverage-75/features/` (e.g., `FEAT-003.json`).
3. Commit the test files and feature JSON file together.
4. In a subsequent commit, mark the feature as completed by updating the same feature JSON file.

**Files Involved:**
- `tests/test_*.py`
- `.agents/tasks/task-coverage-75/features/FEAT-*.json`

**Example:**
```bash
# Step 1: Add a new test
vim tests/test_junk_detector.py

# Step 2: Update feature JSON
vim .agents/tasks/task-coverage-75/features/FEAT-003.json

# Step 3: Commit together
git add tests/test_junk_detector.py .agents/tasks/task-coverage-75/features/FEAT-003.json
git commit -m "feat: add tests and update feature coverage for FEAT-003"

# Step 4: Mark feature as completed in a follow-up commit
vim .agents/tasks/task-coverage-75/features/FEAT-003.json
git add .agents/tasks/task-coverage-75/features/FEAT-003.json
git commit -m "chore: mark FEAT-003 as completed"
```

---

### Task State and Review Artifact Workflow
**Trigger:** When you want to record the state, context, and review of a task iteration.  
**Command:** `/add-task-state`

1. Create or update `context.json`, `task.json`, and relevant feature JSON files in the appropriate `.agents/tasks/` subdirectory.
2. Add or update review artifact markdown files (e.g., `2025-01-15-160000-review.md`).
3. Commit all related files together.

**Files Involved:**
- `.agents/tasks/*/context.json`
- `.agents/tasks/*/task.json`
- `.agents/tasks/*/features/FEAT-*.json`
- `.agents/tasks/*/*-review.md`

**Example:**
```bash
# Step 1: Update task state and context
vim .agents/tasks/task-coverage-75/context.json
vim .agents/tasks/task-coverage-75/task.json

# Step 2: Add a review artifact
vim .agents/tasks/task-coverage-75/2025-01-15-160000-review.md

# Step 3: Commit all together
git add .agents/tasks/task-coverage-75/context.json \
        .agents/tasks/task-coverage-75/task.json \
        .agents/tasks/task-coverage-75/2025-01-15-160000-review.md
git commit -m "chore: update task state and add review artifact for coverage iteration"
```

## Testing Patterns

- **Test files** are Python scripts located in the `tests/` directory and follow the pattern: `test_*.py`.
- The testing framework is **not specified**; use standard Python testing tools (e.g., `unittest`, `pytest`) as appropriate.
- Example test file:
  ```python
  # tests/test_junk_detector.py
  from ..junk_detector import detect_junk

  def test_detect_junk_with_spam():
      assert detect_junk("Buy now!") is True
  ```

## Commands

| Command            | Purpose                                                        |
|--------------------|----------------------------------------------------------------|
| /add-feature-tests | Add or update tests and track feature coverage completion      |
| /add-task-state    | Record or update task state, context, and review artifacts     |
```
