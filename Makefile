.PHONY: test test-po test-dev test-frontend test-qa test-form test-orchestrator test-validation-docker test-graphe graphe nettoyer-sauvegardes run pipeline docker-build docker-up docker-down docker-logs

# PYTHONPATH vide : evite que pytest charge les plugins ROS (launch_testing) du ~/.bashrc
PYTEST = env -u PYTHONPATH pytest

test:
	$(PYTEST) --cov=src --cov-report=term-missing

test-form:
	$(PYTEST) tests/test_agent_form.py -v
test-po:
	$(PYTEST) tests/test_agent_po.py -v
test-dev:
	$(PYTEST) tests/test_agent_dev.py -v
test-frontend:
	$(PYTEST) tests/test_agent_frontend.py -v
test-qa:
	$(PYTEST) tests/test_agent_qa.py -v
test-orchestrator:
	$(PYTEST) tests/test_orchestrator.py -v
test-validation-docker:
	$(PYTEST) tests/test_agent_validation_docker.py -v
test-graphe:
	$(PYTEST) tests/test_graphe.py -v

graphe:
	python -m src.agent_orchestrateur.graphe

nettoyer-sauvegardes:
	rm -f checkpoints/pipeline.sqlite

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
