.PHONY: test test-po test-dev test-frontend test-qa test-form run pipeline docker-build docker-up docker-down docker-logs

test:
	pytest --cov=src --cov-report=term-missing

test-form:
	pytest tests/test_agent_form.py -v
test-po:
	pytest tests/test_agent_po.py -v
test-dev:
	pytest tests/test_agent_dev.py -v
test-frontend:
	pytest tests/test_agent_frontend.py -v
test-qa:
	pytest tests/test_agent_qa.py -v
test-orchestrator:
	pytest tests/test_orchestrator.py -v

run:
	python -m src.agent_form.app

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f autodev
