#!/usr/bin/env python3
"""
WaveOS Fleet Deploy — deploy a bundle to multiple hosts via SSH.

Usage:
  python scripts/fleet_deploy.py --hosts "node1,node2" --bundle-id my-app-1.0 --cache /path/to/cache
  python scripts/fleet_deploy.py --nodes-file out/nodes.json --bundle-id my-app-1.0 --cache /path/to/cache

Options:
  --hosts         Comma-separated SSH hosts (user@host or host).
  --nodes-file    Path to nodes.json; uses node_id as host (or meta.ssh_host if set).
  --canary-sites  Only deploy to nodes in these site IDs (comma-separated; Fleet Phase 2 canary-by-site).
  --bundle-id     Bundle ID to install.
  --cache         Path to bundle cache (or --bundle-dir for a single bundle directory).
  --bundle-dir    Path to bundle directory (alternative to --cache + --bundle-id).
  --ssh-user      SSH user (default: current user).
  --ssh-opts      Extra SSH options (e.g. "-i key.pem").
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy WaveOS bundle to multiple hosts")
    ap.add_argument("--hosts", type=str, help="Comma-separated SSH hosts")
    ap.add_argument("--nodes-file", type=str, help="Path to nodes.json (node_id or meta.ssh_host used as host)")
    ap.add_argument("--canary-sites", type=str, help="Only deploy to nodes in these site IDs (comma-separated)")
    ap.add_argument("--bundle-id", type=str, help="Bundle ID (when using --cache)")
    ap.add_argument("--cache", type=str, help="Path to bundle cache directory")
    ap.add_argument("--bundle-dir", type=str, help="Path to single bundle directory (instead of cache)")
    ap.add_argument("--ssh-user", type=str, default="", help="SSH user (default: current)")
    ap.add_argument("--ssh-opts", type=str, default="", help="Extra SSH options")
    args = ap.parse_args()

    hosts: list[str] = []
    if args.hosts:
        hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    if args.nodes_file:
        path = Path(args.nodes_file)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                nodes = data.get("nodes", data) if isinstance(data, dict) else data
                if isinstance(nodes, list):
                    canary_sites = None
                    if getattr(args, "canary_sites", None):
                        canary_sites = {s.strip() for s in args.canary_sites.split(",") if s.strip()}
                    for n in nodes:
                        if isinstance(n, dict):
                            if canary_sites:
                                site = n.get("site_id")
                                if site not in canary_sites:
                                    continue
                            h = n.get("meta", {}).get("ssh_host") or n.get("node_id")
                            if h:
                                hosts.append(h)
            except Exception as e:
                print(f"Failed to load nodes: {e}", file=sys.stderr)
                return 1

    if not hosts:
        print("No hosts (use --hosts or --nodes-file)", file=sys.stderr)
        return 1

    if args.bundle_dir:
        install_cmd = f"waveos bundle install --dir {args.bundle_dir}"
    elif args.cache and args.bundle_id:
        install_cmd = f"waveos bundle install --from-cache {args.cache} --bundle-id {args.bundle_id}"
    else:
        print("Use --bundle-dir or both --cache and --bundle-id", file=sys.stderr)
        return 1

    user = f"{args.ssh_user}@" if args.ssh_user else ""
    opts = args.ssh_opts.strip()
    failed = 0
    for host in hosts:
        target = f"{user}{host}" if user else host
        cmd = ["ssh"] + (opts.split() if opts else []) + [target, install_cmd]
        print(f"Deploying to {target}...")
        try:
            r = subprocess.run(cmd, timeout=60)
            if r.returncode != 0:
                failed += 1
        except Exception as e:
            print(f"  Failed: {e}", file=sys.stderr)
            failed += 1
    if failed:
        print(f"{failed}/{len(hosts)} hosts failed", file=sys.stderr)
        return 1
    print(f"Deployed to {len(hosts)} hosts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
