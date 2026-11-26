# WorkMate — single-VPS deployment (English-only build)

One Linux host runs everything: PostgreSQL 16, a **private** Ollama (local models), the API, the web app and Caddy (HTTPS).
Only ports **80/443** are published. Postgres, Ollama and the API have no host ports and sit on an internal Docker network with
no route to the internet.

> **Status — read this first.** The compose file, init script and env template are validated statically
> (`python scripts/check_vps_topology.py`, `backend/tests/test_vps_topology.py`, `docker compose config`). The same application code
> is tested against a restricted non-owner database login (the one this stack uses). **This package has not been run on a real
> server by this repository**; nothing has been provisioned, paid for or deployed. Use the acceptance checklist below on a staging
> host before real users. If you prefer a hosted database, use the managed-database runbook in `deploy/staging/README.md` instead.

## 1. Sizing (measured, not guessed)
Measured on an 8 GB laptop-class CPU (no GPU), models loaded in Ollama:

| Component | Measured |
|---|---|
| `qwen2.5:3b` (chat) | **2.2 GB** resident, cold load ≈ 18 s, warm 4-token reply ≈ 0.5 s |
| `nomic-embed-text` | **0.39 GB** resident |
| Both together | ≈ 2.6 GB. On that 8 GB machine, with Docker/Postgres/browser also running, free memory fell to ~0 and replies became slow |

Recommendation: **16 GB RAM, 4–6 vCPU, 80 GB SSD** for the full stack with AI on. 8 GB is enough only with `LOCAL_AI_ENABLED=false`:
SOP lookup, guided workflows, safety triage, discrepancy reports, approvals and all admin/manager screens do **not** call the model
(measured latency: tens of milliseconds); only free-form follow-up generation uses it. Re-measure on your actual host
(`docker stats`, `ollama ps`) before committing to a plan. CPU token throughput on a real VPS was **not** measured.

## 2. Prepare the host (Ubuntu LTS assumed)
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 ufw git
sudo ufw default deny incoming && sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw enable
sudo adduser --disabled-password deploy && sudo usermod -aG docker deploy      # run the stack as a non-root user
```
Point an **A record** for your domain at the server first (Caddy obtains the certificate on first start).
Docker publishes ports by editing iptables and can bypass `ufw`; this stack publishes only 80/443 by design (verify in §6).

## 3. Configure
```bash
git clone <your repo> && cd WM/deploy/vps
cp .env.example .env && chmod 600 .env
openssl rand -base64 36        # once per secret: OWNER_DB_PASSWORD, APP_DB_PASSWORD, JWT_SECRET, INTERNAL_WEBHOOK_SECRET
```
Fill every value in `.env` (never commit it). Pin `OLLAMA_IMAGE` to a tag you have tested. Create an
[age](https://age-encryption.org) key pair on **another machine** and put only the *public* recipient in `BACKUP_AGE_RECIPIENT`.

## 4. First start
```bash
docker compose build
docker compose up -d postgres                     # creates the owner login and the non-owner app login on first start
docker compose up -d                              # migrations -> grants -> API preflight -> web -> HTTPS
docker compose --profile models run --rm models   # one-time model download (the only step with internet egress)
```
The API refuses to start if its database login can bypass row-level security or owns tables (`verify_runtime_database.py`).

First administrator and organization (values come from your shell; the password is never printed):
```bash
BOOTSTRAP_ADMIN_EMAIL=you@company.com BOOTSTRAP_ADMIN_PASSWORD='<16+ characters>' \
BOOTSTRAP_DEPARTMENT_ID=operations BOOTSTRAP_DEPARTMENT_NAME='Operations' \
BOOTSTRAP_ORGANIZATION_NAME='Your Company' BOOTSTRAP_WAREHOUSE_NAME='Main DC' \
docker compose --profile bootstrap run --rm bootstrap
```
Sign in at `https://<domain>/login`, open **Employees**, and invite your managers and staff (the invite link is shown once;
WorkMate does not send email). Upload SOPs in **Knowledge Studio**; a manager must approve each upload on **SOP approvals**
before it is live.

## 5. Day-2 operations
| Task | Command |
|---|---|
| Status / health | `docker compose ps` · `docker compose exec backend curl -fsS localhost:8000/ready` · AI: `docker compose exec backend curl -fsS localhost:8000/health/ai` |
| Logs | `docker compose logs -f --tail 200 backend` (never paste `.env`) |
| Restart | `docker compose restart backend frontend` (state is in Postgres) |
| Memory check | `docker stats --no-stream` and `docker compose exec ollama ollama ps` |
| Encrypted backup | `docker compose --profile backup run --rm backup` → `deploy/vps/backups/wm-*.dump.age`; **copy off the host** on a schedule (cron + rsync/rclone to storage you control) |
| Restore drill (monthly) | on a separate machine: `age --decrypt -i key.txt -o r.dump wm-….dump.age` then `pg_restore --no-owner --no-acl --exit-on-error -d "$SCRATCH_DB_URL" r.dump`; check row counts and sign in |
| Upgrade | back up → `git pull` → `docker compose build` → `docker compose up -d` (migrations are forward-only and re-runnable) |
| Rollback | migrations are not reversible: **restore the pre-upgrade backup** into a fresh volume and check out the previous tag. Always back up first. |

## 6. Acceptance checklist (run on the real host before users)
1. From outside, a port scan of the server shows only 80/443 (and 22 if open): **no 5432, 11434, 8000, 3000**.
2. `https://<domain>` serves a valid certificate; HTTP redirects to HTTPS; responses carry HSTS.
3. Sign in as the bootstrap admin; **Employees → Add employee**; accept the invite in a private window and sign in as that user.
4. Upload a small SOP file as admin; confirm an employee **cannot** find it; approve it as a manager; confirm the employee now can.
5. As an employee ask: a covered question (gets the SOP); an uncovered one (gets "I don't have an approved procedure… won't guess" and a case under *Unanswered questions*); and "hydraulic leak on the forklift, how do I fix it myself?" (stop-work wording and an urgent case, no repair steps).
6. `docker compose exec postgres psql -U <app login> -d workmate -c "select rolsuper, rolbypassrls from pg_roles where rolname=current_user"` shows `f | f`.
7. Run a backup, copy it off-host, and complete a restore drill into a scratch database.
8. `docker compose exec backend env | grep LOCAL_AI_BASE_URL` shows the internal `ollama` address — no external AI provider is configured.
9. Reboot the server; everything returns without manual steps (`restart: unless-stopped`).

## 7. Known limits
- Not load-tested; single host, no failover, no point-in-time recovery (logical dumps only).
- TLS terminates at Caddy; container-to-container traffic is plain HTTP/PostgreSQL on the private network (the backup job uses `sslmode=disable` for that reason).
- WorkMate sends no email; invite and recovery links are handed over by an administrator.
- Row-level security is enforced in the database for the tables whose migrations define policies (reference documents, source
  objects, drafts, handovers, work items, exceptions, integration records, pilot feedback). The remaining tenant isolation
  (knowledge items, analytics, escalations, gaps, employees, sessions) is application-level and covered by cross-tenant tests, not DB policies.
- Free-form model answers are unmeasured for quality; the acceptance scenarios exercise the deterministic paths.
