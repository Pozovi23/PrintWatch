.PHONY: help up down restart logs status build add-printer vpn-bypass-docker check-printer test test-live test-all sync lock reload-prometheus pre-commit-install pre-commit

SHELL := /bin/bash

help: ## Показать справку по командам
	@echo "========================================================================"
	@echo "PrintWatch - Стенд мониторинга 3D-принтеров (Klipper / Moonraker)"
	@echo "========================================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Запустить стек мониторинга (Prometheus, Grafana, Alertmanager, Exporter, Camera)
	docker compose up -d

down: ## Остановить и удалить контейнеры стека
	docker compose down

restart: ## Перезапустить все сервисы
	docker compose restart

logs: ## Просмотр логов в реальном времени (follow)
	docker compose logs -f

status: ## Статус и здоровье контейнеров
	docker compose ps

build: ## Собрать / пересобрать образы exporter и camera-proxy
	docker compose build

add-printer: ## Перезапустить экспортёр и применить добавленные в printers.yaml принтеры
	@echo "==> Обновление конфигурации N принтеров..."
	docker compose restart printer-exporter camera-proxy
	@echo "✓ Экспортёр и прокси камер перезапущены с обновлённым списком принтеров!"

vpn-bypass-docker: ## Добавить маршруты и ip rule для обхода VPN (LAN 192.168.0.0/16 и Docker 172.16.0.0/12)
	@echo "==> Запуск скрипта обхода VPN для Docker и локальной сети..."
	@./scripts/vpn-bypass-docker.sh

check-printer: ## Проверить маршрутизацию и сетевую доступность всех N принтеров
	@./scripts/check-printer.sh

test: ## Запустить модульные тесты (Unit tests с моками через uv или в контейнере)
	@PYTHONPATH="" uv run pytest -v -m "not live" services/printer-exporter/tests 2>/dev/null || docker compose run --rm --no-deps printer-exporter pytest -v -m "not live" /app/tests

test-live: ## Запустить интеграционные тесты реальных принтеров из config/printers.yaml
	@PYTHONPATH="" uv run pytest -v -m live services/printer-exporter/tests 2>/dev/null || docker compose run --rm --network=host printer-exporter pytest -v -m live /app/tests

test-all: ## Запустить все тесты (модульные + интеграционные)
	@PYTHONPATH="" uv run pytest -v services/printer-exporter/tests 2>/dev/null || docker compose run --rm --network=host printer-exporter pytest -v /app/tests

sync: ## Установить все зависимости и поднять виртуальное окружение .venv через uv.lock
	uv sync --all-packages

lock: ## Обновить файл блокировки uv.lock
	uv lock

reload-prometheus: ## Перезагрузить правила и конфигурацию Prometheus без перезапуска контейнера
	curl -s -X POST http://localhost:9090/-/reload && echo "✓ Prometheus config reloaded"

pre-commit-install: ## Установить pre-commit через uv и зарегистрировать git-хуки в репозитории
	@echo "==> Установка pre-commit через uv..."
	@uv tool install --upgrade pre-commit
	@echo "==> Регистрация git-хуков в локальном репозитории (pre-commit, commit-msg, pre-push)..."
	@uv tool run pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
	@echo "✓ Pre-commit успешно установлен и активирован!"

pre-commit: ## Запустить ВСЕ проверки pre-commit по всем файлам проекта
	@echo "==> Запуск ВСЕХ проверок pre-commit..."
	@uv tool run pre-commit run --all-files
