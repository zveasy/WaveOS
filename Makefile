.PHONY: help observability-validate

help:
	@echo "Wave OS dev skeleton"

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
