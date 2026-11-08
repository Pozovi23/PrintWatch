#!/usr/bin/env bash
# ==============================================================================
# check-printer.sh
# Диагностика доступности принтеров из config/printers.yaml
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
YAML_FILE="${PROJECT_ROOT}/config/printers.yaml"

if [ ! -f "$YAML_FILE" ]; then
    echo "❌ Ошибка: Файл конфигурации ${YAML_FILE} не найден!" >&2
    echo "   Создайте его на основе примера:" >&2
    echo "   cp config/printers.yaml.example config/printers.yaml" >&2
    exit 1
fi

echo "======================================================================"
echo "Диагностика сетевой доступности 3D-принтеров из config/printers.yaml"
echo "Конфигурация: ${YAML_FILE}"
echo "======================================================================"

declare -A PRINTERS_MAP=()

if [ -f "$YAML_FILE" ]; then
    current_name=""
    while IFS= read -r line; do
        if [[ $line =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*[\"\']?([^\"\'[:space:]]+) ]]; then
            current_name="${BASH_REMATCH[1]}"
        elif [[ $line =~ ^[[:space:]]*name:[[:space:]]*[\"\']?([^\"\'[:space:]]+) ]]; then
            current_name="${BASH_REMATCH[1]}"
        fi

        if [[ $line =~ ^[[:space:]]*host:[[:space:]]*[\"\']?([^\"\'[:space:]]+) ]]; then
            raw_host="${BASH_REMATCH[1]}"
            clean_host=$(echo "$raw_host" | sed -E 's|^https?://||; s|:[0-9]+/?$||; s|/.*$||' | tr -d ' "\r\n')
            p_name="${current_name:-printer}"
            if [ -n "$clean_host" ]; then
                PRINTERS_MAP["$p_name"]="$clean_host"
                current_name=""
            fi
        fi
    done < "$YAML_FILE"
fi

if [ ${#PRINTERS_MAP[@]} -eq 0 ]; then
    echo "❌ Ошибка: В файле ${YAML_FILE} не найдено ни одного принтера с полем 'host'." >&2
    exit 1
fi

for name in "${!PRINTERS_MAP[@]}"; do
    host="${PRINTERS_MAP[$name]}"
    echo ""
    echo "----------------------------------------------------------------------"
    echo "🔍 Проверка принтера: ${name} (Хост: ${host})"
    echo "----------------------------------------------------------------------"

    # [1] Проверка маршрута ядра
    echo "[1/3] Маршрут ядра Linux (ip route get):"
    route_out=$(ip route get "$host" 2>&1 || true)
    echo "      ${route_out}"
    if echo "$route_out" | grep -q "dev tun"; then
        echo "      ⚠️  ВНИМАНИЕ: Трафик идёт в VPN-туннель! Выполните 'make vpn-bypass-docker'."
    else
        echo "      ✓ Маршрут корректен (напрямую в LAN мимо VPN)."
    fi

    # [2] Проверка ICMP Ping
    echo "[2/3] Проверка ICMP Ping:"
    if ping -c 1 -W 2 "$host" > /dev/null 2>&1; then
        echo "      ✓ Ping успешен (устройство отвечает на ICMP)."
    else
        echo "      ⚠️  Ping не прошёл (устройство выключено, другой IP или ICMP заблокирован)."
    fi

    # [3] Проверка Moonraker API
    echo "[3/3] Проверка Moonraker API (http://${host}/server/info):"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "http://${host}/server/info" 2> /dev/null) || http_code="000"
    if [ "$http_code" = "200" ]; then
        echo "      ✓ Moonraker API доступен! (HTTP 200 OK)"
    elif [ "$http_code" = "000" ] || [ -z "$http_code" ]; then
        echo "      ⚠️  Таймаут подключения (трафик уходит в VPN tun0 либо принтер не отвечает)."
    else
        echo "      ℹ️  Сервер ответил с кодом HTTP ${http_code}"
    fi
done

echo ""
echo "======================================================================"
echo "Диагностика завершена."
echo "======================================================================"
