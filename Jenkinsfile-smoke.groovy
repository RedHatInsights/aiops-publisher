/*
 * Required plugins:
 * Blue Ocean / all the 'typical' plugins for GitHub multi-branch pipelines
 * GitHub Branch Source Plugin
 * SCM Filter Branch PR Plugin
 * Pipeline GitHub Notify Step Plugin
 * Pipeline: GitHub Plugin
 * SSH Agent Plugin
 * Lockable Resources Plugin
 *
 * Configuration:
 * Discover branches:
 *   Strategy: Exclude branches that are also filed as PRs
 * Discover pull requests from forks:
 *   Strategy: Merging the pull request with the current target branch revision
 *   Trust: From users with Admin or Write permission
 * Discover pull requests from origin
 *   Strategy: Merging the pull request with the current target branch revision
 * Filter by name including PRs destined for this branch (with regular expression):
 *   Regular expression: .*
 * Clean before checkout
 * Clean after checkout
 * Check out to matching local branch
 *
 * Script whitelisting is needed for 'currentBuild.rawBuild' and 'currentBuild.rawBuild.getCause()'
 *
 * Configure projects in OpenShift, create lockable resources for them with label "smoke_test_projects"
 * Add Jenkins service account as admin on those projects
 *
 */

// Some constants...
jenkinsSvcAccount = "jenkins"
e2eSmokeContext = "continuous-integration/jenkins/e2e-smoke"
e2eDeployDir = 'e2e-deploy'
e2eDeployRepo = 'https://github.com/RedHatInsights/e2e-deploy.git'
e2eTestsDir = 'e2e-tests'
e2eTestsRepo = 'https://github.com/RedHatInsights/e2e-tests.git'
venvDir = "~/.venv"
ocdeployerBuilderPath = "aiops/aiops-publisher"
ocdeployerComponentPath = "aiops/aiops-publisher"
ocdeployerServiceSets = "aiops,platform"
pytestMarker = "aiops_smoke"
// Jenkins resource label configured as a 'lockable resource'
resourceLabel = "smoke_test_projects"


// Smoke tests are run via a GitHub comment trigger
properties([
    pipelineTriggers([
        issueCommentTrigger('.*smoke test please.*'),
    ])
])


@NonCPS
def triggeredByComment() {
    def cause = currentBuild.rawBuild.getCause(org.jenkinsci.plugins.pipeline.github.trigger.IssueCommentCause)
    if (cause) {
        return true
    } else {
        echo('Build skipped, not started by issue comment trigger')
        return false
    }
}


if (triggeredByComment()) {
    // Fire up a jnlp slave that uses the service account to auth with OpenShift
    podTemplate(
        label: pytestMarker,
        slaveConnectTimeout: 120,
        serviceAccount: jenkinsSvcAccount,
        cloud: 'openshift',
        containers: [
            containerTemplate(
                name: 'jnlp',
                image: 'docker-registry.default.svc:5000/jenkins/jenkins-slave-base-centos7-python36',
                args: '${computer.jnlpmac} ${computer.name}',
                resourceRequestCpu: '200m',
                resourceLimitCpu: '500m',
                resourceRequestMemory: '256Mi',
                resourceLimitMemory: '650Mi',
                envVars: [
                    envVar(key: 'LC_ALL', value: 'en_US.utf-8'),
                    envVar(key: 'LANG', value: 'en_US.utf-8'),
                ],
            ),
        ]
    ) {
        node(pytestMarker) {
            runPipeline()
        }
    }
}


def runPipeline() {
    milestone()

    // trick to cancel previous builds, see https://issues.jenkins-ci.org/browse/JENKINS-40936
    // avoids quick PR updates triggering too many concurrent tests
    for (int i = 0; i < (env.BUILD_NUMBER as int); i++) {
        milestone()
    }

    currentBuild.result = "SUCCESS"

    notify(e2eSmokeContext, "PENDING")
    try {
        lock(label: resourceLabel, quantity: 1, variable: "PROJECT") {
            runSmokeTest(env.PROJECT)
        }
    } catch (err) {
        currentBuild.result = "UNSTABLE"
    }

    // 'junit' archival would have set the build status to a failure if any tests failed...
    if (currentBuild.result != "SUCCESS") {
        notify(e2eSmokeContext, "FAILURE")
    } else {
        notify(e2eSmokeContext, "SUCCESS")
    }
}


def checkoutRepo(targetDir, repoUrl, branch = 'master') {
    /* Helper to check out a github repo */
    checkout([
        $class: 'GitSCM',
        branches: [[name: branch]],
        doGenerateSubmoduleConfigurations: false,
        extensions: [
            [$class: 'RelativeTargetDirectory', relativeTargetDir: targetDir],
        ],
        submoduleCfg: [],
        userRemoteConfigs: [
            [credentialsId: 'github', url: repoUrl]
        ]
    ])
}


def notify(String context, String status) {
    /* Helper to update a github status context on a PR */
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
        targetUrl = "${blueBuildUrl}tests"
    }

    try {
        githubNotify context: context, status: status, targetUrl: targetUrl
    } catch (err) {
        msg = err.getMessage()
        echo "Error notifying GitHub: ${msg}"
    }
}



def deployEnvironment(refspec, project) {
    stage("Deploy test environment") {
        dir(e2eDeployDir) {
            // First, deploy the builder for only this app to build the PR image in this project
            sh "echo \"${ocdeployerBuilderPath}:\" > env.yml"
            sh "echo \"  SOURCE_REPOSITORY_REF: ${refspec}\" >> env.yml"
            sh  "${venvDir}/bin/ocdeployer --pick ${ocdeployerBuilderPath} --template-dir buildfactory -e env.yml --secrets-src-project secrets --no-confirm ${project}"

            // Now deploy the full env, set the image for this app to be pulled from this local project instead of buildfactory
            sh "echo \"${ocdeployerComponentPath}:\" > env.yml"
            sh "echo \"  IMAGE_NAMESPACE: ${project}\" >> env.yml"   
            sh  "${venvDir}/bin/ocdeployer -s ${ocdeployerServiceSets} -e env.yml --secrets-src-project secrets --no-confirm ${project}"
        }
    }
}



def collectLogs(project) {
    stage("Collect logs") {
        try {
            sh "oc project ${project}"
            sh '''
                mkdir -p applogs/
                PODS=$(oc get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\\n"}')
                for pod in $PODS; do
                    CONTAINERS=$(oc get pod $pod -o jsonpath='{range .spec.containers[*]}{.name}{"\\n"}')
                    for container in $CONTAINERS; do
                        oc logs $pod -c $container > applogs/${pod}_${container}.log || echo "get logs: ${pod}_${container} failed."
                        echo "Saved logs for $pod container $container"
                    done
                done
            '''
            sh "oc export all -o yaml > oc_export_all.yaml"
            archiveArtifacts "oc_export_all.yaml"
            archiveArtifacts "applogs/*.log"
        } catch (err) {
            errString = err.toString()
            echo "Collecting logs failed: ${errString}"
        }
    }
}


def runSmokeTest(project) {
    /* Deploy a test env to 'project' in openshift, checkout e2e-tests, run the smoke tests */

    // cache creds so we can git 'ls-remote' below...
    sh "git config --global credential.helper cache"
    checkout scm

    // get refspec so we can set up the OpenShift build config to point to this PR
    // there's gotta be a better way to get the refspec, somehow 'checkout scm' knows what it is ...
    def refspec;
    stage("Get refspec") {
        refspec = "refs/pull/${env.CHANGE_ID}/merge"
        def refspecExists = sh(returnStdout: true, script: "git ls-remote | grep ${refspec}").trim()
        if (!refspecExists) {
            error("Unable to find git refspec: ${refspec}")
        }
    }

    // check out e2e-tests
    stage("Check out repos") {
        checkoutRepo(e2eTestsDir, e2eTestsRepo)
        checkoutRepo(e2eDeployDir, e2eDeployRepo)
    }

    stage("Install ocdeployer") {
        sh """
            python3.6 -m venv ${venvDir}
            ${venvDir}/bin/pip install --upgrade pip
        """
        dir(e2eDeployDir) {
            sh "${venvDir}/bin/pip install -r requirements.txt"
        }
    }

    stage("Wipe test environment") {
        sh "${venvDir}/bin/ocdeployer -w --no-confirm ${project}"
    }

    stage("Install e2e-tests") {
        dir(e2eTestsDir) {
            // Use sshagent so we can clone github private repos referenced in requirements.txt
            sshagent(credentials: ['insightsdroid-ssh-git']) {
                sh """
                    mkdir -p ~/.ssh
                    touch ~/.ssh/known_hosts
                    cp ~/.ssh/known_hosts ~/.ssh/known_hosts.backup
                    ssh-keyscan -t rsa github.com > ~/.ssh/known_hosts
                    ${venvDir}/bin/pip install -r requirements.txt
                    cp ~/.ssh/known_hosts.backup ~/.ssh/known_hosts
                """
            }
        }
    }

    try {
        deployEnvironment(refspec, project)
    } catch (err) {
        collectLogs(project)
        throw err
    }

    stage("Run tests (pytest marker: ${pytestMarker})") {
        /*
         * Set up the proper env vars for the tests by getting current routes from the OpenShfit project,
         * then run the tests with the proper smoke marker for this app/service.
         *
         * NOTE: 'tee' is used when running pytest so we always get a "0" return code. The 'junit' step
         * will take care of failing the build if any tests fail...
         */
        dir(e2eTestsDir) {
            sh """
                ${venvDir}/bin/ocdeployer --list-routes ${project} --output json > routes.json
                cat routes.json
                ${venvDir}/bin/python envs/convert-from-ocdeployer.py routes.json env_vars.sh
                cat env_vars.sh
                . ./env_vars.sh
                export OCP_ENV=${project}

                ${venvDir}/bin/python -m pytest --junitxml=junit.xml -s -v -m ${pytestMarker} 2>&1 | tee pytest.log
            """

            archiveArtifacts "pytest.log"
        }
    }

    collectLogs(project)

    dir(e2eTestsDir) {
        junit "junit.xml"
    }

    stage("Wipe test environment") {
        sh "${venvDir}/bin/ocdeployer -w --no-confirm ${project}"
    }
}

