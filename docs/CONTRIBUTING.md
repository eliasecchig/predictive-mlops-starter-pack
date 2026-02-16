# Contributing to Predictive MLOps Demo

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/predictive_mlops_demo.git`
3. Install dependencies: `make install`
4. Set up your dev environment (see README)

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/` - new features
- `fix/` - bug fixes
- `docs/` - documentation updates
- `refactor/` - code refactoring

### 2. Make Changes

- Follow existing code patterns and style
- Keep changes focused and atomic
- Write tests for new functionality
- Update documentation as needed

### 3. Test Your Changes

```bash
# Run unit tests
make test-unit

# Run integration tests (requires PROJECT_ID)
export PROJECT_ID=your-test-project
make test-integration

# Check code style
make lint

# Fix formatting issues
make format

# Test locally before submitting to cloud
make run-training-local
make run-scoring-local
```

### 4. Commit Your Changes

Follow the conventional commit format:

```
type: brief description

Longer explanation if needed (optional)
```

Types:
- `feat:` - new feature
- `fix:` - bug fix
- `docs:` - documentation only
- `refactor:` - code refactoring
- `test:` - adding or updating tests
- `chore:` - maintenance tasks

Examples:
```
feat: add model versioning support

fix: handle timezone-aware timestamps in feature engineering

docs: update quickstart guide with ARM Mac instructions
```

### 5. Submit a Pull Request

1. Push your branch: `git push origin feature/your-feature-name`
2. Open a PR against the `main` branch
3. Include:
   - Clear description of changes
   - Related issue numbers (if applicable)
   - Testing performed
   - Breaking changes (if any)

## Code Guidelines

### Python Style

- Follow PEP 8
- Use type hints where appropriate
- Keep functions focused and testable
- Document complex logic with comments
- Use descriptive variable names

### Testing

- Write unit tests for business logic
- Add integration tests for cloud interactions
- Aim for meaningful test coverage, not 100%
- Use fixtures for reusable test data
- Mock external dependencies in unit tests

### Documentation

- Update README if adding new features
- Update CLAUDE.md / GEMINI.md with new gotchas
- Add docstrings to public functions
- Include usage examples for new features

## Project Structure

```
fraud_detector/        # Main package - all business logic
  model.py            # Core model class
  config.py           # Config loading
  pipelines/          # KFP pipeline definitions
    components/       # Individual pipeline components

tests/
  unit/              # Unit tests (no cloud dependencies)
  integration/       # Integration tests (require PROJECT_ID)

deployment/
  terraform/         # Infrastructure as code

scripts/             # Setup and utility scripts
```

## Key Design Principles

1. **Config-driven** - All parameters in YAML files, no hardcoded values
2. **Local-first** - Test locally before cloud submission
3. **Thin wrappers** - KFP components call library functions, business logic stays in the main package
4. **Single source of truth** - BigQuery for all data (raw + features + predictions)
5. **Minimal dependencies** - Add new packages only when necessary

## Common Pitfalls

See `CLAUDE.md` or `GEMINI.md` for detailed gotchas. Key ones:

- BigQuery returns Decimals → always `.astype(float)` for model input
- Timezone-aware timestamps → strip tz or guard comparisons
- KFP type checking is strict → `float(value)` not `int`
- ARM Mac builds → use `--platform linux/amd64`

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas
- Check existing issues before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
