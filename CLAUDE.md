# AetherEdge

# 🛸 Project: AetherEdge

**Vision:** *The "Apple of the Edge"—Zero-Touch AI Agent infrastructure for the Missing Middle.*

## 1. Executive Summary

- **Problem:** Current Edge platforms (EdgeX, KubeEdge) are too complex for non-technical business owners. They require manual OS installation and complex cloud configuration.
- **Solution:** A protocol that allows any bare-metal CPU with an ethernet port to become a "Sovereign AI Worker" via a simple **Plug -> Scan -> Work** flow.
- **Key Innovation:** Combining **iPXE network booting** with **QR-based JWT identity** to bypass the "Manual Setup" barrier.

---

## 2. Technical Architecture (The 4-Layer Stack)

### Layer 1: The "Hardware" (Bare Metal)

- **Target:** x86 (old laptops, NUCs) or ARM (Raspberry Pi 4/5).
- **Requirement:** PXE Boot capability + Ethernet connection.

### Layer 2: The "AetherBoot" (Provisioning)

- **Mechanism:** iPXE Bootloader.
- **OS:** **Alpine Linux (Micro-OS)** — volatile, in-memory, highly secure.
- **Process:** On boot, the device fetches the latest kernel from the AetherCloud.

### Layer 3: The "Identity Handshake" (Security)

- **Node ID:** Unique hash of MAC address + CPU Serial.
- **UI:** Local web-server displays a unique **Claiming QR**.
- **Auth:** Mobile scan triggers a **JWT (JSON Web Token)** issuance, pairing the hardware to the user's account.

### Layer 4: The "Agentic Runtime" (Execution)

- **Container Engine:** Docker / K3s.
- **AI Framework:** **CrewAI** (for role-based team tasks) or **LangGraph**.
- **Mission:** Automatic pulling of "Workforce Pods" based on the user's business needs (e.g., TPP Logistics Tracker).

---

## 3. The Implementation Roadmap (Phase-Wise)

### 🟢 Phase A: The Local Cloud (Days 1-3)

- **Goal:** Set up a laptop as the "AetherCloud" server.
- **Tasks:**
    - Configure a DHCP/TFTP server to host iPXE.
    - Test booting a Virtual Machine (VM) over the network.
- **Success:** A blank VM boots into an Alpine Linux shell without a hard drive.

### 🟡 Phase B: The Handshake Logic (Days 4-7)

- **Goal:** Build the "Claiming" system.
- **Tasks:**
    - Write Python script `identity.py` to generate the Node ID.
    - Create a simple Flask API for the QR-Scan-to-JWT flow.
- **Success:** Scanning a QR on a phone registers the node in a local database.

### 🔴 Phase C: The Workforce Pilot (Days 8-14)

- **Goal:** Run an autonomous agent on the node.
- **Tasks:**
    - Configure a Docker container with **CrewAI**.
    - Script the "Auto-Pull" logic once the JWT is verified.
- **Success:** A newly booted node starts executing a TPP logistics task automatically.

---

## 4. Testing & Validation Checklist

- [ ]  **Cold Boot Test:** Does it reach the QR screen in < 60 seconds?
- [ ]  **Zero-Touch Test:** Can a "non-tech" friend claim the node?
- [ ]  **Resilience Test:** Does the agent resume work after a power cut?
- [ ]  **Security Test:** Is the JWT encrypted and non-reusable?

---

## 5. Stakeholder Pitch Points (For SmartHub.ai)

- **Scale:** How AetherEdge solves the "Last Mile" setup in unorganized sectors.
- **Integration:** How AetherNodes can be "SmartHub-Ready" out of the box.
- **Cost:** Reducing setup costs from $500/node (pro-install) to $0/node (user-install).

## Working on the Orchestrator now

1. Ensuring that DB is updated for orchestrator to remember the tasks
"Let’s start Epic 3: The Workload Runner.
First, update our database.py to include a Tasks table.
Fields needed: id (UUID), node_id (foreign key), script_name (e.g., maintenance_agent.py), status (PENDING, RUNNING, COMPLETED, FAILED), result (JSON/Text), and created_at/updated_at.
Also, add a helper function get_pending_task(node_id) to find the next task for a specific node."
Step 2 :  For registry of agents
"1. Create a directory on the Orchestrator called registry/.
2. Inside registry/, create a sample maintenance_agent.py that checks disk/CPU usage and returns a JSON string.
3. Implement a new FastAPI endpoint: GET /api/v1/registry/download/{script_name}. This endpoint must require mTLS authentication—only a verified node can download scripts."

Step 3 - now lets ensure the heartbeat returns more meaning ful data, tasks instructions and not just SUCCESS:
"Modify the POST /api/v1/nodes/heartbeat endpoint.
When a node checks in:

Look up the Tasks table for any PENDING task for this node_id.

If a task exists, return a JSON response containing:

task_id: The UUID.

action: 'EXECUTE'.

script_url: The URL to download the script from our new registry endpoint.

Update the task status to RUNNING in the database."

Step 4: Create the "Result Collection" Endpoint
The Orchestrator needs a "mailbox" where nodes can drop off the results of their work.

Tell Claude:

"Add a new endpoint: POST /api/v1/tasks/{task_id}/result.
This endpoint should:

Receive the output (stdout) and exit code from the node.

Update the task in the database with the result and set the status to COMPLETED.

Log a summary of the task completion for the operator to see."

Step 5-6 : To test this now -
"Create a script scripts/create_task.py that allows me to manually insert a task into the SQLite tasks table.

It should take arguments for node_id and script_name.

It should generate a unique task_id (UUID).

Set the initial status to PENDING.

Bonus: Add a small validation check to make sure the node_id actually exists in the nodes table before creating the task."