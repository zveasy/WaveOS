.PHONY: help lint test coverage docker-build docker-smoke observability-validate release-rc

help:
	@echo "Wave OS — development and production targets"
	@echo ""
	@echo "  make lint           Run Ruff check and format check"
	@echo "  make test           Run pytest"
	@echo "  make coverage       Run pytest with coverage report (fail-under 45%%)"
	@echo "  make docker-build   Build production image (waveos:latest)"
	@echo "  make docker-smoke   Build image and run health-check + pipeline smoke"
	@echo "  make observability-validate  Generate data, run pipeline, sample metrics"
	@echo "  make release-rc     Tag and push a release candidate (VERSION=x.y.z RC=n)"

lint:
	ruff check src tests && ruff format --check src tests

test:
	pytest -q

coverage:
	pytest --cov=src/waveos --cov-report=term-missing --cov-report=xml
	coverage report --fail-under=45

docker-build:
	docker build -t waveos:latest .

docker-smoke: docker-build
	@echo "--- health-check ---"
	docker run --rm -e WAVEOS_LICENSE_KEY=$${WAVEOS_LICENSE_KEY:-WAVEOS-CI-20991231-TEST} waveos:latest health-check
	@echo "--- pipeline smoke ---"
	docker run --rm -e WAVEOS_LICENSE_KEY=$${WAVEOS_LICENSE_KEY:-WAVEOS-CI-20991231-TEST} waveos:latest sh -c \
	  "waveos sim --out /data/demo && waveos baseline --in /data/demo/baseline && \
	   waveos run --in /data/demo/run --baseline /data/demo/baseline --out /data/out && \
	   test -f /data/out/health_summary.json && test -f /data/out/report.html && echo Pipeline OK"

observability-validate:
	@out_dir="out/observability"; \
	metrics_port="$${WAVEOS_METRICS_PORT:-9109}"; \
	echo "Generating demo data in $$out_dir"; \
	PYTHONPATH=src python -m waveos.cli sim --out "$$out_dir"; \
	echo "Building baseline with metrics on port $$metrics_port"; \
	PYTHONPATH=src WAVEOS_METRICS_PORT="$$metrics_port" python -m waveos.cli baseline --in "$$out_dir/baseline"; \
	echo "Running pipeline and sampling metrics"; \
	PYTHONPATH=src WAVEOS_METRICS_PORT="$$metrics_port" python -m waveos.cli run --in "$$out_dir/run" --baseline "$$out_dir/baseline" --out "$$out_dir/report" & \
	pid=$$!; \
	sleep 1; \
	if command -v curl >/dev/null 2>&1 && command -v rg >/dev/null 2>&1; then \
		curl -s "http://localhost:$$metrics_port/metrics" | rg "waveos_(telemetry_ingested|normalize_errors|normalize_duration|scoring_duration)" || true; \
	else \
		echo "curl and/or rg not found; skipping metrics scrape"; \
	fi; \
	wait $$pid; \
	echo "Validation run complete. Report: $$out_dir/report/report.html"

.PHONY: release-rc
release-rc:
	@test -n "$(VERSION)" || (echo "VERSION is required, e.g. VERSION=1.3.0" && exit 1)
	@test -n "$(RC)" || (echo "RC is required, e.g. RC=1" && exit 1)
	@git diff --quiet || (echo "Working tree not clean. Commit or stash changes first." && exit 1)
	@git diff --cached --quiet || (echo "Index not clean. Commit staged changes first." && exit 1)
	@tag="v$(VERSION)-rc$(RC)"; \
	git rev-parse -q --verify "refs/tags/$$tag" >/dev/null && (echo "Tag $$tag already exists" && exit 1) || true; \
	echo "Creating tag $$tag"; \
	git tag -a $$tag -m "Wave OS release candidate $$tag"; \
	git push origin $$tag
