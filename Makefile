.PHONY: bootstrap test lint release help

help:
	@echo "FlowSnip - Available targets:"
	@echo "  make bootstrap - Setup development environment (run this first!)"
	@echo "  make test      - Run tests with coverage"
	@echo "  make lint      - Lint and format code"
	@echo "  make release   - Cut a release (e.g. make release v=1.2.3)"
	@echo "  make help      - Show this help message"

bootstrap:
	@echo "🚀 Bootstrapping FlowSnip development environment..."
	@command -v python3 >/dev/null 2>&1 || (echo "❌ Python 3 not found. Please install Python 3.11 or higher." && exit 1)
	@python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" || (echo "❌ Python 3.11+ required. Current version:" && python3 --version && exit 1)
	@echo "✓ Python 3.11+ detected"
	@command -v uv >/dev/null 2>&1 || (echo "📦 Installing UV package manager..." && pip install --upgrade uv)
	@echo "✓ UV available"
	@echo "📦 Installing project dependencies..."
	@uv sync
	@echo "✓ Dependencies installed"
	@echo "🖥️  Ensuring GUI runtime is available..."
	@uv run python -c "import tkinter" >/dev/null 2>&1 || ( \
		if command -v dnf >/dev/null 2>&1; then \
			if command -v sudo >/dev/null 2>&1; then \
				echo "📦 Installing Fedora/RHEL Tk runtime with sudo dnf..."; \
				sudo dnf install -y python3-tkinter; \
			else \
				echo "⚠️  GUI runtime missing. Sudo is required to install python3-tkinter automatically on Fedora/RHEL."; \
				exit 1; \
			fi; \
		elif command -v apt-get >/dev/null 2>&1; then \
			if command -v sudo >/dev/null 2>&1; then \
				echo "📦 Installing Debian/Ubuntu Tk runtime with sudo apt-get..."; \
				sudo apt-get update && sudo apt-get install -y python3-tk; \
			else \
				echo "⚠️  GUI runtime missing. Sudo is required to install python3-tk automatically on Debian/Ubuntu."; \
				exit 1; \
			fi; \
		else \
			echo "⚠️  GUI runtime missing. Install the system Tk package manually for your distro."; \
			exit 1; \
		fi \
	)
	@uv run python -c "import tkinter" >/dev/null 2>&1 || (echo "❌ GUI runtime is still unavailable after bootstrap. Please install the system Tk package manually." && exit 1)
	@echo "✓ GUI runtime available"
	@echo "🔗 Installing pre-commit hooks..."
	@uv run pre-commit install
	@echo "✓ Pre-commit hooks installed"
	@echo "✅ Bootstrap complete! Your environment is ready."
	@command -v node >/dev/null 2>&1 || \
		echo "⚠  Node.js not found on PATH. Set FLOWSNIP_NODE_PATH=/path/to/node if needed for yt-dlp n-challenge solving."
	@echo ""
	@echo "Next steps:"
	@echo "  • Run 'make test' to verify the test suite"
	@echo "  • Run 'make lint' to check code quality"
	@echo "  • Run 'uv run python -m flowsnip.main' to start the app"

test:
	uv run pytest --cov=flowsnip --cov-report=html --cov-report=term

lint:
	uv run ruff check --fix flowsnip tests
	uv run ruff format flowsnip tests

release:
ifndef v
	$(error Usage: make release v=x.y.z)
endif
	@PREV=$$(git describe --tags --abbrev=0 2>/dev/null || echo "none"); \
	echo "Previous release: $$PREV  →  v$(v)"
	@python3 -c "import re; f=open('pyproject.toml'); s=f.read(); f.close(); s=re.sub(r'(?m)^version = \"[^\"]+\"', 'version = \"$(v)\"', s); open('pyproject.toml','w').write(s)"
	@uv sync
	@git add pyproject.toml uv.lock
	@git commit -m "chore: bump version to $(v)"
	@git tag -a v$(v) -m "v$(v)"
	@git push origin main
	@git push origin v$(v)
	@echo "Released v$(v)"
