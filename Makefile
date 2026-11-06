.PHONY: vpn-bypass-docker check-printer

SHELL := /bin/bash

vpn-bypass-docker: ## Добавить маршруты и ip rule для обхода VPN
	@echo "==> Запуск скрипта обхода VPN для Docker и локальной сети..."
	@./scripts/vpn-bypass-docker.sh

check-printer: ## Проверить маршрутизацию и сетевую доступность всех N принтеров
	@./scripts/check-printer.sh