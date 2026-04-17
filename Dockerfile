# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=debian:bookworm
FROM --platform=$TARGETPLATFORM ${BASE_IMAGE}

ARG BASE_FAMILY
ARG CANGJIE_CHANNEL
ARG CANGJIE_VERSION
ARG CANGJIE_ARCHIVE_URL
ARG CANGJIE_ARCHIVE_SHA256
ARG CANGJIE_NATIVE_DIR

COPY scripts/install-base-deps.sh /usr/local/bin/install-base-deps

RUN set -eux; \
    chmod +x /usr/local/bin/install-base-deps; \
    /usr/local/bin/install-base-deps "$BASE_FAMILY"

RUN --mount=type=tmpfs,target=/tmp/cj \
    set -eux; \
    curl -fsSL "$CANGJIE_ARCHIVE_URL" -o /tmp/cj/sdk.tar.gz; \
    if [ -n "$CANGJIE_ARCHIVE_SHA256" ]; then \
      echo "$CANGJIE_ARCHIVE_SHA256  /tmp/cj/sdk.tar.gz" | sha256sum -c -; \
    fi; \
    tar -xzf /tmp/cj/sdk.tar.gz -C /opt \
      --exclude='cangjie/lib/windows_*' \
      --exclude='cangjie/lib/*.dll' \
      --exclude='cangjie/lib/*.dll.a' \
      --exclude='cangjie/runtime/lib/windows_*' \
      --exclude='cangjie/modules/windows_*' \
      --exclude='cangjie/third_party/mingw'; \
    mkdir -p /workspace; \
    export PATH="/opt/cangjie/bin:/opt/cangjie/tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"; \
    export LD_LIBRARY_PATH="/opt/cangjie/runtime/lib/${CANGJIE_NATIVE_DIR}:/opt/cangjie/tools/lib"; \
    cjc --version; \
    cjpm --version

ENV CANGJIE_HOME=/opt/cangjie
ENV PATH=/opt/cangjie/bin:/opt/cangjie/tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV LD_LIBRARY_PATH=/opt/cangjie/runtime/lib/${CANGJIE_NATIVE_DIR}:/opt/cangjie/tools/lib

LABEL org.opencontainers.image.title="Cangjie"
LABEL org.opencontainers.image.description="Prebuilt Cangjie SDK image"
LABEL io.cangjie.channel="${CANGJIE_CHANNEL}"
LABEL io.cangjie.version="${CANGJIE_VERSION}"

WORKDIR /workspace
CMD ["bash"]

