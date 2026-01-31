# Makefile for Varta MQTT Service

.PHONY: help install install-dev test test-cov clean docker-build docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install      - Install package"
	@echo "  make install-dev  - Install with development dependencies"
	@echo "  make test         - Run tests"
	@echo "  make test-cov     - Run tests with coverage"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up    - Start Docker container"
	@echo "  make docker-down  - Stop Docker container"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest

test-cov:
	pytest --cov=varta_mqtt --cov-report=html --cov-report=term

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	cd docker && docker-compose build

docker-up:
	cd docker && docker-compose up -d

docker-down:
	cd docker && docker-compose down

docker-logs:
	cd docker && docker-compose logs -f
