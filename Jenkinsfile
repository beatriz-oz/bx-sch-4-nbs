// Back end pipeline (run on demand from the local Jenkins: see jenkins/README.md).
// Each build gets its own throwaway MySQL and Mailpit, removed at the end whatever happens.
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 40, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        string(name: 'BRANCH', defaultValue: 'develop', description: 'Branch to check: develop, uat or main.')
        booleanParam(name: 'DEPLOY_BENCH', defaultValue: false, description: 'Publish to the bench after the checks (not available yet).')
    }

    environment {
        // One name per build, so two builds never share a database.
        MYSQL = "nbs-ci-mysql-${BUILD_NUMBER}"
        MAILPIT = "nbs-ci-mail-${BUILD_NUMBER}"
        // Caches in the Jenkins volume: the next build does not download everything again.
        UV_CACHE_DIR = "${JENKINS_HOME}/cache/uv"
        UV_PYTHON_INSTALL_DIR = "${JENKINS_HOME}/cache/uv-python"
        PYTHONIOENCODING = 'utf-8'
    }

    stages {
        stage('Install') {
            steps {
                sh 'uv sync --frozen'
            }
        }

        stage('Lint and types') {
            steps {
                sh '''
                    uv run ruff check src
                    uv run ruff format --check src
                    uv run ty check src
                '''
            }
        }

        stage('MySQL and Mailpit') {
            steps {
                // The same versions as on the development machine.
                sh '''
                    docker run -d --rm --name "$MYSQL" --network nbs-ci \
                        -e MYSQL_ROOT_PASSWORD=ci -e MYSQL_DATABASE=nbs mysql:8.0
                    docker run -d --rm --name "$MAILPIT" --network nbs-ci axllent/mailpit
                    # Ready when it answers over TCP (during its first start it only listens on a socket).
                    for attempt in $(seq 1 60); do
                        if docker exec "$MYSQL" mysql -h 127.0.0.1 -uroot -pci -e 'SELECT 1' nbs >/dev/null 2>&1; then
                            exit 0
                        fi
                        sleep 2
                    done
                    echo 'MySQL did not start in 2 minutes.'
                    exit 1
                '''
            }
        }

        stage('Configuration') {
            steps {
                // Fresh secrets for every build: nothing real ever reaches Jenkins.
                sh '''
                    cat > .env <<EOF
DATABASE_URL=mysql+pymysql://root:ci@${MYSQL}:3306/nbs
ENCRYPTION_KEY=$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
HASH_PEPPER=$(uv run python -c 'import secrets; print(secrets.token_hex(32))')
JWT_SECRET_KEY=$(uv run python -c 'import secrets; print(secrets.token_hex(32))')
SMTP_HOST=${MAILPIT}
SMTP_PORT=1025
EOF
                '''
            }
        }

        stage('Migrations') {
            steps {
                // Up, one step down and up again, then no difference between the models and the database.
                sh '''
                    uv run alembic upgrade head
                    uv run alembic downgrade -1
                    uv run alembic upgrade head
                    uv run alembic check
                '''
            }
        }

        stage('Test data') {
            steps {
                sh '''
                    uv run python -m bx_sch_4_nbs.scripts.seed_ci
                    uv run python -m bx_sch_4_nbs.scripts.seed_demo
                '''
            }
        }

        stage('Tests') {
            steps {
                sh 'uv run --with httpx python -m bx_sch_4_nbs.scripts.run_try_scripts'
            }
        }

        stage('Deploy to bench') {
            when { expression { params.DEPLOY_BENCH } }
            steps {
                // Ready for when the Docker deploy exists; until then it stops here on purpose.
                error('The bench deploy is not set up yet: it comes with the Docker deploy.')
            }
        }
    }

    post {
        always {
            sh '''
                docker rm -f "$MYSQL" "$MAILPIT" >/dev/null 2>&1 || true
                rm -f .env
            '''
        }
    }
}
