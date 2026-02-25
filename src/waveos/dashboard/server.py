"""Operator dashboard — HTML fleet view, rollout progress, approvals, health, evidence retrieval."""

from __future__ import annotations

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.dashboard.server")

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WaveOS Operator Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0f172a;color:#e2e8f0}header{background:#1e293b;padding:1rem 2rem;border-bottom:2px solid #3b82f6}
h1{font-size:1.5rem;color:#60a5fa}.card{background:#1e293b;border-radius:8px;padding:1.5rem;margin:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem;padding:1rem 2rem}
table{width:100%;border-collapse:collapse;margin-top:0.5rem}th,td{padding:0.5rem;text-align:left;
border-bottom:1px solid #334155}th{color:#94a3b8;font-size:0.85rem;text-transform:uppercase}
.badge{display:inline-block;padding:0.2rem 0.6rem;border-radius:4px;font-size:0.8rem;font-weight:600}
.badge-ok{background:#065f46;color:#6ee7b7}.badge-warn{background:#78350f;color:#fbbf24}
.badge-err{background:#7f1d1d;color:#fca5a5}.badge-info{background:#1e3a5f;color:#93c5fd}
#fleet-data,#registry-data,#governance-data,#drills-data{min-height:60px}
nav{display:flex;gap:1rem;padding:0.5rem 2rem;background:#1e293b;border-bottom:1px solid #334155}
nav a{color:#93c5fd;text-decoration:none;padding:0.5rem 1rem;border-radius:4px}
nav a:hover{background:#334155}.refresh-btn{background:#3b82f6;color:#fff;border:none;padding:0.4rem 1rem;
border-radius:4px;cursor:pointer;margin-left:auto}.refresh-btn:hover{background:#2563eb}
</style></head><body>
<header><h1>WaveOS Operator Dashboard</h1></header>
<nav><a href="#fleet">Fleet</a><a href="#registry">Registry</a><a href="#governance">Governance</a>
<a href="#drills">Drills</a><button class="refresh-btn" onclick="loadAll()">Refresh</button></nav>
<div class="grid">
<div class="card" id="fleet-section"><h2>Fleet Status</h2><div id="fleet-data">Loading...</div></div>
<div class="card" id="registry-section"><h2>Registry</h2><div id="registry-data">Loading...</div></div>
<div class="card" id="governance-section"><h2>Governance Log</h2><div id="governance-data">Loading...</div></div>
<div class="card" id="drills-section"><h2>Failure Drills</h2><div id="drills-data">Loading...</div></div>
</div>
<script>
function badge(cls,text){return `<span class="badge badge-${cls}">${text}</span>`}
async function loadFleet(){try{const r=await fetch('/api/fleet');const d=await r.json();
let h='<table><tr><th>Node</th><th>Bundle</th><th>Status</th></tr>';
(d.nodes||[]).forEach(n=>{h+=`<tr><td>${n.node_id}</td><td>${n.bundle||'—'}</td><td>${badge(n.healthy?'ok':'warn',n.healthy?'OK':'Stale')}</td></tr>`});
h+='</table>';document.getElementById('fleet-data').innerHTML=h}catch(e){document.getElementById('fleet-data').innerHTML='<p>'+e+'</p>'}}
async function loadRegistry(){try{const r=await fetch('/api/registry');const d=await r.json();
let h='<table><tr><th>Bundle</th><th>Channel</th><th>Version</th></tr>';
(d.bundles||[]).forEach(b=>{h+=`<tr><td>${b.bundle_id}</td><td>${badge('info',b.channel)}</td><td>${b.version}</td></tr>`});
h+='</table>';document.getElementById('registry-data').innerHTML=h}catch(e){document.getElementById('registry-data').innerHTML='<p>'+e+'</p>'}}
async function loadGovernance(){try{const r=await fetch('/api/governance');const d=await r.json();
let h='<table><tr><th>Action</th><th>Actor</th><th>Bundle</th><th>Time</th></tr>';
(d.events||[]).slice(-10).forEach(e=>{h+=`<tr><td>${badge('info',e.event_type)}</td><td>${e.actor}</td><td>${e.bundle_id||'—'}</td><td>${(e.timestamp||'').slice(0,19)}</td></tr>`});
h+='</table>';document.getElementById('governance-data').innerHTML=h}catch(e){document.getElementById('governance-data').innerHTML='<p>'+e+'</p>'}}
async function loadDrills(){try{const r=await fetch('/api/drills');const d=await r.json();
let h='<table><tr><th>Drill</th><th>Type</th><th>Expected</th></tr>';
(d.drills||[]).forEach(dr=>{h+=`<tr><td>${dr.name}</td><td>${badge('info',dr.drill_type)}</td><td>${dr.expected_behavior.slice(0,60)}...</td></tr>`});
h+='</table>';document.getElementById('drills-data').innerHTML=h}catch(e){document.getElementById('drills-data').innerHTML='<p>'+e+'</p>'}}
function loadAll(){loadFleet();loadRegistry();loadGovernance();loadDrills()}
loadAll();setInterval(loadAll,30000);
</script></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer

    def log_message(self, format, *args) -> None:
        logger.debug("Dashboard: %s", format % args)

    def _json(self, data: Any) -> None:
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        if path in ("", "/", "/dashboard"):
            body = DASHBOARD_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/fleet":
            self._json(self.server.data_provider.get_fleet_data())
        elif path == "/api/registry":
            self._json(self.server.data_provider.get_registry_data())
        elif path == "/api/governance":
            self._json(self.server.data_provider.get_governance_data())
        elif path == "/api/drills":
            self._json(self.server.data_provider.get_drills_data())
        elif path == "/api/health":
            self._json({"status": "ok", "timestamp": utc_now().isoformat()})
        else:
            self.send_response(404)
            self.end_headers()


class DashboardDataProvider:
    """Provides data to the dashboard from various WaveOS subsystems."""

    def __init__(self, registry_root: Optional[Path] = None, governance_log: Optional[Path] = None,
                 nodes_file: Optional[Path] = None) -> None:
        self.registry_root = registry_root or Path("out/registry")
        self.governance_log = governance_log
        self.nodes_file = nodes_file

    def get_fleet_data(self) -> Dict[str, Any]:
        nodes = []
        if self.nodes_file and self.nodes_file.exists():
            try:
                from waveos.orchestration import load_nodes_from_file, get_node_registry
                load_nodes_from_file(self.nodes_file)
                for nid, rec in get_node_registry().items():
                    nodes.append({"node_id": nid, "role": rec.role.value if hasattr(rec.role, 'value') else str(rec.role),
                                  "site_id": getattr(rec, 'site_id', ''), "bundle": "", "healthy": True})
            except Exception:
                pass
        return {"nodes": nodes, "timestamp": utc_now().isoformat()}

    def get_registry_data(self) -> Dict[str, Any]:
        bundles = []
        try:
            from waveos.registry.store import RegistryStore
            store = RegistryStore(self.registry_root)
            for entry in store.list_bundles():
                bundles.append(entry.to_dict())
        except Exception:
            pass
        return {"bundles": bundles, "timestamp": utc_now().isoformat()}

    def get_governance_data(self) -> Dict[str, Any]:
        events = []
        if self.governance_log and self.governance_log.exists():
            try:
                data = json.loads(self.governance_log.read_text(encoding="utf-8"))
                events = data if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError):
                pass
        return {"events": events, "timestamp": utc_now().isoformat()}

    def get_drills_data(self) -> Dict[str, Any]:
        try:
            from waveos.fleet.drills import list_drills
            return {"drills": [d.to_dict() for d in list_drills()], "timestamp": utc_now().isoformat()}
        except Exception:
            return {"drills": [], "timestamp": utc_now().isoformat()}


class DashboardHTTPServer(HTTPServer):
    def __init__(self, addr, data_provider: DashboardDataProvider, **kwargs) -> None:
        self.data_provider = data_provider
        super().__init__(addr, DashboardHandler, **kwargs)


class DashboardServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9300, **kwargs) -> None:
        self.host = host
        self.port = port
        self.provider = DashboardDataProvider(**kwargs)

    def serve(self) -> None:
        server = DashboardHTTPServer((self.host, self.port), self.provider)
        logger.info("Dashboard on http://%s:%d", self.host, self.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


def run_dashboard(host: str = "0.0.0.0", port: int = 9300, registry_root: str = "out/registry",
                  governance_log: Optional[str] = None, nodes_file: Optional[str] = None) -> None:
    provider = DashboardDataProvider(
        registry_root=Path(registry_root),
        governance_log=Path(governance_log) if governance_log else None,
        nodes_file=Path(nodes_file) if nodes_file else None,
    )
    server = DashboardHTTPServer((host, port), provider)
    logger.info("Dashboard on http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
