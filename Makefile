.PHONY: help

help:
	@echo "Wave OS dev skeleton"

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
