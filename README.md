# PrintWatch: Стенд мониторинга парка 3D-принтеров на базе Klipper

Стенд комплексного мониторинга парка 3D-принтеров на базе **Docker Compose, Prometheus, Grafana, Alertmanager и Python**.

Стенд спроектирован с учётом эксплуатации в реальной сетевой среде: он стабильно работает на хосте, где периодически включается и выключается VPN, исключая разрыв связи контейнеров со службами локальной домашней сети. Система ориентирована на принтеры под управлением **Klipper** с веб-интерфейсами **Fluidd** и **Mainsail**, взаимодействующими через API-шлюз **Moonraker**.

______________________________________________________________________

## Быстрый запуск

### 1. Подготовка конфигурации

Скопируйте шаблоны переменных окружения, конфигурации принтеров и алертинга:

```bash
cp .env.example .env
cp config/printers.yaml.example config/printers.yaml
cp alertmanager/alertmanager.yml.example alertmanager/alertmanager.yml
```

- Отредактируйте `.env`: логин и пароль администратора Grafana.
- Отредактируйте `config/printers.yaml`: укажите IP-адреса и URL веб-камер ваших принтеров.
- Отредактируйте `alertmanager/alertmanager.yml`: укажите `bot_token` (от @BotFather) и `chat_id` (от @userinfobot) для отправки уведомлений в Telegram.

Пример `config/printers.yaml`:

```yaml
settings:
  poll_interval: 5.0

printers:
  - name: "printer-1"
    host: "http://192.168.0.198"
    api_key: ""
    camera_url: "http://192.168.0.198/webcam/?action=stream"
    camera_snapshot_url: "http://192.168.0.198/webcam/?action=snapshot"

  - name: "printer-2"
    host: "http://192.168.0.200"
    api_key: ""
    camera_url: "http://192.168.0.200/webcam/?action=stream"
    camera_snapshot_url: "http://192.168.0.200/webcam/?action=snapshot"
```

### 2. Настройка сетевого обхода VPN (при наличии)

Если на хосте активен VPN-клиент в TUN-режиме, он по умолчанию перехватывает трафик к локальной сети и Docker-мостам. Для добавления правил маршрутизации в обход туннеля выполните:

```bash
make vpn-bypass-docker
```

Для проверки сетевой доступности всех принтеров из списка:

```bash
make check-printer
```

### 3. Запуск сервисов мониторинга

Запустите весь стек контейнеров в фоновом режиме:

```bash
make up
```

или напрямую через Docker Compose:

```bash
docker compose up -d
```

Проверьте статус и здоровье всех контейнеров:

```bash
make status
```

______________________________________________________________________

## Доступ к веб-интерфейсам и сервисам

После успешного запуска доступны следующие точки входа:

| Сервис           | Адрес                          | Описание                                                         |
| :--------------- | :----------------------------- | :--------------------------------------------------------------- |
| **Grafana**      | `http://localhost:3000`        | Дашборды мониторинга принтеров, вкладки принтеров, видеоснапшоты |
| **Camera Proxy** | `http://localhost:8080/camera` | Веб-витрина живых MJPEG-видеопотоков всех принтеров              |
| **Prometheus**   | `http://localhost:9090`        | Интерфейс метрик PromQL, таргеты и состояние алертов             |
| **Alertmanager** | `http://localhost:9093`        | Управление алертами, дедупликация и подавление                   |
| **Jenkins**      | `http://localhost:8088`        | Локальный CI/CD сервер автоматизации (опционально)               |

### Возможности дашборда Grafana

- **Вкладки для принтеров**: навигационная панель в верхней части позволяет переключаться между отдельными принтерами (`[printer-1]`, `[printer-2]`) или сводным представлением (`[All Printers]`).
- **Просмотр веб-камеры**: полноформатный стрим с веб-камеры.

______________________________________________________________________

## Эксплуатация и обслуживание

Все регулярные сценарии обслуживания автоматизированы через команды `Makefile`:

### Управление контейнерами

- **Запуск всех сервисов**:
  ```bash
  make up
  ```
- **Остановка всех контейнеров**:
  ```bash
  make down
  ```
- **Перезапуск всех сервисов**:
  ```bash
  make restart
  ```
- **Просмотр логов в реальном времени**:
  ```bash
  make logs
  ```
- **Просмотр статуса контейнеров**:
  ```bash
  make status
  ```
- **Пересборка образов (exporter, camera-proxy)**:
  ```bash
  make build
  ```

### Добавление новых принтеров

При добавлении нового принтера в `config/printers.yaml`:

```bash
make add-printer
```

Команда перезапустит микросервисы `printer-exporter` и `camera-proxy`. Новый принтер автоматически появится в сборе метрик, на витрине камер и на дашборде Grafana.

### Горячая перезагрузка Prometheus

Если вы изменили правила алертинга в `alerts/alerts.yml` или конфигурацию в `prometheus/prometheus.yml`, перезагрузите их без остановки контейнера:

```bash
make reload-prometheus
```

______________________________________________________________________

## Разработка и локальное тестирование

### Установка зависимостей через `uv`

Проект использует современный менеджер пакетов [uv](https://github.com/astral-sh/uv):

```bash
# Установка uv (если не установлен)
wget -qO- https://astral.sh/uv/install.sh | sh

# Создание виртуального окружения и установка зависимостей
make sync
```

### Pre-commit проверки

Для поддержания качества кода в проекте настроен набор проверок (Ruff, Pyright, Hadolint, ShellCheck, shfmt, Yamllint):

```bash
# Регистрация git-хуков в локальном репозитории
make pre-commit-install

# Ручной запуск всех проверок по всем файлам
make pre-commit
```

### Запуск тестов

- **Модульные тесты экспортёра (с моками, без внешних принтеров)**:
  ```bash
  make test
  ```
- **Интеграционные тесты (проверка подключения к реальным принтерам)**:
  ```bash
  make test-live
  ```
- **Запуск всех доступных тестов**:
  ```bash
  make test-all
  ```

### Ручной запуск сервисов вне Docker

- **Запуск экспортёра локально**:
  ```bash
  PYTHONPATH="services/printer-exporter" uv run python -m exporter.main
  ```
- **Запуск прокси веб-камер локально**:
  ```bash
  uv run uvicorn app:app --app-dir services/camera-proxy --port 8080
  ```

______________________________________________________________________

## Непрерывная интеграция (GitHub Actions CI)

В репозитории настроен автоматический пайплайн CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)), выполняющий на каждом pull request и коммите:

1. **Pre-commit Hooks**: валидация синтаксиса, линтинг Python (Ruff, Pyright), Dockerfile (Hadolint), Shell-скриптов (ShellCheck, shfmt) и YAML-файлов.
1. **Unit Tests**: выполнение модульных тестов с моками сетевых ответов через `uv run pytest -m "not live"`.
1. **Docker Build Check**: сборка образов сервисов с помощью Docker Buildx и валидация спецификации `docker compose config`.

______________________________________________________________________

## Локальный сервер автоматизации (Jenkins CI/CD)

В дополнение к облачному GitHub Actions в проекте предусмотрена интеграция с локальным сервером **Jenkins**.

В отличие от облачных раннеров, локальный Jenkins запущен внутри домашней сети и имеет доступ к физическому оборудованию (принтерам), позволяя автоматически выполнять интеграционные тесты (`make test-live`) и локальный деплой стека.

Развертывание выполняется по официальному руководству Jenkins (схема **Docker-in-Docker**) с адаптацией веб-порта под `8088` (для исключения конфликта с `camera-proxy`) и флагом автоперезапуска `--restart unless-stopped`.

### Быстрый запуск через Makefile

Все шаги автоматизированы с помощью команд `make`:

```bash
# 1. Сборка кастомного образа Jenkins с Docker CLI
make jenkins-build

# 2. Запуск контейнеров (сеть, dind и jenkins на порту 8088)
make jenkins-up

# 3. Получение пароля администратора для первого входа
make jenkins-password

# 4. Просмотр логов в реальном времени
make jenkins-logs

# 5. Остановка контейнеров
make jenkins-down
```

______________________________________________________________________

### Ручной запуск через Docker CLI (Пошагово)

Если вы хотите выполнить развертывание вручную по шагам:

#### 1. Создание сети Docker

```bash
docker network create jenkins
```

#### 2. Запуск демона Docker-in-Docker (`jenkins-docker`)

```bash
docker run \
	--name jenkins-docker \
	--restart unless-stopped \
	--detach \
	--privileged \
	--network jenkins \
	--network-alias docker \
	--sysctl net.ipv6.conf.all.disable_ipv6=1 \
	--env DOCKER_TLS_CERTDIR=/certs \
	--volume jenkins-docker-certs:/certs/client \
	--volume jenkins-data:/var/jenkins_home \
	--publish 2376:2376 \
	docker:dind \
	--storage-driver overlay2
```

#### 3. Сборка кастомного образа Jenkins с Docker CLI

В корне репозитория подготовлен [Dockerfile.jenkins](Dockerfile.jenkins) (на базе `jenkins/jenkins:2.580.2-jdk21` из официального руководства). Соберите образ:

```bash
docker build -t myjenkins-blueocean:2.580.2-1 -f Dockerfile.jenkins .
```

#### 4. Запуск сервера Jenkins (`jenkins-blueocean`)

```bash
docker run \
	--name jenkins-blueocean \
	--restart unless-stopped \
	--detach \
	--network jenkins \
	--env DOCKER_HOST=tcp://docker:2376 \
	--env DOCKER_CERT_PATH=/certs/client \
	--env DOCKER_TLS_VERIFY=1 \
	--env JAVA_OPTS="-Djava.net.preferIPv4Stack=true" \
	--publish 8088:8080 \
	--publish 50000:50000 \
	--volume jenkins-data:/var/jenkins_home \
	--volume jenkins-docker-certs:/certs/client:ro \
	myjenkins-blueocean:2.580.2-1
```

______________________________________________________________________

### Первичная настройка и доступ

1. Откройте в браузере: `http://localhost:8088`
1. Получите первичный пароль администратора (`make jenkins-password` или `docker exec jenkins-blueocean cat /var/jenkins_home/secrets/initialAdminPassword`).
1. Выберите **Install suggested plugins** и создайте учетную запись администратора.
1. В корне репозитория доступен готовый [Jenkinsfile](Jenkinsfile), описывающий пайплайн проверки качества кода, модульных тестов, интеграционных тестов с принтерами и валидации спецификации Docker Compose.
