# Testing

## Coverage Targets
- Unit tests: >= 80%
- Integration tests: cover baseline/run/report outputs

## Suites
- `pytest -q tests/test_pipeline_integration.py`
- `pytest -q tests/test_fault_injection.py`
- `pytest -q tests/test_rbac.py`

## Load/Perf
- `waveos load-test --out ./out/load --links 200 --samples 200`
