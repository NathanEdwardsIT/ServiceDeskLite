# Help Desk Ticketing System

A portfolio-ready Python help desk / IT ticketing platform built to demonstrate systems thinking, documentation practices, and common enterprise IT workflows—including an **Active Directory simulation** with a full directory administration console.

## Screenshots

<img width="1632" height="875" alt="image" src="https://github.com/user-attachments/assets/bfd271a2-3e0d-4eff-bf56-9c0a89acc602" />
<img width="1638" height="680" alt="image" src="https://github.com/user-attachments/assets/33c56b37-df49-4ba2-a8ec-11a9bb141253" />
<img width="1609" height="798" alt="image" src="https://github.com/user-attachments/assets/27fe9e83-f7fc-4354-b4a9-f41fcf6a9433" />
<img width="1443" height="764" alt="image" src="https://github.com/user-attachments/assets/d1bb2da1-143b-46f2-998a-48b8db6e930f" />
<img width="1313" height="763" alt="image" src="https://github.com/user-attachments/assets/7072a43e-f3a4-4da8-8267-019536757797" />


## Features

| Area | Capabilities |
|------|----------------|
| **Tickets** | ITIL workflow engine, impact×urgency priority matrix, escalation levels, CSAT surveys |
| **Queue Ops** | Advanced search/filters, pagination, Kanban board, live queue stats |
| **REST API** | `/api/v1/tickets` JSON endpoints with OpenAPI docs at `/docs` |
| **SLA** | Priority-based timers, pause on pending, at-risk/breach tracking, live countdown |
| **Assignment** | Workload-balanced auto-assignment; manual reassignment |
| **Automation** | Keyword-triggered auto-resolution scripts (extensible Python modules) |
| **Duplicates** | Fuzzy text matching to flag likely duplicate tickets |
| **Knowledge Base** | Search + ticket-context article suggestions |
| **Devices** | Asset records + full ticket history per device |
| **Documentation** | Work notes (investigation/action/escalation) + formal resolution docs |
| **Dashboard** | Queue stats + technician performance (SLA compliance, resolution time) |
| **Security** | Role-based access control with group-granted permissions (Azure-style) |
| **Audit** | Full audit trail of creates, updates, assignments, resolutions |
| **Directory Admin** | Users, groups, OUs, permissions, org chart, bulk ops, account lock, role sync |
| **Incident timeline** | Unified per-ticket event stream (status, SLA, assignments, escalations) |
| **Device inventory** | Full asset lifecycle: stock, deploy, assign, retire, ticket history |
| **Password resets** | Request → approve → complete workflow with audit + linked ticket |
| **Employee provisioning** | One-click: AD user, email, groups, device, onboarding ticket |

## Quick Start

```bash
# From project root
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python seed.py
python run.py
```

Open **http://127.0.0.1:8000** and sign in.

**Port already in use (error 10048)?** Close the previous terminal or:

```powershell
netstat -ano | findstr :8000
taskkill /PID <pid_from_above> /F
```

Or: `$env:PORT=8001; python run.py`

**Upgrading an existing database** (schema auto-migrates on startup; optional scripts):

```powershell
python migrate_ad.py
python migrate_v2.py
```

### Demo Accounts

| User | Password | Role |
|------|----------|------|
| `admin` | `password` | Administrator |
| `lead1` | `password` | Team lead (performance dashboard) |
| `tech1` | `password` | Technician |
| `user1` | `password` | End user |

You can also log in with AD-style identifiers: `jsmith`, `jsmith@corp.local`.

## Interview Talking Points

1. **ITIL workflow** — Status changes follow validated transitions; invalid moves are rejected with clear errors.
2. **Priority matrix** — Impact × urgency auto-calculates priority on ticket creation (override optional).
3. **Kanban queue** — `/tickets?view=kanban` shows live SLA-aware columns for open work.
4. **REST API** — Integrate with `/api/v1/tickets`; explore schemas at `/docs`.
5. **Escalation & CSAT** — Escalate tickets (bumps priority + audit trail); requesters rate resolved tickets.
6. **Directory Admin** — Org chart from manager hierarchy, account lock/unlock, directory audit tab.
7. **Auto-resolution** — Create *"Forgot password need reset"* as `user1` → script auto-resolves.
8. **SLA pressure** — Create a **critical** ticket and watch timers on list/Kanban views.

## Project Structure

```
app/
  auth/           # AD simulation, RBAC, passwords
  models/         # SQLAlchemy entities & enums
  services/       # Business logic (tickets, SLA, workflow, queue, AD, etc.)
  routes/         # AD, devices, ops, tickets API routers
  scripts/auto_resolve/   # Pluggable auto-resolve scripts
  templates/      # Web UI (Jinja2)
  static/         # CSS + JS (tickets.js, ad.js)
  main.py         # FastAPI application
data/             # SQLite database (created at runtime)
seed.py           # Demo data loader
run.py            # Dev server entrypoint
```

## API Examples

```bash
# List open high-priority tickets (session cookie required after login)
GET /api/v1/tickets?priority=high&status=open

# Kanban board data
GET /api/v1/tickets/kanban

# Queue statistics
GET /api/v1/tickets/stats

# Create ticket (JSON)
POST /api/v1/tickets
{"title": "VPN down", "description": "Cannot connect from home", "impact": "high", "urgency": "high"}
```

## Tech Stack

- **Python 3.11+**
- **FastAPI** + **Jinja2** templates
- **SQLAlchemy** + **SQLite**
- **passlib** (bcrypt) for password hashing

## License

MIT — use freely for learning and job portfolio projects.
