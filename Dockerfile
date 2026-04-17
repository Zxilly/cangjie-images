# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=debian:bookworm

FROM --platform=$TARGETPLATFORM ${BASE_IMAGE} AS base
ARG BASE_FAMILY
RUN --mount=type=bind,source=scripts/install-base-deps.sh,target=/usr/local/bin/install-base-deps \
    install-base-deps "$BASE_FAMILY"

FROM base AS sdk
ARG CANGJIE_ARCHIVE_URL
ARG CANGJIE_ARCHIVE_SHA256
RUN --mount=type=bind,source=scripts/install-cangjie.sh,target=/usr/local/bin/install-cangjie \
    --mount=type=tmpfs,target=/tmp/cj \
    install-cangjie

FROM base
ARG CANGJIE_CHANNEL
ARG CANGJIE_VERSION

COPY --from=sdk --link /target/ /
COPY scripts/cangjie-entrypoint.sh /usr/local/bin/cangjie-entrypoint
RUN chmod +x /usr/local/bin/cangjie-entrypoint

LABEL org.opencontainers.image.title="Cangjie"
LABEL org.opencontainers.image.description="Prebuilt Cangjie SDK image"
LABEL io.cangjie.channel="${CANGJIE_CHANNEL}"
LABEL io.cangjie.version="${CANGJIE_VERSION}"

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/cangjie-entrypoint"]
CMD ["bash"]
