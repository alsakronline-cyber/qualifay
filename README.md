# 🤖 AI WhatsApp CRM

**Self-hosted AI-powered CRM with WhatsApp integration**
Built for Ubuntu 22.04 LTS · ARM64 (aarch64) · 4 vCPU · 24 GB RAM

---

## Architecture

```
WhatsApp User
     ↓
Evolution API (WhatsApp bridge, port 8080)
     ↓ webhook
FastAPI Backend (port 5000)
     ↓ queue
Celery Workers
  ├── Intent Classification   → Llama 3.3 70B :free (fast)
  ├── AI Auto-Reply          → DeepSeek R1 :free (reasoning)
  ├── Lead Scoring           → Llama 3.3 70B :free
  └── Contact Summarization  → DeepSeek R1 :free
     ↓
PostgreSQL + Redis
     ↓
React CRM Dashboard (Nginx)
```

### Stack
| Layer | Technology | Why |
|---|---|---|
| WhatsApp | **Evolution API v2** | Best open-source WA bridge, multi-instance, active 2026 |
| Backend | **FastAPI + Python 3.11** | Best for async LLM/API integrations |
| AI/LLM | **OpenRouter Free** | DeepSeek R1 + Llama 3.3 70B — both free |
| Queue | **Celery + Redis** | Non-blocking AI calls |
| Database | **PostgreSQL 15** | Persistent CRM data |
| Frontend | **React + Vite + Tailwind** | Fast CRM UI |
| Proxy | **Nginx** | Single entry point |

### Memory Budget (24 GB)
| Service | Limit |
|---|---|
| PostgreSQL | 2 GB |
| Redis | 512 MB |
| Evolution API | 1 GB |
| Backend (FastAPI) | 1 GB |
| Celery Workers | 1.5 GB |
| Celery Beat | 256 MB |
| Frontend + Nginx | 384 MB |
| **Headroom** | **~17 GB free** ✅ |

---

## Prerequisites

```bash
# Install Docker (ARM64 compatible)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

---

## Setup

### 1. Configure environment

```bash
cp .env.example .env
nano .env
```

Fill in **all** required values:

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Strong DB password |
| `REDIS_PASSWORD` | Strong Redis password |
| `EVOLUTION_API_KEY` | Any strong random string (32+ chars) |
| `OPENROUTER_API_KEY` | Free key from [openrouter.ai](https://openrouter.ai) |
| `SECRET_KEY` | Random 64-char string for JWT |
| `EVOLUTION_SERVER_URL` | Your server's public IP/domain, port 8080 |
| `DEFAULT_ADMIN_EMAIL` | Your admin login email |
| `DEFAULT_ADMIN_PASSWORD` | Your admin password |

Generate secure values:
```bash
# Generate SECRET_KEY
openssl rand -hex 32

# Generate EVOLUTION_API_KEY
openssl rand -hex 16
```

### 2. Deploy

```bash
chmod +x scripts/deploy.sh manage.sh
./scripts/deploy.sh
```

The deploy script:
1. Validates your `.env`
2. Pulls ARM64-compatible Docker images
3. Builds backend and frontend
4. Starts all services
5. Creates the admin user
6. Runs health checks
7. Prints the access URLs

### 3. Connect WhatsApp

1. Open **Evolution Manager**: `http://YOUR_SERVER_IP:8080/manager`  
   *(or use the CRM at `http://YOUR_SERVER_IP` → WhatsApp tab)*
2. Click **Create Instance** → give it a name (e.g. `sales`)
3. Scan the QR code with WhatsApp → **Settings → Linked Devices → Link a Device**
4. Once connected, incoming messages will appear in the CRM inbox

---

## CRM Features

### 📥 WhatsApp Inbox
- Real-time incoming message display (auto-refreshes every 3s)
- Send messages directly from the CRM
- Toggle AI auto-reply per conversation
- Click **Suggest** to get 3 AI-generated quick replies

### 🤖 AI Auto-Reply Pipeline
When a message arrives:
1. **Llama 3.3 70B** classifies intent in ~1s (greeting, question, complaint, purchase intent…)
2. If `requires_human: false` → Celery queues an AI reply after a 2-second typing delay
3. **DeepSeek R1** generates a contextual, language-aware reply
4. Reply is sent via Evolution API and saved to DB
5. If AI can't help → escalates silently (no reply, conversation stays open for agent)

### 👥 Contacts
- Auto-created from WhatsApp JID on first message
- AI-generated profile summary (click Refresh)
- Lead scoring 0–100 (AI-assessed purchase intent)
- Tags, custom fields, notes
- Sentiment tracking

### 📊 Pipeline / Kanban
- Drag-style deal stage management: Lead → Contacted → Qualified → Proposal → Negotiation → Won/Lost
- Deal value tracking
- Link deals to contacts

### 📱 Multi-Instance WhatsApp
- Connect multiple WhatsApp numbers (one QR each)
- Manage all from one CRM
- Each instance has independent conversations

---

## OpenRouter Free Models

No cost. No credit card. Just sign up at [openrouter.ai](https://openrouter.ai).

| Model | Used For | Context |
|---|---|---|
| `deepseek/deepseek-r1:free` | Auto-replies, contact summaries | 1M tokens |
| `meta-llama/llama-3.3-70b-instruct:free` | Intent classification, lead scoring, suggestions | 128K |
| `openrouter/auto:free` | Auto-fallback when others are rate-limited | Varies |

Rate limits on free tier: ~200 req/day per model. For production scale, add $5 OpenRouter credits — still extremely cheap vs any SaaS.

---

## Management Commands

```bash
./manage.sh status        # Service health + resource usage
./manage.sh logs          # All logs
./manage.sh logs-ai       # AI worker logs only
./manage.sh logs-wa       # WhatsApp (Evolution) logs
./manage.sh wa-status     # Check all WA instance connection states
./manage.sh ai-stats      # AI message stats from DB
./manage.sh backup        # Backup DB → backups/wacrm_TIMESTAMP.sql.gz
./manage.sh restore FILE  # Restore DB from backup
./manage.sh shell-db      # psql shell
./manage.sh shell-redis   # redis-cli
./manage.sh update        # Pull latest + rebuild
./manage.sh reset-ai      # Restart AI workers (clears stuck tasks)
./manage.sh resources     # Per-container memory/CPU
```

---

## API Documentation

FastAPI auto-generates interactive docs:
- **Swagger UI**: `http://YOUR_SERVER_IP/api/docs`
- **ReDoc**: `http://YOUR_SERVER_IP/api/redoc`

### Key Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/dashboard/stats` | CRM metrics |
| GET | `/api/v1/contacts/` | List contacts |
| GET | `/api/v1/conversations/` | List conversations |
| GET | `/api/v1/conversations/{id}/messages` | Messages |
| POST | `/api/v1/messages/send` | Send message |
| GET | `/api/v1/instances/` | WA instances |
| POST | `/api/v1/instances/` | Create instance |
| GET | `/api/v1/instances/{name}/qr` | Get QR code |
| POST | `/api/v1/ai/suggest-replies` | AI reply suggestions |
| POST | `/api/v1/webhook/evolution` | Evolution webhook (auto-configured) |

---

## Troubleshooting

**Evolution API not connecting?**
```bash
./manage.sh logs-wa
# Check EVOLUTION_SERVER_URL — must be your public IP/domain, not localhost
# The WA client needs to reach it from the internet for QR
```

**AI not replying?**
```bash
./manage.sh logs-ai
# Check OPENROUTER_API_KEY is valid
# Check rate limits: 200 req/day on free tier
# Toggle AI on/off per conversation in inbox
```

**Messages not appearing?**
```bash
# Verify webhook is set in Evolution
curl -H "apikey: YOUR_KEY" http://localhost:8080/webhook/YOUR_INSTANCE_NAME
# Should show BACKEND_URL/api/v1/webhook/evolution
```

**Out of memory?**
```bash
./manage.sh resources
# All 8 services should use ~7 GB total
# 24 GB RAM gives ~17 GB headroom
```

**Database issues?**
```bash
./manage.sh shell-db
# \dt — list tables
# SELECT COUNT(*) FROM contacts;
```

---

## File Structure

```
wacrm/
├── docker-compose.yml        # Full stack orchestration
├── .env.example              # Environment template
├── manage.sh                 # Management commands
├── scripts/
│   ├── deploy.sh             # One-click deployment
│   └── init_db.sql           # DB initialization
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI app entry
│       ├── core/
│       │   ├── config.py     # Settings (pydantic)
│       │   └── database.py   # Async SQLAlchemy
│       ├── models/
│       │   └── models.py     # All DB models
│       ├── api/              # REST endpoints
│       │   ├── webhook.py    # Evolution webhook receiver
│       │   ├── contacts.py
│       │   ├── conversations.py
│       │   ├── messages.py
│       │   ├── instances.py
│       │   ├── pipeline.py
│       │   ├── ai.py
│       │   ├── auth.py
│       │   └── dashboard.py
│       ├── services/
│       │   ├── ai_service.py        # OpenRouter LLM client
│       │   └── evolution_service.py # Evolution API client
│       └── workers/
│           ├── celery_app.py  # Celery configuration
│           └── tasks.py       # AI processing tasks
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── main.jsx          # React entry + routing
│       ├── store/authStore.js
│       ├── hooks/api.js      # All API calls
│       ├── components/layout/Layout.jsx
│       └── pages/
│           ├── Login.jsx
│           ├── Dashboard.jsx
│           ├── Inbox.jsx     # WhatsApp chat UI
│           ├── Contacts.jsx
│           ├── ContactDetail.jsx
│           ├── Pipeline.jsx
│           └── Instances.jsx
└── nginx/
    └── nginx.conf
```
