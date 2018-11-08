/*
 * Required plugins:
 * Blue Ocean / all the 'typical' plugins for GitHub multi-branch pipelines
 * GitHub Branch Source Plugin
 * SCM Filter Branch PR Plugin
 * Pipeline GitHub Notify Step Plugin
 * Pipeline: GitHub Plugin
 * Kubernetes Plugin
 */

// Some constants...

// Name for auto-generated openshift pod
podLabel = "aiops-test-${UUID.randomUUID().toString()}"

// Status contexts for Github
unitTestContext = "continuous-integration/jenkins/unittest"
pipInstallContext = "continuous-integration/jenkins/pipinstall"
coverageContext = "continuous-integration/jenkins/coverage"

// Local user exec path inside the py container, apps installed with 'pip3 install --user' live here
userPath = '/home/jenkins/.local/bin'

// Error msgs for pip3 install stage
lockErrorRegex = /.*Your Pipfile.lock \(\S+\) is out of date. Expected: \(\S+\).*/
lockError = "\n* `Pipfile.lock` is out of sync. Run '`pipenv lock`' and commit the changes."
installError = "\n* '`pipenv install`' has failed."

// Code coverage failure threshold
codecovThreshold = 0


def resetContexts() {
    notify(unitTestContext, "PENDING")
    notify(pipInstallContext, "PENDING")
    notify(coverageContext, "PENDING")
}


node {
    milestone()

    // trick to cancel previous builds, see https://issues.jenkins-ci.org/browse/JENKINS-40936
    // avoids quick PR updates triggering too many concurrent tests
    for (int i = 0; i < (env.BUILD_NUMBER as int); i++) {
        milestone()
    }

    stage ('Checkout') {
        scmVars = checkout scm
    }

    echo "env.CHANGE_ID:                  ${env.CHANGE_ID}"
    echo "env.BRANCH_NAME:                ${env.BRANCH_NAME}"
    echo "GIT_COMMIT:                     ${scmVars.GIT_COMMIT}"
    echo "GIT_PREVIOUS_SUCCESSFUL_COMMIT: ${scmVars.GIT_PREVIOUS_SUCCESSFUL_COMMIT}"
    echo "GIT_URL:                        ${scmVars.GIT_URL}"

    if (env.CHANGE_ID || (env.BRANCH_NAME == 'master' && scmVars.GIT_COMMIT != scmVars.GIT_PREVIOUS_SUCCESSFUL_COMMIT)) {
        // run lint and unit tests for any PR or upon new commits/merges to master
        resetContexts()
        runStages()
    } else {
        echo 'Skipped pipeline for this commit, not a PR or not a new commit on master.'
    }
}


def notify(String context, String status) {
    def targetUrl

    def buildUrl = env.BUILD_URL
    def jobNameSplit = JOB_NAME.tokenize('/') as String[]
    def projectName = jobNameSplit[0]
    def blueBuildUrl = buildUrl.replace("job/${projectName}", "blue/organizations/jenkins/${projectName}")
    blueBuildUrl = blueBuildUrl.replace("job/${env.BRANCH_NAME}", "detail/${env.BRANCH_NAME}")

    if (status == "PENDING") {
        // Always link to the fancy blue ocean UI while the job is running ...
        targetUrl = env.RUN_DISPLAY_URL
    } else {
        switch (context) {
            case unitTestContext:
                targetUrl =  "${blueBuildUrl}tests"
                break  
            case coverageContext:
                targetUrl = "${env.BUILD_URL}artifact/htmlcov/index.html"
                break
            default:
                targetUrl = env.RUN_DISPLAY_URL
                break
        }
    }

    try {
        githubNotify context: context, status: status, targetUrl: targetUrl
    } catch (err) {
        msg = err.getMessage()
        echo "Error notifying GitHub: ${msg}"
    }
}


def removePipfileComments() {
    try {
        for (comment in pullRequest.comments) {
            if (comment.body.contains("Pipfile violation")) {
                deleteComment(comment.id)
            }
        }
    } catch (err) {
        msg = err.getMessage()
        echo "Error removing Pipfile comments: ${msg}"
    }
}


def postPipfileComment(commitId, str) {
    def shortId = commitId.substring(0, 7)
    def body = "Commit `${shortId}` Pipfile violation\n${str}"
    try {
        pullRequest.comment(body)
    } catch (err) {
        msg = err.getMessage()
        echo "Error adding Pipfile comment: ${msg}"
    }
}


def runUnitTests() {
    try {
        sh "${userPath}/pipenv run python -m pytest --pylama --junitxml=junit.xml --cov=. --cov-report html -s -v"
        notify(unitTestContext, "SUCCESS")
    } catch (err) {
        echo err.getMessage()
        currentBuild.result = "UNSTABLE"
        notify(unitTestContext, "FAILURE")
    }

    junit 'junit.xml'
}


def checkCoverage() {
    def status = 99

    status = sh(
        script: "${userPath}/pipenv run coverage html --fail-under=${codecovThreshold} --skip-covered",
        returnStatus: true
    )

    archiveArtifacts 'htmlcov/*'

    if (status != 0) {
        currentBuild.result = "UNSTABLE"
        notify(coverageContext, "FAILURE")
    } else {
        notify(coverageContext, "SUCCESS")
    }
}


def runPipInstall(scmVars) {
    sh "pip3 install --user --no-warn-script-location pipenv"
    sh "${userPath}/pipenv run pip3 install --upgrade pip"

    // NOTE: Removing old comments won't work unless Pipeline Github Plugin >= v2.0
    removePipfileComments()

    // use --deploy to check if Pipfile and Pipfile.lock are in sync
    def cmdStatus = sh(
        script: "${userPath}/pipenv install --dev --deploy --verbose > pipenv_install_out.txt",
        returnStatus: true
    )

    def installFailed = false
    def errorMsg = ""
    if (cmdStatus != 0) { 
        if (readFile('pipenv_install_out.txt').trim() ==~ lockErrorRegex) {
            currentBuild.result = "UNSTABLE"
            errorMsg += lockError
            // try to install without the deploy flag to allow the other tests to run
            try {
                sh "${userPath}/pipenv install --dev --verbose"
            } catch (err) {
                // second try without --deploy failed too, fail this build.
                echo err.getMessage()
                installFailed = true
                errorMsg += installError
            }
        } else {
            // something else failed (not a lock error), fail this build.
            echo err.getMessage()
            installFailed = true
            errorMsg += installError
        }
    }

    if (errorMsg) {
        postPipfileComment(scmVars.GIT_COMMIT, errorMsg)
    }
    if (installFailed) {
        error("pipenv install has failed")
        notify(pipInstallContext, "FAILURE")
    } else {
        notify(pipInstallContext, "SUCCESS")
    }
}


def runStages() {
    // Fire up a pod on openshift with containers for the DB and the app
    podTemplate(label: podLabel, slaveConnectTimeout: 120, cloud: 'openshift', containers: [
        containerTemplate(
            name: 'jnlp',
            image: 'docker-registry.default.svc:5000/jenkins/jenkins-slave-base-centos7-python36',
            args: '${computer.jnlpmac} ${computer.name}',
            resourceRequestCpu: '200m',
            resourceLimitCpu: '1000m',
            resourceRequestMemory: '256Mi',
            resourceLimitMemory: '1Gi',
            envVars: [
                envVar(key: 'LC_ALL', value: 'en_US.utf-8'),
                envVar(key: 'LANG', value: 'en_US.utf-8'),
            ],
        ),
    ]) {
        node(podLabel) {
            // check out source again to get it in this node's workspace
            scmVars = checkout scm

            stage('Pip install') {
                runPipInstall(scmVars)
            }

            stage('UnitTest') {
                runUnitTests()
            }

            stage('Code coverage') {
                checkCoverage()
            }

            if (currentBuild.currentResult == 'SUCCESS') {
                if (env.BRANCH_NAME == 'master') {
                    // Stages to run specifically if master branch was updated
                }
            }
        }
    }
}

