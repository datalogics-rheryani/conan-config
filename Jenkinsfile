def ENV_LOC = ''

pipeline {
    options {
        buildDiscarder(logRotator(artifactDaysToKeepStr: '4', artifactNumToKeepStr: '10', daysToKeepStr: '7', numToKeepStr: '10'))
        timeout(time: 1, unit: 'HOURS')
    }
    agent {
        label 'linux-conan-config'
    }
    libraries {
        lib('jenkins-shared-libraries')
    }
    environment {
        // Outside the checkout, because `conan config install .` copies the checkout.
        CONAN_HOME = "${WORKSPACE_TMP}/conan2"
    }
    stages {
        stage('Setup') {
            steps {
                script {
                    ENV_LOC = mkenv()
                }
            }
        }
        stage('Pre-commit checks') {
            when {
                changeRequest()
            }
            environment {
                // remotes.json is a protected path in .pr-classify.yaml, so a human reviews any reordering.
                ALLOW_REMOTE_REORDER = '1'
            }
            steps {
                preCommitCheck("${ENV_LOC}")
            }
        }
        stage('Render profiles') {
            steps {
                sh """. ${ENV_LOC}/bin/activate
                    rm -rf "\$CONAN_HOME"
                    conan config install .
                    python tools/render_profiles.py
                    """
            }
        }
    }
    post {
        success {
            script {
                // Ask the central gatekeeper to review passing PRs without affecting this build.
                if (env.CHANGE_ID) {
                    try {
                        build job: '/pr-gatekeeper', wait: false,
                              parameters: [string(name: 'REPO', value: 'datalogics/conan-config'),
                                           string(name: 'PR', value: env.CHANGE_ID)]
                    } catch (err) {
                        echo "Could not start the PR gatekeeper: ${err}"
                    }
                }
            }
        }
    }
}
