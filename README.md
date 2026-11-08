# PrintWatch: Стенд мониторинга 3D-принтеров на базе klipper

Стенд комплексного мониторинга 3D-принтеров на базе **Docker, Prometheus, Grafana и Python**.

Стенд спроектирован с учётом работы в сложной сетевой среде: он корректно работает на хосте, где периодически включается/выключается VPN, не разрывая связь контейнеров с домашней LAN-сетью. Стенд предназначен для принтеров под управлением **Klipper** с веб-интерфейсами **Fluidd** и **Mainsail**, взаимодействующих через **Moonraker**.

## Запуск

### Создаём .env и настраиваем под себя

```bash
cp .env.example .env
```

### Создаём config/printers.yaml и настраиваем под себя

```bash
cp config/printers.yaml.example config/printers.yaml
```

### Настройка исключений в VPN-клиентах

В TUN-режиме VPN-клиент добавляет правило, по которому весь трафик по умолчанию сначала уходит в tun0. Это правило срабатывает раньше обычных маршрутов, поэтому трафик к локальной сети и Docker-подсетям тоже попадает в VPN. VPN-сервер отбрасывает приватные адреса, и запросы к принтеру или контейнерам падают по таймауту.

Чтобы исправить, выполните:

```bash
make vpn-bypass-docker
```

Для проверки работоспособности:

```bash
make check-printer
```

## Разработка

### Установка uv

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
# Перезапустить терминал (или ввести одну из команд, которые предложит установщик)
uv venv --python 3.11
source .venv/bin/activate
```

### Установка pre-commit

```bash
make pre-commit-install
```

### Запуск pre-commit

```bash
make pre-commit
```

### Тестирование экспортёра

#### Модульные тесты (Unit tests с моками)

Запуск набора тестов в изоляции (без физического принтера):

```bash
make test
# или напрямую:
PYTHONPATH="" uv run pytest -v -m "not live" services/printer-exporter/tests
```

*Проверяются сценарии:*

- Успешный сбор телеметрии Moonraker (температуры сопла/стола, статус печати, расчет времени).
- Обработка сетевого таймаута (`timeout`), ошибок Moonraker (HTTP 500 / 5xx) и повреждённого JSON.
- Аварийные состояния Klippy (`shutdown` / `disconnected`).
- Регистрация и корректное обновление метрик Prometheus (`MultiPrinterCollector`).
- Параллельный сбор телеметрии с N принтеров.

#### Интеграционные тесты живых принтеров

Для проверки подключения к физическому оборудованию из `config/printers.yaml`:

```bash
make test-live
```

### Тестирование прокси веб-камер (Camera Proxy)

Локальный запуск сервиса трансляции видеопотоков:

```bash
uv run uvicorn app:app --app-dir services/camera-proxy --port 8080
```

*Проверка эндпоинтов:*

- **Проверка здоровья (Healthcheck):**
  ```bash
  curl http://localhost:8080/healthz
  ```
- **Список обнаруженных камер (из `config/printers.yaml`):**
  ```bash
  curl http://localhost:8080/camera/list
  ```
- **Прямой JPEG-снапшот с камеры принтера:**
  ```bash
  curl -I http://localhost:8080/camera/snapshot/printer-1
  ```
- **Веб-витрина со стримами в реальном времени:**
  Открыть в браузере `http://localhost:8080/camera` для просмотра живого MJPEG-видеопотока.
