.PHONY: bootstrap test lint help

help:
	@echo "FlowSnip - Available targets:"
	@echo "  make bootstrap - Setup development environment (run this first!)"
	@echo "  make test      - Run tests with coverage"
	@echo "  make lint      - Lint and format code"
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
