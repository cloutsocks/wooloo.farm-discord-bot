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

tempd="$(mktemp -d)"
ssh_control_path="${tempd}/control.sock"
cleanup() {
    ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" -O exit || true
    rm -rf "${tempd}"
}
trap cleanup EXIT INT TERM

ssh -oControlMaster=yes -oControlPath="${ssh_control_path}" -Nf "${DEPLOY_USER}@${DEPLOY_HOST}"
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" mkdir -p "/opt/wooloobot/versions/${version}"
tar cjf - bot systemd Pipfile Pipfile.lock | ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" tar xjf - -C "/opt/wooloobot/versions/${version}"
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" ln -sfn "/opt/wooloobot/versions/${version}" /opt/wooloobot/live
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" sudo /bin/systemctl daemon-reload
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" sudo /bin/systemctl restart wooloobot
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" find -L /opt/wooloobot/versions -maxdepth 1 -mindepth 1 -not -samefile /opt/wooloobot/live -exec rm -rf \{} +
