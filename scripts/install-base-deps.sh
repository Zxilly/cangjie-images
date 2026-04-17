#!/bin/sh
set -eu

family="${1:?base family is required}"

case "$family" in
  debian)
    apt-get update
    apt-get install -y --no-install-recommends \
      bash \
      binutils \
      ca-certificates \
      curl \
      findutils \
      g++ \
      gcc \
      git \
      libc6-dev \
      libssl-dev \
      make \
      openssl \
      pkg-config \
      procps \
      tar \
      unzip \
      xz-utils \
      zip
    rm -rf /var/lib/apt/lists/*
    ;;
  openeuler)
    dnf install -y \
      bash \
      binutils \
      ca-certificates \
      curl \
      findutils \
      gcc \
      gcc-c++ \
      git \
      glibc-devel \
      make \
      openssl \
      openssl-devel \
      pkgconfig \
      procps-ng \
      tar \
      unzip \
      xz \
      zip
    dnf clean all
    rm -rf /var/cache/dnf
    ;;
  *)
    echo "unsupported base family: $family" >&2
    exit 1
    ;;
esac
