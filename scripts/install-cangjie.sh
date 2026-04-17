#!/usr/bin/env bash
set -euo pipefail

: "${CANGJIE_ARCHIVE_URL:?CANGJIE_ARCHIVE_URL is required}"
CANGJIE_ARCHIVE_SHA256="${CANGJIE_ARCHIVE_SHA256:-}"
CANGJIE_HOME="${CANGJIE_HOME:-/opt/cangjie}"
CANGJIE_STAGE="${CANGJIE_STAGE:-/tmp/cj}"
TARGET_ROOT="${CANGJIE_TARGET_ROOT:-/target}"

install_root="$(dirname "$CANGJIE_HOME")"
mkdir -p "$install_root" "$CANGJIE_STAGE"

archive="$CANGJIE_STAGE/sdk.tar.gz"
curl -fsSL "$CANGJIE_ARCHIVE_URL" -o "$archive"

if [ -n "$CANGJIE_ARCHIVE_SHA256" ]; then
    echo "$CANGJIE_ARCHIVE_SHA256  $archive" | sha256sum -c -
fi

tar -xzf "$archive" -C "$install_root" \
    --exclude='cangjie/lib/windows_*' \
    --exclude='cangjie/lib/*.dll' \
    --exclude='cangjie/lib/*.dll.a' \
    --exclude='cangjie/runtime/lib/windows_*' \
    --exclude='cangjie/modules/windows_*' \
    --exclude='cangjie/third_party/mingw'

if [ ! -f "$CANGJIE_HOME/envsetup.sh" ]; then
    echo "envsetup.sh not found under $CANGJIE_HOME" >&2
    exit 1
fi

# Record the install prefix so the runtime entrypoint and
# /etc/profile.d loader can locate envsetup.sh without hardcoding paths.
mkdir -p /etc/cangjie
printf 'CANGJIE_HOME=%s\n' "$CANGJIE_HOME" > /etc/cangjie/prefix

cat > /etc/profile.d/cangjie.sh <<'EOF'
# Load Cangjie SDK environment for login shells.
if [ -r /etc/cangjie/prefix ]; then
    . /etc/cangjie/prefix
    if [ -n "${CANGJIE_HOME:-}" ] && [ -r "$CANGJIE_HOME/envsetup.sh" ]; then
        # shellcheck disable=SC1091
        . "$CANGJIE_HOME/envsetup.sh"
    fi
fi
EOF
chmod 0644 /etc/profile.d/cangjie.sh

# Sanity check via the same code path the entrypoint will use at runtime.
# envsetup.sh expands $LD_LIBRARY_PATH without a default, so relax nounset.
set +u
# shellcheck disable=SC1091
. "$CANGJIE_HOME/envsetup.sh"
set -u
cjc --version
cjpm --version

# Stage the install artefacts for `COPY --from=build --link /target/ /`.
# Keep the layout identical to the final image so the copy is a plain
# whole-tree mirror.
mkdir -p "$TARGET_ROOT$install_root" "$TARGET_ROOT/etc/profile.d"
mv "$CANGJIE_HOME" "$TARGET_ROOT$CANGJIE_HOME"
mv /etc/cangjie    "$TARGET_ROOT/etc/cangjie"
mv /etc/profile.d/cangjie.sh "$TARGET_ROOT/etc/profile.d/cangjie.sh"
