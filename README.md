# cangjie-images

自动发布仓颉 Docker 镜像到 Docker Hub `Zxilly/cangjie` 的仓库模板。

这个项目参考了：

- [`Zxilly/cjv`](https://github.com/Zxilly/cjv) 的稳定版 manifest 与 nightly 下载逻辑
- [`docker-library/python`](https://github.com/docker-library/python) 的 base 变体思路
- [`docker-library/golang`](https://github.com/docker-library/golang) / [`rust-lang/docker-rust`](https://github.com/rust-lang/docker-rust) 的版本矩阵组织方式

## 支持的基础镜像

当前变体与 Python 官方镜像的 Debian 系列保持相近，并额外提供 `openeuler`：

- `bookworm` -> `debian:bookworm`
- `slim-bookworm` -> `debian:bookworm-slim`
- `trixie` -> `debian:trixie`
- `slim-trixie` -> `debian:trixie-slim`
- `openeuler` -> `openeuler/openeuler:24.03-lts-sp1`

`alpine` 不在支持范围内。

## 发布策略

发布工作流分三段：

1. `analyze`
   拉取稳定版 manifest、可选读取 nightly、查询 Docker Hub 当前 tags，然后只生成“还没发布”的版本/base/架构矩阵。
2. `build`
   在对应 runner 上原生构建镜像并按 digest 推送。`arm64` 条目会使用 `ubuntu-24.04-arm`。
3. `publish`
   聚合每个版本/base 的多架构 digest，创建最终 tags。

## Tag 约定

- 每个版本 + 每个 base 都会生成精确 tag，例如 `1.0.5-bookworm`
- 默认 base `bookworm` 额外提供无后缀 tag，例如 `1.0.5`
- 稳定版最新小版本会生成 minor alias，例如 `1.0`
- 最新 LTS 会额外生成 `lts` 与 `latest`
- 最新 STS 会额外生成 `sts`
- 最新 nightly 会生成 `nightly`，同时保留精确 tag `nightly-<version>`

## GitHub Secrets

需要在仓库中配置：

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
- `CANGJIE_NIGHTLY_API_KEY`

`CANGJIE_NIGHTLY_API_KEY` 只在需要发布 nightly 时使用；如果没有配置，工作流会跳过 nightly 计划。

## 本地使用

```bash
uv sync --locked --dev
uv run pytest
uv run cangjie-images plan --image zxilly/cangjie --include-nightly
```

