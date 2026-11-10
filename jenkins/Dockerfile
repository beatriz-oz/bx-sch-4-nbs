# The local Jenkins for Nails by Scooby: Jenkins (Java 21) plus the tools both pipelines use.
# Built and started by compose.yaml (see README.md in this folder).
FROM jenkins/jenkins:lts-jdk21

USER root

# uv (Python and its packages; uv downloads the Python version pyproject.toml asks for).
# Pinned to the version used locally, so the lock file reads the same way.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

# Node 24 (the front end), copied from the official image with npm and npx.
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# The Docker command line only: the pipelines start throwaway MySQL and Mailpit containers
# through the host's Docker (the socket mounted in compose.yaml), next to this one.
COPY --from=docker:29-cli /usr/local/bin/docker /usr/local/bin/docker

USER jenkins

# Plugins, and Configuration as Code instead of the setup wizard.
COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY --chown=jenkins:jenkins casc.yaml /var/jenkins_conf/casc.yaml
ENV CASC_JENKINS_CONFIG=/var/jenkins_conf/casc.yaml \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
