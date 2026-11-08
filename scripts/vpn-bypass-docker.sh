#!/usr/bin/env bash
# ==============================================================================
# vpn-bypass-docker.sh
#
# Назначение:
# Автоматическое восстановление прямой маршрутизации между хостом,
# Docker-контейнерами и принтерами из config/printers.yaml
# при включённом VPN.
#
# Единый источник конфигурации принтеров: config/printers.yaml
# ==============================================================================

set -euo pipefail

RED='\033[031m'
GREEN='\033[032m'
YELLOW='\033[1;33m'
BLUE='\033[034m'
CYAN='\033[036m'
NC='\033[0m' # No Color

# 1. Проверка прав суперпользователя
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Внимание: скрипт требует прав суперпользователя. Перезапуск через sudo...${NC}"
    exec sudo "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
YAML_FILE="${PROJECT_ROOT}/config/printers.yaml"

if [ ! -f "$YAML_FILE" ]; then
    echo -e "${RED}❌ Ошибка: Файл конфигурации ${YAML_FILE} не найден!${NC}" >&2
    echo -e "${YELLOW}   Создайте его на основе примера:${NC}" >&2
    echo -e "   cp config/printers.yaml.example config/printers.yaml" >&2
    exit 1
fi

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}==> [VPN Bypass] Настройка обхода VPN для принтеров из printers.yaml  ${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo -e "Файл конфигурации: ${CYAN}${YAML_FILE}${NC}"

add_ip_rule_if_missing() {
    local target="$1"
    local prio="$2"
    if ip rule show | grep -E "to ${target}(/32)?.*lookup main" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Правило для ${target} уже существует"
    else
        echo -e "  ${YELLOW}+${NC} Добавление: ip rule add to ${target} lookup main priority ${prio}"
        ip rule add to "${target}" lookup main priority "${prio}"
    fi
}

# 2. Добавляем базовые локальные подсети (LAN + Docker)
echo -e "\n${CYAN}--- [1/3] Добавление базовых подсетей (LAN & Docker) ---${NC}"
add_ip_rule_if_missing "192.168.0.0/16" 100
add_ip_rule_if_missing "172.16.0.0/12" 100
add_ip_rule_if_missing "10.0.0.0/8" 100

# 3. Парсинг принтеров строго из config/printers.yaml
echo -e "\n${CYAN}--- [2/3] Чтение принтеров из config/printers.yaml ---${NC}"

declare -A PRINTERS_MAP=()

if [ -f "$YAML_FILE" ]; then
    current_name=""
    while IFS= read -r line; do
        # Поиск имени принтера: - name: "printer-1"
        if [[ $line =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*[\"\']?([^\"\'[:space:]]+) ]]; then
            current_name="${BASH_REMATCH[1]}"
        elif [[ $line =~ ^[[:space:]]*name:[[:space:]]*[\"\']?([^\"\'[:space:]]+) ]]; then
            current_name="${BASH_REMATCH[1]}"
        fi

        # Поиск хоста: host: "http://192.168.0.xxx"
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
    echo -e "${RED}❌ Ошибка: В ${YAML_FILE} не найдено ни одного принтера с указанным host!${NC}" >&2
    exit 1
fi

for name in "${!PRINTERS_MAP[@]}"; do
    host="${PRINTERS_MAP[$name]}"
    target_ip="$host"

    # Если host не IPv4, пробуем разрешить DNS
    if ! [[ $host =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        resolved_ip=$(getent ahostsv4 "$host" 2> /dev/null | awk '{print $1}' | head -n1 || true)
        if [ -n "$resolved_ip" ]; then
            target_ip="$resolved_ip"
            echo -e "  [${name}] Разрешён хост ${host} -> ${target_ip}"
        fi
    fi

    echo -e "  Настройка принтера ${CYAN}${name}${NC} (${target_ip}):"
    add_ip_rule_if_missing "${target_ip}/32" 100
done

# 4. Синхронизация с таблицей VPN 2022 (если активна)
if ip route show table 2022 > /dev/null 2>&1; then
    if ip link show docker0 > /dev/null 2>&1; then
        if ! ip route show table 2022 | grep -q "172.16.0.0/12"; then
            echo -e "\n${CYAN}--- Синхронизация Docker с таблицей VPN 2022 ---${NC}"
            echo -e "  ${YELLOW}+${NC} Добавление маршрута 172.16.0.0/12 в таблицу VPN 2022"
            ip route add 172.16.0.0/12 dev docker0 table 2022 2> /dev/null || true
        fi
    fi
fi

# 5. Проверка фактических маршрутов
echo -e "\n${CYAN}--- [3/3] Проверка маршрутов до всех принтеров ---${NC}"
ALL_OK=true

for name in "${!PRINTERS_MAP[@]}"; do
    host="${PRINTERS_MAP[$name]}"
    target_ip="$host"
    if ! [[ $host =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        resolved_ip=$(getent ahostsv4 "$host" 2> /dev/null | awk '{print $1}' | head -n1 || true)
        [ -n "$resolved_ip" ] && target_ip="$resolved_ip"
    fi

    route_out=$(ip route get "$target_ip" 2>&1 || true)

    if echo "$route_out" | grep -q "dev tun"; then
        echo -e "  ${RED}✗ [${name}] ${target_ip}${NC} -> ${route_out}"
        echo -e "    ${RED}ОШИБКА: Трафик идёт в VPN-туннель (tun)!${NC}"
        ALL_OK=false
    else
        dev_name=$(echo "$route_out" | grep -oE 'dev [^ ]+' | awk '{print $2}' || echo "lan")
        echo -e "  ${GREEN}✓ [${name}] ${target_ip}${NC} -> идёт напрямую через интерфейс ${GREEN}${dev_name}${NC}"
    fi
done

echo -e "\n${BLUE}======================================================================${NC}"
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}✓ ВСЕ ПРИНТЕРЫ ИЗ PRINTERS.YAML ДОСТУПНЫ НАПРЯМУЮ В ОБХОД VPN!${NC}"
else
    echo -e "${RED}⚠️  ВНИМАНИЕ: Некоторые принтеры всё ещё перехватываются VPN!${NC}"
    echo -e "${YELLOW}Рекомендация: проверьте настройки Hiddify/Happ (Bypass LAN / Direct).${NC}"
fi
echo -e "${BLUE}======================================================================${NC}"
