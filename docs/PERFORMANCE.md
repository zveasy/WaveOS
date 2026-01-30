# Performance and Profiling

## Baselines
- Run `waveos load-test` to capture samples/sec.
- Store results in version control for trend tracking.

## Profiling
```
waveos profile --in ./demo_data/run --baseline ./demo_data/baseline --out ./out --profile ./out/profile.pstats
```

## Perf Artifacts (CI)
- CI uploads `perf-artifacts` containing:
  - `out/load/load_test.json`
  - `out/profile.pstats`
  - `out/profile_run/**` (report, run_meta, metrics.csv)
- Download in GitHub Actions: open the `perf` job → Artifacts → `perf-artifacts`.

## Parallelism
- Configure `collector_threads` to parallelize file collectors.
