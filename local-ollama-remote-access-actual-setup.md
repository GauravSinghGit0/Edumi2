# Enterprise Architecture Guide: Remote Access to Local Ollama Models

This guide documents the production-grade setup for accessing locally hosted Ollama AI models (running on a local GPU/CPU machine) from a remote web application (e.g., EduMi RAG Application on an AWS/DigitalOcean Ubuntu server).

---

## 🏗️ System Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                 REMOTE APPLICATION SERVER                   │
│   (EduMi Django Web App / RAG Workspace Service Layer)      │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS (Bearer Token Auth)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 CLOUDFLARE EDGE NETWORK                     │
│    (Named Tunnel / Anycast DDoS Protection / SSL Offload)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Encrypted Inbound Tunnel
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   LOCAL DESKTOP / GPU PC                    │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  FastAPI Production Gateway (Port 8765)             │   │
│   │  - Shared HTTP Async Pool (Lifespan Context)        │   │
│   │  - Constant-Time Bearer Auth (Anti-Timing Attacks)   │   │
│   │  - Pre-Stream Status & Error Interception           │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              │ Loopback HTTP (127.0.0.1)    │
│                              ▼                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Ollama Inference Service (Port 11434)              │   │
│   │  - phi:latest (LLM Text Generation & Summaries)     │   │
│   │  - nomic-embed-text:latest (Vector Embeddings)      │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Local PC Ollama Environment Setup

Verify Ollama is installed and running on your Local Desktop PC.

### Check Service Status
```bash
ollama --version
ollama list
```

### Pull Required Production Models
```bash
# Vector Embedding Model (for RAG Chunk Similarity Search)
ollama pull nomic-embed-text:latest

# Core Reasoning & Text Generation LLM
ollama pull phi:latest
```

---

## 2. FastAPI Gateway Setup (High-Performance Proxy)

To protect your local Ollama port (`11434`), enforce Bearer API authentication, handle connection pooling, and stream NDJSON/SSE responses safely, we deploy a lightweight FastAPI Gateway on port `8765`.

### Create Directory & Virtual Environment
```bash
mkdir -p ~/ollama-gateway
cd ~/ollama-gateway

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install fastapi "uvicorn[standard]" httpx
```

### Gateway Source Code (`app.py`)

Create `~/ollama-gateway/app.py`:

```python
"""
Production FastAPI Proxy Gateway for Local Ollama Service.
Features:
 - Global Connection Pooling via Lifespan Manager
 - Constant-Time Token Verification (Anti-Timing Attack)
 - Pre-Stream Status & Error Header Interception
 - Full Query-String & Dynamic Media-Type Forwarding
 - Multi-Route API Mapping (/api/* and /v1/*)
"""

import os
import secrets
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware

# =========================================================
# CONFIGURATION
# =========================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
API_KEY = os.getenv("OLLAMA_API_KEY")

if not API_KEY:
    raise RuntimeError("OLLAMA_API_KEY environment variable is required")

# Shared connection pool for high scalability & zero socket exhaustion
http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    # Timeout configuration: Infinite read timeout for long streaming responses
    timeout = httpx.Timeout(connect=10.0, read=None, write=120.0, pool=30.0)
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
    http_client = httpx.AsyncClient(timeout=timeout, limits=limits)
    yield
    await http_client.aclose()


app = FastAPI(
    title="Private Ollama Gateway",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan
)

# Enable CORS for direct frontend/dashboard integrations if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# SECURITY AUTHENTICATION
# =========================================================

def authenticate(request: Request):
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {API_KEY}"
    if not secrets.compare_digest(auth, expected):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized access to Ollama Gateway"
        )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
async def health():
    try:
        r = await http_client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if r.status_code == 200:
            return {
                "status": "ok",
                "ollama": "online",
                "models": [m.get("name") for m in r.json().get("models", [])]
            }
        return {"status": "error", "ollama": "offline"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Ollama service unreachable on local machine"
        )


# =========================================================
# CORE PROXY HANDLER
# =========================================================

async def handle_proxy(path_prefix: str, path: str, request: Request):
    authenticate(request)

    # Build target URL with full query string preservation
    target_url = f"{OLLAMA_URL}/{path_prefix}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()

    # Selectively forward essential headers
    forward_headers = {}
    content_type = request.headers.get("content-type")
    if content_type:
        forward_headers["content-type"] = content_type

    try:
        req = http_client.build_request(
            method=request.method,
            url=target_url,
            content=body,
            headers=forward_headers
        )
        res = await http_client.send(req, stream=True)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama local connection failure: {str(exc)}"
        )

    # Intercept HTTP error codes BEFORE starting stream (prevents 500/502 crashes)
    if res.status_code >= 400:
        error_content = await res.aread()
        await res.aclose()
        return Response(
            content=error_content,
            status_code=res.status_code,
            media_type=res.headers.get("content-type", "application/json")
        )

    # Stream NDJSON / SSE chunks smoothly
    async def stream_response():
        try:
            async for chunk in res.aiter_bytes():
                yield chunk
        finally:
            await res.aclose()

    media_type = res.headers.get("content-type", "application/x-ndjson")
    return StreamingResponse(
        stream_response(),
        status_code=res.status_code,
        media_type=media_type
    )


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_api(path: str, request: Request):
    return await handle_proxy("api", path, request)


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_v1(path: str, request: Request):
    return await handle_proxy("v1", path, request)


@app.get("/")
async def root():
    return {
        "service": "Private Ollama Gateway",
        "status": "online"
    }
```

---

## 3. Generate Gateway API Key

Generate a cryptographically secure 256-bit token on your local PC:

```bash
openssl rand -hex 32
```
*Save this token securely. It will be passed as `OLLAMA_API_KEY` on the local machine and `AI_LLM_BEARER_TOKEN` on the remote server.*

---

## 4. Systemd Service Deployment (Production Auto-Start)

To guarantee the FastAPI Gateway automatically starts on system boot and restarts if interrupted, configure a Linux `systemd` unit file.

### Create Unit File
```bash
sudo nano /etc/systemd/system/ollama-gateway.service
```

### Paste Configuration
*(Replace `YOUR_LINUX_USERNAME` and `YOUR_GENERATED_API_KEY_HERE`)*:

```ini
[Unit]
Description=EduMi Private Ollama Gateway Service
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/home/YOUR_LINUX_USERNAME/ollama-gateway
Environment="OLLAMA_URL=http://127.0.0.1:11434"
Environment="OLLAMA_API_KEY=YOUR_GENERATED_API_KEY_HERE"
ExecStart=/home/YOUR_LINUX_USERNAME/ollama-gateway/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable & Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ollama-gateway

# Check runtime logs and status
sudo systemctl status ollama-gateway
```

---

## 5. Cloudflare Tunnel Deployment

### Option A: Quick Tunnel (Development Testing)
For temporary development testing:
```bash
cloudflared tunnel --url http://127.0.0.1:8765
```
*Note: Quick Tunnel URLs (e.g. `https://xxx.trycloudflare.com`) expire whenever the process or machine restarts.*

### Option B: Named Cloudflare Tunnel (Production Recommendation)
For a persistent, non-expiring domain (e.g., `ollama.yourdomain.com`):

```bash
# 1. Login to Cloudflare Account
cloudflared tunnel login

# 2. Create Named Tunnel
cloudflared tunnel create local-ollama-gateway

# 3. Route Subdomain to Tunnel
cloudflared tunnel route dns local-ollama-gateway ollama.yourdomain.com

# 4. Configure Tunnel YAML File (~/.cloudflared/config.yml)
```

Create `~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /home/YOUR_USERNAME/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: ollama.yourdomain.com
    service: http://127.0.0.1:8765
  - service: http_status:404
```

Start named tunnel service:
```bash
cloudflared service install
sudo systemctl start cloudflared
```

---

## 6. Remote Server Integration (`EduMi2/.env`)

On your remote Ubuntu production server (where EduMi Django App is deployed), configure `.env`:

```env
# AI Model & RAG Workspace Configuration
AI_LLM_URL=https://ollama.yourdomain.com/api/generate
AI_LLM_BEARER_TOKEN=YOUR_GENERATED_API_KEY_HERE
AI_MODEL_NAME=phi:latest

AI_EMBEDDING_URL=https://ollama.yourdomain.com
AI_EMBEDDING_MODEL=nomic-embed-text:latest
```

---

## 7. RAG (Retrieval-Augmented Generation) Architecture & Workspace Pipeline

The **EduMi AI Study Workspace** (`rag_workspace`) integrates Retrieval-Augmented Generation (RAG) to deliver zero-hallucination academic tutoring directly grounded in uploaded course study materials (`StudyMaterial`, e.g., lecture slides, textbooks, PDF notes).

### 🔄 End-to-End RAG Execution Flow

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   STUDENT / USER INTERFACE                                  │
│                   Selects Study Materials + Choice of 5 Learning Modes                     │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ Prompt + Material IDs
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              EDUMI DJANGO RAG WORKSPACE SERVICE                             │
│                                  (`rag_workspace/services.py`)                              │
│                                                                                             │
│  1. Document Chunk Retrieval: Query `MaterialChunk` database for selected materials          │
│  2. Dense Vector Embeddings: Fetch embedding for query via `nomic-embed-text`               │
│  3. Hybrid Search Scoring: Combine Cosine Similarity (75%) + BM25 Lexical Keyword (25%)     │
│  4. Strict Grounding Filter: Check `max_score >= 0.12` threshold to prevent hallucinations  │
│  5. Dynamic Prompt Assembly: Inject Top-6 source chunks with [Title, Page X] markers         │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ Assembled System + User Prompt Payload
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               CLOUDFLARE TUNNEL + FASTAPI GATEWAY                           │
│                     (HTTPS Auth Proxy -> `http://127.0.0.1:8765/api/generate`)             │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ Encrypted Loopback Pass-Through
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 LOCAL OLLAMA INFERENCE ENGINE                               │
│                                (`phi:latest` @ Port 11434)                                  │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ NDJSON Token Stream (SSE)
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  STUDENT / USER INTERFACE                                  │
│                       Renders real-time answer with page-level citations                     │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 🧠 Core RAG Engine Components

#### 1. Document Extraction & Chunking (`meetings.models.MaterialChunk`)
- Course materials uploaded by instructors are parsed and divided into sequential `MaterialChunk` records.
- Each chunk preserves exact page numbers (`page_number`), parent unit metadata (`unit_title`), and document titles to allow pinpoint source attribution.

#### 2. Vector Embedding Generation (`get_nomic_embedding`)
- **Primary Model**: `nomic-embed-text:latest` (768-dimensional float vectors) hosted on local Ollama via `/api/embeddings`.
- **Circuit Breaker**: A 30-second offline circuit breaker avoids batch indexing slowdowns if the embedding endpoint is temporarily unreachable.
- **Fallback**: Secondary support for OpenAI `text-embedding-3-small` when an OpenAI key is present in `.env`.

#### 3. Hybrid Search Algorithm (`retrieve_source_chunks`)
To achieve high recall and semantic precision, chunk retrieval utilizes a weighted **Hybrid Search**:
- **Dense Vector Cosine Similarity (75% Weight)**: Measures semantic context match between query vector $\vec{q}$ and chunk vector $\vec{c}$:
  $$\text{Cosine Similarity} = \frac{\vec{q} \cdot \vec{c}}{\|\vec{q}\| \|\vec{c}\|}$$
- **Lexical BM25 Keyword Match (25% Weight)**: Measures exact keyword hits with logarithmic frequency scaling and document title boosting.
- **Selection**: Returns the Top-6 highest scoring chunks (`top_k=6`) for prompt injection.

#### 4. Hallucination Prevention & Strict Grounding Mode
- **Strict Grounding (`strict_mode=True`)**: If the highest chunk score falls below the relevance threshold (`max_score < 0.12`), the engine blocks generation and safely responds:
  > *"I couldn't find this information in your selected study materials."*
- **Instructor Safeguards (`RagInstructorSetting`)**: Course instructors can configure classroom-level controls to toggle feature availability, mandate source citations, or permit fallback to external general knowledge when relevant materials are missing.

---

### 🎓 5 Specialized Educational Learning Modes

The RAG engine powers 5 distinct study workflows tailored for interactive learning:

| Mode | Purpose & Behavior | Prompt Strategy & System Persona |
| :--- | :--- | :--- |
| **`ask`** | Direct Q&A grounded strictly in selected course documents. | Instructs LLM to answer using *only* context chunks and cite source titles and pages as `[Title, Page X]`. |
| **`explain`** | Multi-tiered topic explanations matching student comprehension levels (`simple`, `detailed`, `exam`). | Adapts depth: `simple` uses analogies; `detailed` provides step-by-step principles; `exam` highlights formulas, definitions, and test questions. |
| **`summarize`** | Automated structured study guides for selected chapters or units. | Generates Markdown sections: 1. Key Concepts, 2. Important Definitions, 3. Core Formulas/Rules, 4. Practical Examples, 5. Exam Focus Points. |
| **`quiz`** | Interactive multiple-choice question generation. | Extracts key material concepts to synthesize practice questions, options, correct choices, and detailed answer explanations. |
| **`revision`** | Flashcards and quick review decks for exam prep. | Generates key concept cards with front-facing prompt and back-facing answer key tied to specific unit topics. |

---

### 📊 Data Models & Audit Logging Architecture

All user interactions in the RAG workspace are logged for analytical auditing and session continuation:

- **`RagSession`**: Manages active study sessions, linking users to selected `StudyMaterial` items, active mode, and strict mode preferences.
- **`RagChatMessage`**: Persists multi-turn conversation logs, role (`user`/`assistant`), content, and structured source citations (`sources`).
- **`RagQueryLog`**: Audit record logging raw user prompts, generated responses, retrieved chunk count, strict mode status, and whether a "not found" state was triggered.
- **`RagInstructorSetting`**: Classroom configuration record allowing instructors to grant or restrict specific AI modes and citation policies.

---

## 8. Verification & Testing Playbook

Execute these verification commands from your **Remote Server**:

### 1. Public Health Check
```bash
curl -i "https://ollama.yourdomain.com/health"
```
*Expected Output: `HTTP/2 200 OK` with Ollama status `online`.*

### 2. Authenticated Model List Query (`/api/tags`)
```bash
curl -i "https://ollama.yourdomain.com/api/tags" \
  -H "Authorization: Bearer YOUR_GENERATED_API_KEY_HERE"
```
*Expected Output: `HTTP/2 200 OK` returning JSON array of installed models (`nomic-embed-text`, `phi:latest`).*

### 3. Dense Vector Embedding Test (`/api/embeddings`)
```bash
curl -X POST "https://ollama.yourdomain.com/api/embeddings" \
  -H "Authorization: Bearer YOUR_GENERATED_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nomic-embed-text:latest",
    "prompt": "RAG document retrieval test chunk"
  }'
```
*Expected Output: `HTTP/2 200 OK` returning float array vector (`"embedding": [0.012, -0.045, ...]`).*

### 4. Real-Time Streaming Generation Test (`/api/generate`)
```bash
curl -N -X POST "https://ollama.yourdomain.com/api/generate" \
  -H "Authorization: Bearer YOUR_GENERATED_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "phi:latest",
    "prompt": "State the law of conservation of energy in one sentence.",
    "stream": true
  }'
```
*Expected Output: Incremental stream of NDJSON token frames terminating with `"done": true`.*

---

## 9. Troubleshooting & Edge-Case Reference

| Symptom / Error | Root Cause | Solution |
| :--- | :--- | :--- |
| **`502 Bad Gateway`** | FastAPI Gateway (`:8765`) or Ollama (`:11434`) is offline. | Run `sudo systemctl status ollama-gateway` and ensure Uvicorn is listening on `127.0.0.1:8765`. |
| **`401 Unauthorized`** | Missing or mismatched `Authorization` Bearer header. | Verify `AI_LLM_BEARER_TOKEN` in remote `.env` matches `OLLAMA_API_KEY` on local gateway. |
| **`524 Timeout Occurred`** | Non-streaming generation (`stream=False`) timed out on cold start. | Ensure client sets `"stream": true` so first tokens arrive immediately. |
| **`Model Not Found`** | Requested model (e.g. `phi:latest`) is not pulled on local PC. | Run `ollama pull phi:latest` on local machine. |
| **Connection Reset / Hang** | High request concurrency exhausting sockets. | Covered by FastAPI `lifespan` HTTP connection pool in Section 2. |
