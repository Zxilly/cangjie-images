# 关于这个仓库

[![CI](https://github.com/Zxilly/cangjie-images/actions/workflows/ci.yml/badge.svg)](https://github.com/Zxilly/cangjie-images/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Docker Hub](https://img.shields.io/badge/Docker%20Hub-zxilly%2Fcangjie-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/zxilly/cangjie)

`cangjie-images` 是 Docker 镜像 [`zxilly/cangjie`](https://hub.docker.com/r/zxilly/cangjie) 的构建与发布仓库。

镜像使用方式、tag 选择和变体说明见 Docker Hub 页面

## 稳定版基础变体

稳定版当前生成以下基础变体：

- `bookworm`
- `slim-bookworm`
- `bullseye`
- `slim-bullseye`
- `trixie`
- `slim-trixie`
- `openeuler-24.03`
- `slim-openeuler-24.03`
- `openeuler-22.03`
- `slim-openeuler-22.03`
- `openeuler-20.03`
- `slim-openeuler-20.03`

默认基础变体为 `bookworm`。

## 发布的 tag 形式

稳定版 tag：

- 默认 `bookworm` 变体同时发布无后缀 tag 和 `-bookworm` 别名，例如
  `1.0.5`、`1.0.5-bookworm`、`1.0`、`1.0-bookworm`、`lts`、`lts-bookworm`、
  `latest`、`latest-bookworm`
- 其他变体发布 `<stable-tag>-<base>`，例如
  `1.0.5-slim-bookworm`、`lts-slim-bookworm`、`1.0.5-openeuler-24.03`、
  `1.0.5-slim-openeuler-24.03`

nightly tag：

- 默认 `bookworm` 变体发布 `nightly` 和 `nightly-<version>`
- 其他变体发布 `nightly-<base>` 或 `nightly-<version>-<base>`

## 本地开发

安装依赖：

```console
uv sync --locked --dev
```

生成稳定版 Dockerfile：

```console
uv run cangjie-images generate --versions-root versions
```

生成 Docker Hub 发布计划：

```console
uv run cangjie-images plan --image zxilly/cangjie
```

写入单架构 digest：

```console
uv run cangjie-images write-digest \
  --output-dir digests \
  --release-id lts-1-0-5-bookworm \
  --arch amd64 \
  --digest sha256:...
```

合并多架构 manifest：

```console
uv run cangjie-images merge \
  --image zxilly/cangjie \
  --release-id lts-1-0-5-bookworm \
  --tags-json '["1.0.5","1.0.5-bookworm"]' \
  --arches-json '["amd64","arm64"]' \
  --digests-dir digests
```

## GitHub 工作流

- `ci.yml`
  运行 `ruff`、`pyright` 和 `pytest`
- `update-versions.yml`
  重新生成 `versions/` 下的稳定版 Dockerfile 并创建更新 PR
- `publish.yml`
  对比已提交 Dockerfile 与 Docker Hub tags，构建缺失变体并发布多架构 manifest

## 许可证

本仓库采用 MIT 许可证发布，详见 [`LICENSE`](LICENSE)。

发布到 Docker Hub 的镜像同时包含上游仓颉 SDK 和所选基础镜像中的软件包；这些组件仍分别受其原始许可证和使用条款约束。
