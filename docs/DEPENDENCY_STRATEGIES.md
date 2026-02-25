# WaveOS Dependency Strategies

## Problem

Target environments may have incompatible libraries, runtimes, or OS versions. WaveOS must tolerate dependency mismatches without requiring host modifications.

## Strategies

### 1. Bundled Runtime (MVP)

Ship all required libraries and runtime with the application.

- **Pros**: Zero host dependencies, fully reproducible
- **Cons**: Larger bundle size
- **Use case**: Air-gapped environments, defense systems

### 2. Side-by-Side Install (MVP)

Install multiple versions under a structured path:

```
/opt/waveos/apps/
  myapp/
    v1.0.0/
    v1.1.0/
    v2.0.0/
```

- **Pros**: Zero conflict, instant rollback, atomic activation
- **Cons**: More disk space
- **Use case**: All environments (default strategy)

### 3. Container Runtime (Optional)

Run in Docker/Podman containers for full isolation.

- **Pros**: Complete isolation, works with any legacy stack
- **Cons**: Requires container runtime on host
- **Use case**: Enterprise environments with container support

### 4. VM Wrapper (Optional)

Run in a virtual machine for extreme legacy stacks.

- **Pros**: Complete isolation including kernel
- **Cons**: Heavy resource usage
- **Use case**: Legacy RTOS compatibility

## Runtime Strategy Plugin Interface

Strategies are selected via the `runtimes.strategy` field in the bundle manifest:

```json
{
  "runtimes": {
    "strategy": "side_by_side",
    "runtime_version": "python3.11",
    "dependencies": ["pydantic>=2.7", "rich>=13.7"],
    "isolation": "none"
  }
}
```

## CLI

```bash
waveos compat check <bundle_dir>
```
