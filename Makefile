# Makefile
.PHONY: Start start-gpu stop restart logs build clean help

# ensure to make the scripts executatble: chmod +x scripts/linux/app-start.sh
# USAGE:
#   make start        # CPU
#   make start-gpu    # GPU
#   make stop
#   make logs

# K8S USAGE:
#   make start          # local Docker, CPU
#   make start-gpu      # local Docker, GPU
#   make k8s-start      # minikube, CPU
#   make k8s-start-gpu  # minikube, GPU

# ------------------------
# START
# ------------------------
start:  # start all services (CPU)
	./scripts/linux/app-start.sh
start-gpu:  #  start all services (NVIDIA GPU)
	./scripts/linux/app-start.sh


# -----------------------------------------
# STOP
# -----------------------------------------
stop:  # stop all containers (keep volumes/data)
	docker compose down

stop-clean:  # stop and delete all data (volumes)
	docker compose down -v


# ----------------
# DEV
# ----------------
restart:  # restart backend + frontend only (keep ollama running)
	docker compose restart backend frontend

logs:  # follow all logs
	docker compose logs --follow

logs-backend:  # Follow backend logs only
	docker compose logs backend --follow

build:  # Rebuild images without cache
	docker compose build --no-cache

build-ollama:  # build only ollama image
	docker compose build ollama

# ----------------
# Tests
# ----------------
test:  # Run test suite
	pytest tests/ -v --cov=src/backend --cov-report=term-missing --cov-fail-under=90

lint:  # Run black + flake8 + mypy
	black --check src/ tests/
	flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203
	mypy src/ tests/ --ignore-missing-imports


# ----------------
# Ollama
# ----------------
models:  # List downloaded Ollama models
	docker exec edu_ollama ollama list


# ----------------
# Cleanup
# ----------------
clean:  # Remove built images
	docker compose down --rmi local

help:  # Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'



# ---------------------
# K8S
# ---------------------
k8s-start:  # Start on minikube (CPU)
	./k8s/scripts/linux/minikube-start.sh

k8s-start-gpu:  # Start on minikube (GPU)
	./k8s/scripts/linux/minikube-start.sh --gpu

k8s-stop:  # Delete minikube namespace (keeps cluster)
	kubectl delete namespace edu-helpai

k8s-clean:  # Stop minikube entirely
	minikube stop && minikube delete