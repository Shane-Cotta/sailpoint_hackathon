#!/usr/bin/env bash
# Run the SailPoint CLI with credentials from ui-plugins/.env (gitignored).
#
# The CLI's keyring storage does not work in this sandbox ("PAT will only work
# with environment variables"), so we feed it SAIL_BASE_URL / SAIL_CLIENT_ID /
# SAIL_CLIENT_SECRET from the environment instead of `sail env create`.
#
# Usage (from inside a plugin workspace, e.g. manager-lookup-shcotta/):
#   ../sail.sh ui-plugins list
#   ../sail.sh ui-plugins create --private
#   ../sail.sh ui-plugins link
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$here/.env" ]]; then
  echo "Missing $here/.env (needs SAIL_BASE_URL, SAIL_CLIENT_ID, SAIL_CLIENT_SECRET)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. "$here/.env"
set +a
# </dev/null: some sail commands prompt ("Press Enter to continue") and would
# otherwise hang in a non-interactive shell.
exec sail "$@" </dev/null
