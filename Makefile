.PHONY: help vpn-bypass-docker check-printer pre-commit-install pre-commit

SHELL := /bin/bash

help: ## Показать справку по командам
	@echo "========================================================================"
	@echo "PrintWatch - Стенд мониторинга 3D-принтеров (Klipper / Moonraker)"
	@echo "========================================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

vpn-bypass-docker: ## Добавить маршруты и ip rule для обхода VPN (LAN 192.168.0.0/16 и Docker 172.16.0.0/12)
	@echo "==> Запуск скрипта обхода VPN для Docker и локальной сети..."
	@./scripts/vpn-bypass-docker.sh

check-printer: ## Проверить маршрутизацию и сетевую доступность всех N принтеров
	@./scripts/check-printer.sh

pre-commit-install: ## Установить pre-commit через uv и зарегистрировать git-хуки в репозитории
	@echo "==> Установка pre-commit через uv..."
	@uv tool install --upgrade pre-commit
	@echo "==> Регистрация git-хуков в локальном репозитории (pre-commit, commit-msg, pre-push)..."
	@uv tool run pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
	@echo "✓ Pre-commit успешно установлен и активирован!"

pre-commit: ## Запустить ВСЕ проверки pre-commit по всем файлам проекта
	@echo "==> Запуск ВСЕХ проверок pre-commit..."
	@uv tool run pre-commit run --all-files
