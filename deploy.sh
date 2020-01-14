#!/bin/bash
set -euo pipefail
set -x

tempd="$(mktemp -d)"
ssh_control_path="${tempd}/control.sock"
cleanup() {
    ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" -O exit || true
    rm -rf "${tempd}"
}
trap cleanup EXIT INT TERM

ssh -oControlMaster=yes -oControlPath="${ssh_control_path}" -Nf "${DEPLOY_USER}@${DEPLOY_HOST}"
tar cjf - bot systemd Pipfile Pipfile.lock | ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" tar xjf - -C "/opt/wooloobot/live"
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" sudo /usr/bin/sudo -u wooloobot -H -i PWD=/var/lib/wooloobot /usr/local/bin/pipenv install
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" sudo /bin/systemctl daemon-reload
ssh -oControlMaster=no -oControlPath="${ssh_control_path}" "${DEPLOY_HOST}" sudo /bin/systemctl restart wooloobot
