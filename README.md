# 🎓 Edu-HelpAI


[![Python 3.11.3](https://img.shields.io/badge/python-3.11.3-blue.svg)](https://www.python.org/downloads/)

RAG-based local chatbot for students. Upload your study materials and get intelligent answers without sending data to the cloud.

## Features

- ✅ **Local-first**: Runs entirely on your machine using Ollama
- ✅ **RAG Architecture**: Retrieves relevant chunks from your documents
- ✅ **Document Upload**: PDF, TXT support with more coming
- ✅ **Conversation History**: Track all Q&A sessions
- ✅ **Docker & K8s Ready**: Easy deployment with Minikube

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend API | FastAPI |
| Chat UI | Chainlit |
| LLM | Ollama (Mistral/LLaMA3) |
| Vector DB | ChromaDB |
| Metadata DB | SQLite/PostgreSQL |
| Container | Docker + Kubernetes |
| CI/CD | GitHub Actions |
| Tracking | MLflow |


## Quick Start

```bash
# Clone and setup
git clone https://github.com/Rackkoun/edu-helpai.git
cd edu-helpai
python -m venv venv
source venv/bin/activate  # or `venv\\Scripts\\activate` on Windows
pip install -r requirements.txt
```

# Start Ollama (in separate terminal)
```Shell
ollama pull mistral
ollama serve
```
# Run the app

```Shell
uvicorn app.main:app --reload --port 8000 &
chainlit run app/chainlit_app.py -w
```