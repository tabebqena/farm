#!/usr/bin/env bash
#
# Deploy / update the farm app on the remote host.
#
# Prompts for the SSH username and password, logs in, updates the repository
# (git pull, cloning it if missing) and rebuilds/recreates the docker compose
# stack.
#
# Requirements (local): OpenSSH client + util-linux (`setsid`), Linux/macOS.
#
# Usage:
#   ./scripts/deploy.sh
#
# Overridable via environment variables:
#   FARM_HOST=ssh.mazr3a.garden   FARM_APP_DIR=farm
#   FARM_BRANCH=main              FARM_REPO_URL=https://github.com/tabebqena/farm.git
#   FARM_COMPOSE_CMD="docker compose"
#
set -euo pipefail

HOST="${FARM_HOST:-ssh.mazr3a.garden}"
APP_DIR="${FARM_APP_DIR:-farm-hisab}"          # relative to the remote $HOME
BRANCH="${FARM_BRANCH:-main}"
REPO_URL="${FARM_REPO_URL:-https://github.com/tabebqena/farm.git}"
GIT_REMOTE="${FARM_GIT_REMOTE:-origin}"
COMPOSE_CMD="${FARM_COMPOSE_CMD:-docker compose}"

printf 'SSH username: '
read -r SSH_USER
printf 'SSH password: '
read -rs SSH_PASS
printf '\n'

if [ -z "${SSH_USER}" ]; then
  echo "error: SSH username is required" >&2
  exit 1
fi

# Temporary SSH_ASKPASS helper so the password is never passed as an argument.
ASKPASS_FILE="$(mktemp)"
trap 'rm -f "${ASKPASS_FILE}"' EXIT
{
  printf '#!/bin/sh\n'
  printf 'printf "%%s\\n" %q\n' "${SSH_PASS}"
} > "${ASKPASS_FILE}"
chmod 700 "${ASKPASS_FILE}"

run_remote() {
  SSH_ASKPASS="${ASKPASS_FILE}" \
  SSH_ASKPASS_REQUIRE=force \
  DISPLAY="${DISPLAY:-:0}" \
  setsid -w ssh \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile="${HOME}/.ssh/known_hosts" \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 \
    "${SSH_USER}@${HOST}" "$@"
}

REMOTE_SCRIPT=$(cat <<REMOTE
set -e
APP_DIR="\$HOME/${APP_DIR}"
if [ ! -d "\$APP_DIR/.git" ]; then
  echo ">> cloning ${REPO_URL} into \$APP_DIR"
  git clone "${REPO_URL}" "\$APP_DIR"
fi
cd "\$APP_DIR"
if [ ! -f .env ]; then
  echo "!! .env is missing in \$APP_DIR — copy .env.example and fill it in first." >&2
  exit 1
fi
echo ">> updating repository (${GIT_REMOTE}/${BRANCH})"
git fetch "${GIT_REMOTE}" "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only "${GIT_REMOTE}" "${BRANCH}"
echo ">> rebuilding and recreating the stack"
${COMPOSE_CMD} up --build -d
${COMPOSE_CMD} ps
REMOTE
)

echo ">> connecting to ${SSH_USER}@${HOST}"
run_remote "${REMOTE_SCRIPT}"
echo ">> done: https://hisab.mazr3a.garden/"
