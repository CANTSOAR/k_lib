# --- CONFIGURATION ---
BACKEND_DIR = backend
FRONTEND_DIR = frontend
PYTHON = python3
PIP = pip3
NPM = npm

# --- INSTALLATION ---
.PHONY: install
install: install-backend install-frontend

.PHONY: install-backend
install-backend:
	@echo "🐍 Installing Backend Dependencies..."
	cd $(BACKEND_DIR) && $(PIP) install fastapi uvicorn requests sentence-transformers numpy scikit-learn chromadb

.PHONY: install-frontend
install-frontend:
	@echo "⚛️  Installing Frontend Dependencies..."
	cd $(FRONTEND_DIR) && $(NPM) install

# --- RUNNING ---
# Usage: make -j 2 run (Runs both in parallel)
.PHONY: run
run:
	@echo "🚀 Starting Full Stack App..."
	@$(MAKE) -j 2 run-backend run-frontend

.PHONY: run-backend
run-backend:
	@echo "🔌 Starting FastAPI Backend..."
	cd $(BACKEND_DIR) && uvicorn main:app --reload --port 8000

.PHONY: run-frontend
run-frontend:
	@echo "💻 Starting React Frontend..."
	cd $(FRONTEND_DIR) && $(NPM) run dev

# --- UTILITIES ---
.PHONY: clean
clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "node_modules" -exec rm -rf {} +
	@echo "✅ Clean complete."

.PHONY: db-nuke
db-nuke:
	@echo "☢️  Wiping Database..."
	cd $(BACKEND_DIR) && $(PYTHON) -c "import database; database.init_db(nuke=True)"

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make install      - Install all dependencies (Backend & Frontend)"
	@echo "  make run          - Run both servers simultaneously (requires -j 2)"
	@echo "  make run-backend  - Run only FastAPI (Port 8000)"
	@echo "  make run-frontend - Run only React (Port 5173)"
	@echo "  make db-nuke      - Wipe and re-initialize the SQLite database"
	@echo "  make clean        - Remove __pycache__ and node_modules"