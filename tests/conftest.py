"""Pytest configuration. Ensures WAVEOS_LICENSE_KEY is set for CLI and integration tests."""

import os

# Use CI/test license key so subprocess CLI invocations (e.g. test_cli_e2e) pass license check.
# CI already sets this; local runs get it here.
if "WAVEOS_LICENSE_KEY" not in os.environ and "WAVEOS_LICENSE_SKIP" not in os.environ:
    os.environ["WAVEOS_LICENSE_KEY"] = "WAVEOS-CI-20991231-TEST"
