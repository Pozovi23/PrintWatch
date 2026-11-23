pipeline {
    agent any

    environment {
        UV_LINK_MODE = 'copy'
        DOCKER_BUILDKIT = '0'
        COMPOSE_DOCKER_CLI_BUILD = '0'
    }

    stages {
        stage('Validate Docker Compose') {
            steps {
                sh '''
                    cp -n alertmanager/alertmanager.yml.example alertmanager/alertmanager.yml || true
                    cp -n config/printers.yaml.example config/printers.yaml || true
                    docker compose config --quiet
                    echo "Docker Compose specification is valid."
                '''
            }
        }

        stage('Build Docker Images') {
            steps {
                sh 'docker compose build printer-exporter camera-proxy'
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -v "$(pwd):/workspace:ro" \
                        -w /workspace \
                        -e PYTHONPATH="services/printer-exporter" \
                        -e UV_PROJECT_ENVIRONMENT="/tmp/venv" \
                        -e UV_LINK_MODE="copy" \
                        ghcr.io/astral-sh/uv:python3.11-bookworm \
                        sh -c "uv sync --all-packages && uv run pytest -v -o cache_dir=/tmp/.pytest_cache -m 'not live' services/printer-exporter/tests"
                '''
            }
        }

        stage('Live Hardware Check') {
            steps {
                sh '''
                    docker run --rm --network host \
                        -v "$(pwd):/workspace:ro" \
                        -w /workspace \
                        -e PYTHONPATH="services/printer-exporter" \
                        -e UV_PROJECT_ENVIRONMENT="/tmp/venv" \
                        -e UV_LINK_MODE="copy" \
                        ghcr.io/astral-sh/uv:python3.11-bookworm \
                        sh -c "uv sync --all-packages && uv run pytest -v -o cache_dir=/tmp/.pytest_cache -m live services/printer-exporter/tests" || true
                '''
            }
        }
    }

    post {
        always {
            sh 'docker compose down --remove-orphans 2>/dev/null || true'
        }
        success {
            echo 'PrintWatch pipeline executed successfully in Jenkins.'
        }
        failure {
            echo 'PrintWatch pipeline failed.'
        }
    }
}
