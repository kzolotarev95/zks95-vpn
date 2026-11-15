.PHONY: install update health down test lint
install:
	sudo bash scripts/install.sh
update:
	sudo bash scripts/update.sh
health:
	bash scripts/health-check.sh
down:
	docker compose down
test:
	python -m pytest -q
lint:
	ruff check backend migrations scripts
	ruff format --check backend migrations scripts
	cd apps/web && npm run lint && npm run typecheck
