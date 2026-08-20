.PHONY: help setup dev dev-backend dev-frontend test lint clean

help:
	@echo "Available commands:"
	@echo "  make dev           - Start full development environment (Docker)"
	@echo "  make dev-backend   - Start backend only"
	@echo "  make dev-frontend  - Start frontend only"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linters"
	@echo "  make clean         - Clean up"

# 完整开发环境（Docker）
dev:
	docker-compose up --build

# 仅后端
dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

# 仅前端
dev-frontend:
	cd frontend && npm run dev

# 测试
test:
	cd backend && python -m pytest tests/ -v

# 代码检查
lint:
	cd backend && ruff check .
	cd frontend && npm run lint

# 清理
clean:
	docker-compose down -v
	rm -f backend/code_review.db
	rm -rf frontend/node_modules
