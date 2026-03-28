# AetherEdge

**Open source edge node provisioning and AI workload dispatch.**

AetherEdge turns any x86 machine into a managed edge worker — securely registered, remotely tasked, and capable of running AI agents or Docker workloads without anyone physically present.

Inspired by projects like Dell NativeEdge and Balena.io. Built to be the open, lightweight, hardware-agnostic alternative.

> ⚠️ **Early-stage prototype.** Works for small fleets today (~50 nodes). Production hardening is in progress. Contributors welcome.

---

## What it does

```
Plug in machine → runs node software → appears in dashboard → deploy tasks from UI
```

- **Zero-touch node registration** — hardware fingerprint + Ed25519 identity + mTLS
- **Secure workload dispatch** — orchestrator assigns tasks; nodes pull and execute them
- **Two workload types:**
  - **Scripts** — Python agents (e.g. system health monitor, AI analytics)
  - **Blueprints** — Docker Compose apps (e.g. logistics tracker)
- **AI agent support** — CrewAI-style multi-agent crews run on edge nodes
- **Web dashboard** — deploy tasks, monitor nodes, inspect results

---

## Architecture

```
┌─────────────────────────────────┐
│         AetherOrchestrator      │  FastAPI + SQLite
│  Port 8000 (bootstrap HTTP)     │  Node registry, task queue
│  Port 8001 (mTLS)               │  Certificate authority
└──────────────┬──────────────────┘
               │ mTLS (mutual TLS)
    ┌──────────┴──────────┐
    │    AetherEdge Node  │  Any x86 machine
    │  Ed25519 identity   │  Hardware fingerprint
    │  Heartbeat every 5s │  Pulls and executes tasks
    │  Zero-footprint     │  Cleans up after itself
    └─────────────────────┘
```

---

## Quick start

**Requirements:** Python 3.9+, Docker (for blueprint workloads)

```bash
git clone https://github.com/your-org/aetheredge
cd aetheredge
pip3 install -r requirements.txt
```

**Terminal 1 — start orchestrator:**
```bash
python3 scripts/start_orchestrator.py
```

**Terminal 2 — start a node:**
```bash
python3 scripts/run_node.py
```

**Terminal 3 — open the dashboard:**
```bash
python3 -m streamlit run scripts/aether_view.py
```

Go to `http://localhost:8501` — your node appears as 🟢 ONLINE. Deploy tasks from the sidebar.

---

## Deploying a task

**Via dashboard:** Select node → choose workload type → click Deploy.

**Via CLI:**
```bash
# Script task
python3 scripts/create_task.py --node-id <node-id> --script-name maintenance_agent.py

# Blueprint task
python3 scripts/create_task.py --node-id <node-id> --script-name tpp_logistics.yml --workload-type blueprint
```

---

## Project layout

```
aetheredge/          # Node client library
  identity.py        # Ed25519 keypair + hardware fingerprint
  handshake.py       # Registration with orchestrator
  certs.py           # mTLS certificate handling
  runner.py          # Script + Docker Compose workload execution
  qr.py              # QR code display

orchestrator/        # Central control server (FastAPI)
  main.py            # App startup, migrations, stale node checker
  models.py          # SQLAlchemy ORM (Node, Task, BootstrapToken)
  routers/           # API endpoints
  registry/          # Python agent scripts served to nodes
  blueprints/        # Docker Compose templates served to nodes

scripts/             # CLI and launch utilities
tests/               # 31 pytest tests (unit + integration)
config/config.yaml   # Default configuration
```

---

## Configuration

Edit `config/config.yaml` or set environment variables:

| Variable | Default | Description |
|--|--|--|
| `AETHER_ORCHESTRATOR_URL` | `https://localhost:8001` | mTLS orchestrator URL |
| `AETHER_BOOTSTRAP_URL` | `http://localhost:8000` | Plain HTTP bootstrap URL |
| `AETHER_PORT` | `7331` | Node local listen port |
| `ADMIN_API_KEY` | _(none)_ | Admin endpoint protection |

---

## Security model

- **mTLS** — all node↔orchestrator communication after bootstrap requires mutual TLS
- **Bootstrap tokens** — one-time, MAC-address-bound, 10-minute expiry
- **Hardware identity** — node ID derived from MAC + hostname + Ed25519 public key
- **Workload isolation** — scripts run in subprocess with sanitised environment (no cert paths, keys, or tokens exposed)
- **Zero-footprint** — downloaded scripts and blueprints deleted after execution

---

## Running tests

```bash
python3 -m pytest tests/ -v
```

31 tests covering identity, certificates, QR codes, full task lifecycle, blueprint validation, and the CrewAI agent.

---

## Comparison

| | AetherEdge | Dell NativeEdge | Balena.io |
|--|--|--|--|
| Open source | ✅ | ❌ | Partial |
| Any hardware | ✅ | ✅ (since 2024) | ✅ |
| AI agent dispatch | ✅ | ❌ | ❌ |
| Scale | ~50 nodes | 50,000+ nodes | Thousands |
| Cost | Free | Enterprise $$$ | Free tier |
| Production-ready | ⚠️ In progress | ✅ | ✅ |

---

## Roadmap

- [ ] PostgreSQL support (replace SQLite for production scale)
- [ ] Prometheus metrics + Grafana dashboard
- [ ] Real CrewAI integration (requires `ANTHROPIC_API_KEY`)
- [ ] iPXE / network boot support (true zero-touch)
- [ ] TOSCA blueprint standard (replace Docker Compose)
- [ ] Multi-orchestrator HA clustering
- [ ] Structured audit logging

---

## Contributing

This is an early-stage project and contributions are very welcome.

1. Fork the repo
2. Create a feature branch
3. Run tests: `python3 -m pytest tests/`
4. Open a PR with a clear description

---

## License

MIT — see [LICENSE](LICENSE)
