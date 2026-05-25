# Production Deployment Runbook

This document details the standard procedures for containerized deployment, environment synchronization, and post-deployment validation gates.

---

## 1. Deployment Pre-Requisites
- **Docker Engine:** Version $\ge 24.0.0$ installed and active on the host machine.
- **Python Runtime:** Version $\ge 3.12$ (slim or full) inside the environment.
- **TWS / IB Gateway:** Installed, configured, and authenticated with API active on port `7496` (live) or `7497` (paper).
- **SSL / Port Binding:** Host port `8000` open for quantitative dashboard access.

---

## 2. Git & Repository Synchronization
Before deploying, synchronize the latest verified release branch from GitHub:
1. Fetch latest changes from the origin remote:
   ```bash
   git fetch origin
   ```
2. Verify that the local branch is clean and aligned with remote master:
   ```bash
   git status
   ```
3. Pull the verified changes:
   ```bash
   git pull origin master
   ```

---

## 3. Containerized Orchestration Deployment (Recommended)
Our micro-container layout isolates execution environments and preserves local state caches via volume maps.

### Step A: Hydrate Environment Configuration
Verify that the production `.env` is fully populated with live API credentials and secure ports:
```env
IB_HOST=127.0.0.1
IB_PORT=7496
IB_CLIENTID=1
IB_ACCOUNT=DU1234567
PAPER_TRADING=False
ENABLE_LIVE_TRADING=True
```

### Step B: Build and Orchestrate Containers
Execute container builds and launch services in detached daemon mode:
```bash
# Build production layers
docker-compose build --no-cache

# Boot trading daemon and dashboard services
docker-compose up -d
```

### Step C: Monitor Logs and Container Status
Verify that both containers are running and stable:
```bash
# Check container status
docker-compose ps

# Monitor engine startup logs
docker logs -f quant-trading-engine
```

---

## 4. Post-Deployment Verification Gate
1. **Verification Command:** Run the pre-flight checklist solver in the container:
   ```bash
   docker exec -it quant-trading-engine python -c "from core.approval_gate import LiveApprovalGate; print(LiveApprovalGate().evaluate_readiness())"
   ```
2. **Dashboard Verification:** Point your browser to `http://localhost:8000` and confirm that account net liquidation, cash, positions count, and health status connect and update in real-time.

---

## 5. Rollback Procedures
If the post-deployment validation gate fails or the engine experiences high execution latencies ($> 250\text{ms}$):
1. **Instantly Halt Active Execution:**
   ```bash
   docker-compose down
   ```
2. **Revert Git Repository:** Revert the master branch to the previously known-good commit:
   ```bash
   git reset --hard <previously_verified_commit_hash>
   ```
3. **Re-Deploy Baseline Container:**
   ```bash
   docker-compose up -d --build
   ```
4. **Reconcile Positions:** Re-run the reconciliation process to ensure zero unhedged positions exist.
