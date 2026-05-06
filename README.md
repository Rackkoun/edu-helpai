# Edu-HelpAI 🎓
 A **local, privacy-first** RAG-based study assistant.  
Upload your lecture notes, PDFs and CSV files then ask questions about them.  
Everything runs on your machine. No cloud. No data sharing.

---

## Table of Contents

1. [What is it?](#what-is-it)
2. [Tech Stack](#tech-stack)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
   - [A-) Local (host machine)](#a--local-host-machine)
   - [B-) Docker Compose](#b--docker-compose)
   - [C-) Kubernetes (minikube)](#c--kubernetes-minikube)
5. [Usage](#usage)
6. [Development](#development)
7. [Project Structure](#project-structure)

---

## What is it?

Edu-HelpAI is a **Retrieval-Augmented Generation (RAG)** chatbot that:

1. **Indexes** your documents, splits them into chunks and generates vector embeddings via Ollama (`nomic-embed-text`)
2. **Retrieves** the most relevant chunks when you ask a question (cosine similarity)
3. **Generates** an answer grounded in your documents using a local LLM (`mistral:7b` via Ollama)

No data ever leaves your machine.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM + Embeddings | [Ollama](https://ollama.com):  `mistral:7b`, `nomic-embed-text` |
| Backend API | FastAPI + SQLAlchemy + aiosqlite |
| Frontend UI | [Chainlit](https://chainlit.io) |
| Experiment tracking | MLflow |
| Containerisation | Docker Compose |
| Orchestration | Kubernetes (minikube) |
| Language | Python 3.11.3 |

---

## Prerequisites

### All approaches
- [Ollama](https://ollama.com/download) installed and running
- Python 3.11.3

### Docker Compose (Approach B)
- [Docker Desktop](https://docs.docker.com/desktop/)

### Kubernetes / minikube (Approach C)
- [Docker Desktop](https://docs.docker.com/desktop/)
- [minikube](https://minikube.sigs.k8s.io/docs/start/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- `make`  install on Windows: `winget install GnuWin32.Make`

---

## Quick Start

### A-) Local (host machine)

Run each service directly on your machine. Best for active development.

#### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

#### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the output as SECRET_KEY in .env
```

#### 3. Pull Ollama models (one-time)

```bash
ollama pull mistral:7b
ollama pull nomic-embed-text
```

#### 4. Start each service in a separate terminal

**Terminal 1: FastAPI backend:**
```bash
uvicorn src.backend.main:app --reload --port 8000
```

**Terminal 2: Chainlit frontend:**
```bash
chainlit run src/frontend/app.py --port 8001
```

**Terminal 3: MLflow UI (optional):**
```bash
mlflow server --backend-store-uri sqlite:///data/mlflow.db --port 5000
```

#### 5. Open the app

| Service | URL |
|---|---|
| Chat UI | http://localhost:8001 |
| API docs | http://localhost:8000/docs |
| MLflow | http://localhost:5000 |

---

### B-)  Docker Compose

Runs everything in containers. No Python installation needed on the host beyond running the script.

#### Option B1: Automated script (recommended)

**Linux / macOS:**
```bash
chmod +x scripts/linux/app-start.sh

./scripts/linux/app-start.sh          # CPU
./scripts/linux/app-start.sh --gpu    # NVIDIA GPU
```

**Windows (PowerShell):**
```powershell
# Allow local scripts (run once as Administrator):
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

.\scripts\windows\Start-EduHelpAI.ps1          # CPU
.\scripts\windows\Start-EduHelpAI.ps1 -Gpu     # NVIDIA GPU
```

The script:
1. Builds all images
2. Starts Ollama and waits for it to be healthy
3. Pulls `mistral:7b` and `nomic-embed-text` (skips if already cached)
4. Starts backend, frontend, and MLflow
5. Prints access URLs

#### Option B2: Make

```bash
make start        # CPU
make start-gpu    # NVIDIA GPU
```

#### Option B3: Manual Docker Compose

```bash
# First run only: start Ollama and pull models
docker compose up ollama -d
docker exec edu_ollama ollama pull mistral:7b
docker exec edu_ollama ollama pull nomic-embed-text

# Start everything
docker compose up -d

# Subsequent runs (models already cached):
docker compose up -d
```

#### GPU mode

```bash
# Linux/macOS:
docker compose --profile gpu up -d

# Windows:
.\scripts\windows\Start-EduHelpAI.ps1 -Gpu
```

#### Access URLs (Docker Compose)

| Service | URL |
|---|---|
| Chat UI | http://localhost:8001 |
| API docs | http://localhost:8000/docs |
| MLflow | http://localhost:5000 |
| Ollama | http://localhost:11434 |

#### Useful commands

```bash
# Stop (keep data/volumes)
docker compose down
make stop

# Stop and wipe all data
docker compose down -v
make stop-clean

# View logs
docker compose logs --follow
docker compose logs backend --follow
make logs
make logs-backend

# Rebuild images
docker compose build --no-cache
make build

# List downloaded models
docker exec edu_ollama ollama list
make models
```

---

### C-) Kubernetes (minikube)

Simulates a production cluster locally. Use this to test K8s manifests before deploying to a real cluster.

#### Option C1: Automated script (recommended)

**Windows (PowerShell):**
```powershell
.\k8s\scripts\windows\Start-Minikube.ps1          # CPU
.\k8s\scripts\windows\Start-Minikube.ps1 -Gpu     # NVIDIA GPU
```

**Linux / macOS:**
```bash
chmod +x k8s/scripts/linux/minikube-start.sh
./k8s/scripts/linux/minikube-start.sh             # CPU
./k8s/scripts/linux/minikube-start.sh --gpu       # NVIDIA GPU
```

The script:
1. Starts minikube (4 CPU, 8 GB RAM)
2. Pre-pulls the Ollama image into minikube's Docker cache
3. Builds backend and frontend images inside minikube
4. Creates namespace, configmap, PVCs, and a fresh `SECRET_KEY`
5. Deploys Ollama and waits for it to be ready
6. Pulls `mistral:7b` and `nomic-embed-text` into the Ollama pod
7. Deploys backend and frontend
8. Prints access instructions

#### Option C2: Make

```bash
make k8s-start        # CPU
make k8s-start-gpu    # NVIDIA GPU
```

#### Accessing the app on minikube

Services are exposed as `NodePort`. Get the minikube IP first:

```bash
minikube ip
# e.g. 192.168.49.2
```

| Service | URL |
|---|---|
| Chat UI | `http://$(minikube ip):30801` |
| API docs | `http://$(minikube ip):30800/docs` |
| Ollama | `http://$(minikube ip):30434` |

**Alternative: port-forward (works without NodePort):**
```bash
# Run each in a separate terminal:
kubectl port-forward svc/frontend-service 8001:8001 -n edu-helpai
kubectl port-forward svc/backend-service  8000:8000 -n edu-helpai

# Then access at:
# http://localhost:8001   (Chat UI)
# http://localhost:8000/docs   (API)
```

**Alternative: minikube tunnel (exposes all services at localhost):**
```bash
# Run in a separate terminal (keeps running):
minikube service frontend-service -n edu-helpai
minikube service backend-service  -n edu-helpai
```

#### Useful kubectl commands

```bash
# Check pod status
kubectl get pods -n edu-helpai
kubectl get pods -n edu-helpai --watch

# Check service ports
minikube service list -n edu-helpai

# View logs
kubectl logs -l app=backend  -n edu-helpai --follow
kubectl logs -l app=frontend -n edu-helpai --follow
kubectl logs -l app=ollama   -n edu-helpai --follow

# Describe a failing pod
kubectl describe pod -l app=backend -n edu-helpai

# Check resource usage
kubectl top pod -n edu-helpai

# Open minikube dashboard
minikube dashboard
```

#### Teardown

```bash
# Delete app namespace only (keep minikube running, fastest re-deploy):
.\k8s\scripts\windows\Stop-Minikube.ps1
make k8s-stop

# Stop minikube (preserves cluster, can restart with minikube start):
.\k8s\scripts\windows\Stop-Minikube.ps1 -StopCluster
make k8s-stop-cluster

# Delete minikube entirely (re-downloads images next time):
.\k8s\scripts\windows\Stop-Minikube.ps1 -DeleteCluster
make k8s-clean
```

---

## Usage

### Uploading documents

1. Open the Chat UI
2. Click the 📎 paperclip icon
3. Select a PDF, TXT, CSV, or Markdown file (max 50 MB)
4. Wait for the "✅ Added to knowledge base" confirmation
5. Ask questions; answers will be grounded in your documents

### Supported file types

| Extension | Type |
|---|---|
| `.pdf` | PDF documents |
| `.txt` | Plain text |
| `.md` | Markdown |
| `.csv` | CSV data |

### Generating a new secret key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Development

### Run tests

```bash
pytest tests/ -v --cov=src/backend --cov-report=term-missing --cov-fail-under=90
make test
```

### Lint and type-check

```bash
black --check src/ tests/
flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203
mypy src/ tests/ --ignore-missing-imports
make lint
```

### Auto-format

```bash
black src/ tests/
make format
```

### Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | - | **Required.** Min 32 chars. Generate with `secrets.token_hex(32)` |
| `DATABASE_URL` | `sqlite:///data/edu_helpai.db` | SQLite for dev, PostgreSQL for prod |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `mistral:7b` | LLM model name |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `CHUNK_SIZE` | `500` | Document chunk size (characters) |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `RAG_TOP_K` | `5` | Number of chunks retrieved per query |
| `DEBUG` | `false` | Enable debug mode |

---

## Project Structure

```
edu-helpai/
├── docker/
│   ├── Dockerfile.backend      # FastAPI backend image
│   ├── Dockerfile.frontend     # Chainlit frontend image
│   └── Dockerfile.ollama       # Ollama + curl image
├── k8s/
│   ├── scripts/
│   │   ├── linux/              # Bash automation scripts
│   │   └── windows/            # PowerShell automation scripts
│   ├── backend-deployment.yaml
│   ├── configmap.yaml
│   ├── frontend-deployment.yaml
│   ├── namespace.yaml
│   ├── ollama-deployment.yaml
│   ├── ollama-gpu-deployment.yaml
│   └── pvc.yaml
├── scripts/
│   ├── linux/app-start.sh      # Docker Compose startup (Linux/macOS)
│   └── windows/
│       ├── Start-EduHelpAI.ps1 # Docker Compose startup (Windows)
│       └── Stop-EduHelpAI.ps1  # Docker Compose teardown (Windows)
├── src/
│   ├── backend/
│   │   ├── api/routes/         # FastAPI route handlers
│   │   ├── core/               # Database engine + session
│   │   ├── models/             # SQLAlchemy models
│   │   ├── services/           # RAG, embedding, document processor
│   │   ├── config.py           # Pydantic settings
│   │   └── main.py             # FastAPI app entry point
│   └── frontend/
│       └── app.py              # Chainlit UI
├── tests/                      # pytest test suite (≥90% coverage)
├── .env.example                # Environment variable template
├── docker-compose.yaml
├── Makefile                    # Cross-platform task runner
└── pyproject.toml
```