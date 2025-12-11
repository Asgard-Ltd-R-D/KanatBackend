pipeline {
    agent any

    environment {
        DOCKER_BUILDKIT = "1"
        GH_TOKEN = credentials('GITHUB_TOKEN')   // MUST be a secret text credential
    }

    options {
        skipStagesAfterUnstable()
    }

    stages {

        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Install GitHub CLI') {
            steps {
                sh """
                sudo apt-get update
                sudo apt-get install -y curl git apt-transport-https gnupg

                curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
                    sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg

                sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg

                echo "deb [arch=\$(dpkg --print-architecture) \
                    signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
                    https://cli.github.com/packages stable main" | \
                    sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

                sudo apt-get update
                sudo apt-get install -y gh
                gh --version
                """
            }
        }

        stage('Matrix Build') {
            parallel {
                stage('Build x64') {
                    steps { script { runBuild("x64") } }
                }
                stage('Build arm64') {
                    steps { script { runBuild("arm64") } }
                }
            }
        }

        stage('Collect Installers') {
            steps {
                sh """
                mkdir -p collected_installers
                cp -R installers/* collected_installers/ || true
                ls -R collected_installers
                """
            }
        }

        stage('Determine Release Type') {
            steps {
                script {
                    def branch = env.BRANCH_NAME

                    if (branch == "main" || branch == "master") {
                        env.REL_TYPE = "release"
                        env.PRERELEASE = "false"
                    }
                    else if (branch.startsWith("feature/") || branch.startsWith("fix/")) {
                        env.REL_TYPE = "pre-release"
                        env.PRERELEASE = "true"
                    }
                    else {
                        env.REL_TYPE = "unknown"
                        env.PRERELEASE = "true"
                    }

                    echo "Release type = ${env.REL_TYPE}"
                }
            }
        }

        stage('Publish GitHub Release') {
            when { expression { env.REL_TYPE != "unknown" } }

            steps {
                script {
                    def tag = "v${env.BUILD_NUMBER}"
                    def title = "Kanat Build ${env.BUILD_NUMBER} - ${env.BRANCH_NAME}"

                    // Convert Jenkins SCM URL → owner/repo
                    def repo = env.GIT_URL
                        .replace("https://github.com/", "")
                        .replace(".git", "")

                    echo "Publishing GitHub release to: ${repo}"
                    echo "Using tag: ${tag}"

                    sh """
                    export GH_TOKEN="${GH_TOKEN}"

                    gh auth token

                    gh release create ${tag} \
                        --repo "${repo}" \
                        --title "${title}" \
                        --notes "Automated Jenkins release" \
                        ${env.PRERELEASE == 'true' ? '--prerelease' : ''} \
                        collected_installers/*
                    """
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: "collected_installers/**", fingerprint: true
        }
    }
}

/* ================================
   SHARED FUNCTION: runBuild(arch)
   ================================ */
def runBuild(String arch) {
    echo "🏗️ Building installers for architecture: ${arch}"

    sh """#!/bin/bash
    set -e

    sudo apt-get update
    sudo apt-get install -y python3-tk tk-dev

    docker buildx create --use --name kanatbuilder || true
    docker buildx inspect --bootstrap

    export DOCKER_DEFAULT_PLATFORM=${arch == 'x64' ? 'linux/amd64' : 'linux/arm64'}

    echo "🐳 Building local dev/prod images..."
    docker compose -f docker-compose.dev.yml build
    docker compose -f docker-compose.prod.yml build

    mkdir -p installers/${arch}

    # Use space-separated list instead of bash arrays
    if [ "${arch}" = "x64" ]; then
        platforms="linux-x64 win-x64 osx-x64"
    else
        platforms="linux-arm64 win-arm64 osx-arm64"
    fi

    for platform in \$platforms; do
        outDir="installers/\${platform}"
        echo "🔧 Building installer for \$platform..."

        rm -rf artifacts
        mkdir -p artifacts
        mkdir -p "\$outDir"

        bash ./build_artifacts.sh "\$platform"

        cp -R artifacts/* "\$outDir/"
    done
    """
}
