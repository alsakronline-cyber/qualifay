# Deploying Qualifay

Single source of truth: **GitHub `main`** (`github.com/MohamedMustafa31/qaulifay`).
Local dev machine, the server, and GitHub all track the same `main`.

## Prerequisites (one-time)

Both the local machine and the server need a GitHub token in their remote URL so
they can push/pull the private repo:

```bash
git remote set-url origin https://<PAT>@github.com/MohamedMustafa31/qaulifay.git
```

Use a Personal Access Token with `repo` scope. **Never commit the token** — it lives
only in `.git/config`. Rotate it if it is ever exposed.

## Standard deploy flow

```bash
# 1. On the local dev machine — make changes, then:
git add -A
git commit -m "…"
git push

# 2. On the server — pull and rebuild only the service(s) you changed:
ssh -i ssh-key-2026-03-05.key -p 2222 ubuntu@80.225.65.148
cd /home/ubuntu/qaulifay
git pull
docker compose up -d --build frontend    # or: backend, celery_worker, …
```

Frontend-only content changes still require a rebuild (Next.js is built into the
image). Backend Python changes also need a rebuild since code is `COPY`d in.

## Database migrations

The schema is owned by Alembic (`backend/alembic/versions/`). The app no longer creates
tables or runs `ALTER TABLE` when it boots — that queued behind live workers' locks and
crash-looped deploys. Instead the backend container runs `alembic upgrade head` once,
before uvicorn starts (a no-op when already at head). Celery containers never migrate.

```bash
# Changing a model: generate a revision, review it, commit it with the model change.
cd backend
alembic revision --autogenerate -m "add leads.foo"
alembic upgrade head        # apply locally
alembic check               # models and migrations agree (CI runs this too)
```

First deploy of this change on an existing server: nothing to do by hand. The baseline
revision (`0002_baseline_schema`) detects the tables the old boot code created, only adds
what is missing, and stamps the database. Check with
`docker compose exec backend alembic current` (should print `0002_baseline_schema (head)`).
Migrations run with `lock_timeout = 10s`: if one times out the backend exits, the
redeploy health gate rolls back, and you simply rerun the deploy.

## Tests

```bash
cd backend
pytest -q                                   # unit tests, no services needed
# API + end-to-end tests against a throwaway Postgres + Redis (database name must contain "test"):
RUN_INTEGRATION=1 DATABASE_URL=postgresql+asyncpg://user:pw@127.0.0.1:5432/qualifay_test \
  REDIS_URL=redis://127.0.0.1:6379/0 pytest tests/integration -q
```

## Never commit these

Enforced by `.gitignore` — keep it that way:

- `.env` (secrets) — the server keeps its own `.env` on disk, untracked.
- `*.key`, `*.pem`, `ssh-key-*` (private keys).
- `node_modules/`, `.next/`, `frontend/.next/` (build artifacts — a 133 MB blob in
  here is what originally blocked pushing to GitHub).

## Environment / secrets

Each host has its own untracked `.env` on disk. `.env.example` (committed) lists the
required keys with placeholder values. When adding a new setting, update
`.env.example` and set the real value in each host's `.env` by hand.

## Rollback

The pre-reconcile history is preserved:

- Server tag `pre-reconcile-backup` — the old server history.
- To roll a service back, `git checkout <good-commit>` on the server and rebuild.

## Server quick reference

```
Host:  ssh -i ssh-key-2026-03-05.key -p 2222 ubuntu@80.225.65.148
Repo:  /home/ubuntu/qaulifay
App:   http://80.225.65.148   (nginx → frontend :3000, backend /api → :5000)
Logs:  docker compose logs -f backend
```
