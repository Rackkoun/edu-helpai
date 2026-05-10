# Makefile

# Cross-platform: Linux/Mac use shell scripts, Windows uses PowerShell.
# Install make on Windows: winget install GnuWin32.Make
# or via chocolatey:
# choco install make
# or via scoop:
# scoop install make

.PHONY: start start-gpu stop stop-clean restart logs logs-backend \
        build build-ollama test lint models clean help \
        k8s-start k8s-start-gpu k8s-stop k8s-stop-cluster k8s-clean


# ensure to make the scripts executatble: chmod +x scripts/linux/app-start.sh

# OS detection
ifeq ($(OS),Windows_NT)
    SHELL := pwsh.exe
    .SHELLFLAGS := -NoProfile -NonInteractive -Command
    START_SCRIPT     := .\scripts\windows\Start-EduHelpAI.ps1
    START_GPU_SCRIPT := .\scripts\windows\Start-EduHelpAI.ps1 -Gpu
    STOP_SCRIPT      := docker compose down
    K8S_START        := .\k8s\scripts\windows\Start-Minikube.ps1
    K8S_START_GPU    := .\k8s\scripts\windows\Start-Minikube.ps1 -Gpu
    K8S_STOP         := .\k8s\scripts\windows\Stop-Minikube.ps1
    K8S_STOP_CLUSTER := .\k8s\scripts\windows\Stop-Minikube.ps1 -StopCluster
    K8S_CLEAN        := .\k8s\scripts\windows\Stop-Minikube.ps1 -DeleteCluster
else
    START_SCRIPT     := ./scripts/linux/app-start.sh
    START_GPU_SCRIPT := ./scripts/linux/app-start.sh --gpu
    STOP_SCRIPT      := docker compose down
    K8S_START        := ./k8s/scripts/linux/minikube-start.sh
    K8S_START_GPU    := ./k8s/scripts/linux/minikube-start.sh --gpu
    K8S_STOP         := ./k8s/scripts/linux/minikube-stop.sh
    K8S_STOP_CLUSTER := ./k8s/scripts/linux/minikube-stop.sh --stop-cluster
    K8S_CLEAN        := ./k8s/scripts/linux/minikube-stop.sh --delete-cluster
endif


# ------------------------
# DOCKER COMPOSE
# ------------------------
start: ## Start all services — CPU (Docker Compose)
	$(START_SCRIPT)

start-gpu: ## Start all services — NVIDIA GPU (Docker Compose)
	$(START_GPU_SCRIPT)

stop: ## Stop all containers (keep volumes/data)
	docker compose down

stop-clean: ## Stop and delete all volumes (destructive)
	docker compose down -v

restart: ## Restart backend + frontend only (keep Ollama running)
	docker compose restart backend frontend

logs: ## Follow all container logs
	docker compose logs --follow

logs-backend: ## Follow backend logs only
	docker compose logs backend --follow

build: ## Rebuild all images without cache
	docker compose build --no-cache

build-ollama: ## Rebuild only the Ollama image
	docker compose build ollama


# -----------------------------------------
# QUALITY
# -----------------------------------------
test: ## Run test suite (≥90% coverage required)
	pytest tests/ -v --cov=src/backend --cov-report=term-missing --cov-fail-under=90

lint: ## Run black + flake8 + mypy
	black --check src/ tests/
	flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203
	mypy src/ tests/ --ignore-missing-imports

format: ## Auto-format code with black
	black src/ tests/


# ----------------
# OLLAMA
# ----------------
models: ## List downloaded Ollama models
	docker exec edu_ollama ollama list

# ----------------
# CLEANUP
# ----------------
clean: ## Remove locally built images
	docker compose down --rmi local


# ------------------------
# KUBERNETES (MINIKUBE)
# ------------------------
k8s-start: ## Deploy on minikube — CPU
	$(K8S_START)

k8s-start-gpu: ## Deploy on minikube — NVIDIA GPU
	$(K8S_START_GPU)

k8s-connect: ## Forward all minikube services to localhost
ifeq ($(OS),Windows_NT)
	pwsh -File k8s\scripts\windows\Connect-Minikube.ps1
else
	./k8s/scripts/linux/minikube-connect.sh
endif

k8s-stop: ## Delete app namespace (keep minikube cluster running)
	$(K8S_STOP)

k8s-stop-cluster: ## Stop minikube (cluster preserved, restartable)
	$(K8S_STOP_CLUSTER)

k8s-clean: ## Delete minikube cluster entirely (destructive)
	$(K8S_CLEAN)



# ---------------------
# HELP
# ---------------------
help: ## Show this help
ifeq ($(OS),Windows_NT)
	@pwsh -NoProfile -Command "Get-Content Makefile | Where-Object { $$_ -match '^[a-zA-Z_-]+:.*##' } | ForEach-Object { $$parts = $$_ -split ':.*## '; Write-Host ('  {0,-20} {1}' -f $$parts[0], $$parts[1]) }"
else
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
endif

.DEFAULT_GOAL := help