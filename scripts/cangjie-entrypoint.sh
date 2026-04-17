#!/usr/bin/env bash
# envsetup.sh dispatches on the running shell via /proc/$$/exe, so the
# entrypoint runs under bash (not dash) to hit the sh/bash case, and
# leaves nounset off because envsetup.sh expands $LD_LIBRARY_PATH
# without a default.
set -eo pipefail

if [ -r /etc/cangjie/prefix ]; then
    # shellcheck disable=SC1091
    . /etc/cangjie/prefix
fi

if [ -n "${CANGJIE_HOME:-}" ] && [ -r "$CANGJIE_HOME/envsetup.sh" ]; then
    # shellcheck disable=SC1091
    . "$CANGJIE_HOME/envsetup.sh"
fi

exec "$@"
