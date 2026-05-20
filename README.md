# ServiceDeskLite

### Lightweight IT Help Desk & Infrastructure Ticketing System (Python)

ServiceDeskLite is a Python-based IT ticketing and operations simulator designed to replicate real-world help desk workflows, Active Directory-style user management, device tracking, and automated troubleshooting systems.

It is built as a portfolio project to demonstrate practical IT support, systems administration, and automation skills relevant to entry-level IT / help desk / sysadmin roles.

<img width="1536" height="1024" alt="ChatGPT Image May 20, 2026, 01_51_21 PM" src="https://github.com/user-attachments/assets/4077e059-56de-4aef-9795-89542b6b6a18" />

## Screenshots

<img width="1606" height="883" alt="image" src="https://github.com/user-attachments/assets/2b8315ec-a2c2-4b9b-a258-b21db7c31fda" />
<img width="1610" height="597" alt="image" src="https://github.com/user-attachments/assets/86c80876-a5d9-460f-bb31-dbef0078791a" />
<img width="1644" height="880" alt="image" src="https://github.com/user-attachments/assets/6c3a69f3-f951-4de3-83de-e83ff8b7a69a" />


---

## 🚀 Key Features

### 🎫 Ticketing System
- Create, update, and manage IT support tickets
- Ticket statuses:
  - Open
  - In Progress
  - Waiting on User
  - Escalated
  - Resolved
  - Closed
- Priority levels (Low / Medium / High / Critical)
- Automatic ticket ID generation
- Timestamped ticket history

---

### 🧠 Smart Ticket Routing
- Auto-categorization based on keywords:
  - Networking issues
  - Hardware issues
  - Software issues
  - Account / Access issues
- Intelligent routing to correct support tier
- Duplicate ticket detection (same issue/user/device)

---

### 🏢 Active Directory Simulation
- User account management system
- Group and role simulation (HR, IT, Sales, etc.)
- Password reset and account unlock workflows
- Permission assignment and role-based access control (RBAC)

---

### 💻 Device & Asset Management
- Track devices assigned to users
- Store:
  - Hostname
  - IP address
  - OS version
  - Device status
  - Assigned user
- Basic CMDB-style inventory system

---

### ⚙️ Automation & Troubleshooting Tools
- Built-in diagnostic toolkit (simulated IT scripts):
  - Network reset (ipconfig-style logic)
  - DNS flush simulation
  - Service restart simulation
  - Temporary file cleanup simulation
- Automated resolution suggestions based on ticket type

---

### 📊 SLA & Workflow Tracking
- SLA timers for ticket response/resolution
- Escalation rules for overdue tickets
- Technician assignment system
- Ticket lifecycle tracking

---

### 📈 Analytics Dashboard (Optional / Planned Expansion)
- Ticket volume by category
- Peak issue times
- Technician performance metrics
- Resolution time averages
- Recurring issue detection

---

### 🔐 Audit Logging
- Tracks:
  - Ticket creation and edits
  - User actions
  - Status changes
  - Admin operations
- Designed to mimic enterprise IT compliance logging

---

## 🧰 Tech Stack

- Python 3.x
- SQLite (local database storage)
- CLI or optional GUI (Tkinter / PyQt expansion planned)
- Modular architecture (planned evolution)

---

## 📦 Installation

```bash
git clone https://github.com/NathanEdwardsIT/ServiceDeskLite.git
cd ServiceDeskLite
pip install -r requirements.txt
python run.py
