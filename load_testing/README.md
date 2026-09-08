# 🧪 EduMi Load Testing Suite

A self-contained, removable load-testing framework designed specifically for testing deployed EduMi production environments (`https://eclass.dei.ac.in`) under realistic concurrent usage.

Everything is contained inside the `load_testing/` directory and does not alter production business logic.

---

## 📋 Table of Contents
1. [Architecture & Features](#architecture--features)
2. [Step 1: Provision 1000 Users & 10 Classrooms](#step-1-provision-1000-users--10-classrooms)
3. [Step 2: Run the Production Load Test](#step-2-run-the-production-load-test)
4. [Step 3: Analyze the Performance Reports](#step-3-analyze-the-performance-reports)
5. [Step 4: Cleanup and Removal](#step-4-cleanup-and-removal)

---

## 🏗️ Architecture & Features

- **Real Deployed Edumi Application**: Targets `https://eclass.dei.ac.in` over **HTTPS only**. Rejects `localhost` and `127.0.0.1`.
- **1000 Real Accounts**: Generates users `test1` through `test1000` with password `test`.
  - **10 Admins** (`test1` – `test10`): Full admin/superuser permissions.
  - **40 Teachers** (`test11` – `test50`): Course & classroom instructors.
  - **950 Students** (`test51` – `test1000`): Enrolled students with verified emails.
- **10 Classrooms (10 Students Each)**:
  - Codes: `TESTCLASS01` through `TESTCLASS10`.
  - Assigned to teachers `test11` through `test20`.
  - 10 approved student memberships per classroom (100 students total: `test51` through `test150`).
  - Active live meetings (`TESTMEET01` through `TESTMEET10`) for testing real-time room traffic.
- **Realistic User Personas**:
  - **Casual Student Browsing**: Student dashboard, unread notifications, attendance history, video studio, user directory, profile, and notification WebSocket listener.
  - **Student Joining Meeting**: Classroom access, meeting preparation, room entry, LiveKit token acquisition, participant tracking, and persistent WebSocket room signaling (`/ws/meeting/<code_name>/`).
  - **Teacher Activity**: Teacher dashboard, classroom oversight, attendance records, meeting scheduling, and LiveKit token generation.
  - **Admin Read-Only Activity**: Admin panel, user audits, student/teacher rosters, live meeting inspection, architecture diagram, and `/health/` probes.
- **Wave Progression**:
  $$10 \rightarrow 25 \rightarrow 50 \rightarrow 100 \rightarrow 200 \rightarrow 500 \rightarrow 1000\text{ concurrent users}$$
- **Automated Saturation Analysis**: Detects the exact knee point where response latency increases, P95 degrades, or HTTP 4xx/5xx errors emerge.

---

## 🚀 Step 1: Provision 1000 Users & 10 Classrooms

Run the provisioner directly in your server environment:

```bash
python load_testing/users.py
```

### What this does:
1. Computes the PBKDF2 hash for password `test` in a single pass (takes ~1-2 seconds total).
2. Performs bulk operations (`bulk_create` / `bulk_update`) so it is **100% safe to run multiple times** without duplicate errors.
3. Automatically sets `is_verified = True` on all user profiles so they can log in immediately without email verification prompts.
4. Creates 10 classrooms (`TESTCLASS01`–`TESTCLASS10`) and enrolls 10 approved students into each classroom.
5. Sets up active live meetings (`TESTMEET01`–`TESTMEET10`) for each classroom.
6. Writes fixture metadata to `load_testing/credentials.json`.

### Verification Check
To check that all 1000 users and 10 classrooms are correctly provisioned:

```bash
python load_testing/users.py --verify
```

---

## ⚡ Step 2: Run the Production Load Test

Run the test script:

```bash
python load_testing/test.py
```

By default, this tests **`https://eclass.dei.ac.in`** through all 7 waves:
$$10 \rightarrow 25 \rightarrow 50 \rightarrow 100 \rightarrow 200 \rightarrow 500 \rightarrow 1000$$

### Command Line Options

| Flag | Default | Description | Example |
|---|---|---|---|
| `--url` | `https://eclass.dei.ac.in` | Target base URL (**HTTPS only**) | `--url https://eclass.dei.ac.in` |
| `--waves` | `10,25,50,100,200,500,1000` | Comma-separated user wave tiers | `--waves 25,50,100` |
| `--duration` | `25` | Duration in seconds per wave | `--duration 30` |
| `--insecure` | `False` | Disable SSL certificate check | `--insecure` |

### Quick Smoke Test Examples
Run a quick 10-user check for 10 seconds:
```bash
python load_testing/test.py --waves 10 --duration 10
```

Run waves 10, 50, and 100:
```bash
python load_testing/test.py --waves 10,50,100 --duration 20
```

---

## 📊 Step 3: Analyze the Performance Reports

During the test, live metrics are displayed in the terminal for each wave:
- Concurrency (Users)
- Throughput (Requests/sec)
- Latency statistics (Average, Median P50, P95, P99, Min, Max)
- Status breakdown (2xx/3xx successes, 4xx client errors, 5xx server errors, network drops)
- WebSocket stats (handshake attempts, successes, messages received/sent)
- Performance degradation factor vs baseline (Wave 1)

### Saved Reports
At the end of the test, two reports are automatically saved inside `load_testing/reports/`:
1. **Markdown Report** (`load_testing/reports/load_test_report_<timestamp>.md`):
   - Executive summary with the system saturation knee-point.
   - Formatted performance table across all tiers.
   - Persona breakdown.
   - Production tuning recommendations (Daphne concurrency, Redis connection pool, PostgreSQL pooling, Nginx limits).
2. **JSON Report** (`load_testing/reports/load_test_report_<timestamp>.json`):
   - Raw machine-readable metrics for CI/CD and historical benchmarking.

---

## 🧹 Step 4: Cleanup and Removal

### 1. Remove Test Users, Classrooms, and Fixtures from Database
Run the provisioner with `--cleanup`:

```bash
python load_testing/users.py --cleanup
```

This will cleanly delete:
- Users `test1` through `test1000` and their profiles
- Classrooms `TESTCLASS01` through `TESTCLASS10` and student memberships
- Meetings `TESTMEET01` through `TESTMEET10`
- `load_testing/credentials.json`

### 2. Remove the Load Testing Setup
To completely remove the load testing code from the repository:

```bash
rm -rf load_testing/
```

No core application files or models are touched.
