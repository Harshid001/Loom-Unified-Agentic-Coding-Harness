# Contributing to Loom

Thank you for contributing to Loom — Unified Agentic Coding Harness!

## Development Setup

1. **Clone repository and setup environment**:
   ```bash
   git clone <repo-url>
   cd loom
   pip install -e .[dev]
   ```

2. **Run Linter & Type Checks**:
   ```bash
   ruff check loom/
   mypy loom/ --ignore-missing-imports
   ```

3. **Run Test Suite**:
   ```bash
   pytest
   ```

4. **Web Frontend Development**:
   ```bash
   cd web
   npm install
   npm run lint
   npm run build
   ```

## Pre-Commit Standards
- Ensure 0 Ruff lint errors (`ruff check loom/`).
- Ensure 0 Mypy type errors (`mypy loom/ --ignore-missing-imports`).
- Ensure all automated unit and CLI integration tests pass (`pytest`).
- Ensure frontend passes ESLint (`npm run lint`).
