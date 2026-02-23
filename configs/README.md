# WaveOS configs

## Production profile

- **`production.toml`** – Production defaults: action signing required, strict secrets (no env fallback), enforcement lock paths, safe drift strategy. Use with:
  ```bash
  waveos --config configs/production.toml run --in ... --baseline ... --out ...
  ```
- **`coordinator.production.env`** – Env vars for running the coordinator in production (mTLS required, audit path). Source before `waveos coordinator serve`:
  ```bash
  set -a && source configs/coordinator.production.env && set +a && waveos coordinator serve
  ```
  Or: `env $(grep -v '^#' configs/coordinator.production.env | xargs) waveos coordinator serve`

## RBAC (v1.1)

Per-site and per-node permissions and capability-based authorization are in scope for v1.1 when required by the buyer. The coordinator has the framework (identity, audit); enforcement of allowed_node_ids / allowed_site_ids is optional and can be enabled via config or env.
