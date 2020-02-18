#!/bin/bash
set -euo pipefail

version="$(git rev-parse HEAD)"

if [ "$(git rev-parse --abbrev-ref HEAD)" != 'master' ]; then
    if [[ -z "${DEPLOY_DANGEROUSLY_NON_MASTER+x}" ]]; then
        echo "I will only deploy from the master branch! Set DEPLOY_DANGEROUSLY_NON_MASTER if you want to skip this check!"
        exit 1
    fi
fi

if ! git diff-index --quiet HEAD --; then
    if [[ -z "${DEPLOY_DANGEROUSLY_DIRTY+x}" ]]; then
        echo "I will only deploy commited changes! Set DEPLOY_DANGEROUSLY_DIRTY if you want to skip this check!"
        exit 1
    fi
    version="${version}-dirty-$(date '+%s')"
fi

set -x

ssh "${DEPLOY_USER}@${DEPLOY_HOST}" mkdir -p "/opt/wooloobot/versions/${version}"
tar cjf - bot systemd Pipfile Pipfile.lock | ssh "${DEPLOY_USER}@${DEPLOY_HOST}" tar xjf - -C "/opt/wooloobot/versions/${version}"
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" ln -sfn "/opt/wooloobot/versions/${version}" /opt/wooloobot/live
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" sudo /usr/bin/sudo -u wooloobot -H -i PWD=/var/lib/wooloobot /usr/local/bin/pipenv install
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" sudo /bin/systemctl daemon-reload
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" sudo /bin/systemctl restart wooloobot
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" find -L /opt/wooloobot/versions -maxdepth 1 -mindepth 1 -not -samefile /opt/wooloobot/live -exec rm -rf \{} +
