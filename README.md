# 快速参考

-	**维护者**：
	[Zxilly](https://github.com/Zxilly/cangjie-images) — 社区维护的非官方镜像

-	**问题反馈**：
	[https://github.com/Zxilly/cangjie-images/issues](https://github.com/Zxilly/cangjie-images/issues)

-	**镜像地址**：
	[`zxilly/cangjie`](https://hub.docker.com/r/zxilly/cangjie)

-	**支持的架构**：
	`amd64`、`arm64`

-	**本说明的来源**：
	[`Zxilly/cangjie-images` 中的 `README.md`](https://github.com/Zxilly/cangjie-images/blob/master/README.md)

# 支持的 tag 以及对应的 `Dockerfile`

LTS（以当前最新 LTS `1.0.5` 为例）：

-	[`1.0.5`, `1.0`, `lts`, `latest`, `1.0.5-bookworm`, `1.0-bookworm`, `lts-bookworm`](dockerfiles/1.0.5/bookworm/Dockerfile)
-	[`1.0.5-slim-bookworm`, `1.0-slim-bookworm`, `lts-slim-bookworm`](dockerfiles/1.0.5/slim-bookworm/Dockerfile)
-	[`1.0.5-trixie`, `1.0-trixie`, `lts-trixie`](dockerfiles/1.0.5/trixie/Dockerfile)
-	[`1.0.5-slim-trixie`, `1.0-slim-trixie`, `lts-slim-trixie`](dockerfiles/1.0.5/slim-trixie/Dockerfile)
-	[`1.0.5-bullseye`, `1.0-bullseye`, `lts-bullseye`](dockerfiles/1.0.5/bullseye/Dockerfile)
-	[`1.0.5-slim-bullseye`, `1.0-slim-bullseye`, `lts-slim-bullseye`](dockerfiles/1.0.5/slim-bullseye/Dockerfile)
-	[`1.0.5-openeuler-24.03`, `1.0-openeuler-24.03`, `lts-openeuler-24.03`](dockerfiles/1.0.5/openeuler-24.03/Dockerfile)
-	[`1.0.5-openeuler-22.03`, `1.0-openeuler-22.03`, `lts-openeuler-22.03`](dockerfiles/1.0.5/openeuler-22.03/Dockerfile)
-	[`1.0.5-openeuler-20.03`, `1.0-openeuler-20.03`, `lts-openeuler-20.03`](dockerfiles/1.0.5/openeuler-20.03/Dockerfile)

STS（以当前最新 STS `1.1.0-beta.24` 为例）：

-	[`1.1.0-beta.24`, `sts`, `1.1.0-beta.24-bookworm`, `sts-bookworm`](dockerfiles/1.1.0-beta.24/bookworm/Dockerfile)
-	[`1.1.0-beta.24-slim-bookworm`, `sts-slim-bookworm`](dockerfiles/1.1.0-beta.24/slim-bookworm/Dockerfile)
-	[`1.1.0-beta.24-trixie`, `sts-trixie`](dockerfiles/1.1.0-beta.24/trixie/Dockerfile)
-	[`1.1.0-beta.24-slim-trixie`, `sts-slim-trixie`](dockerfiles/1.1.0-beta.24/slim-trixie/Dockerfile)
-	[`1.1.0-beta.24-bullseye`, `sts-bullseye`](dockerfiles/1.1.0-beta.24/bullseye/Dockerfile)
-	[`1.1.0-beta.24-slim-bullseye`, `sts-slim-bullseye`](dockerfiles/1.1.0-beta.24/slim-bullseye/Dockerfile)
-	[`1.1.0-beta.24-openeuler-24.03`, `sts-openeuler-24.03`](dockerfiles/1.1.0-beta.24/openeuler-24.03/Dockerfile)
-	[`1.1.0-beta.24-openeuler-22.03`, `sts-openeuler-22.03`](dockerfiles/1.1.0-beta.24/openeuler-22.03/Dockerfile)
-	[`1.1.0-beta.24-openeuler-20.03`, `sts-openeuler-20.03`](dockerfiles/1.1.0-beta.24/openeuler-20.03/Dockerfile)

Nightly：

-	[`nightly`, `nightly-<version>`, `nightly-bookworm`, `nightly-<version>-bookworm`](dockerfiles/nightly/bookworm/Dockerfile)
-	[`nightly-slim-bookworm`, `nightly-<version>-slim-bookworm`](dockerfiles/nightly/slim-bookworm/Dockerfile)
-	[`nightly-trixie`, `nightly-<version>-trixie`](dockerfiles/nightly/trixie/Dockerfile)
-	[`nightly-slim-trixie`, `nightly-<version>-slim-trixie`](dockerfiles/nightly/slim-trixie/Dockerfile)
-	[`nightly-bullseye`, `nightly-<version>-bullseye`](dockerfiles/nightly/bullseye/Dockerfile)
-	[`nightly-slim-bullseye`, `nightly-<version>-slim-bullseye`](dockerfiles/nightly/slim-bullseye/Dockerfile)
-	[`nightly-openeuler-24.03`, `nightly-<version>-openeuler-24.03`](dockerfiles/nightly/openeuler-24.03/Dockerfile)
-	[`nightly-openeuler-22.03`, `nightly-<version>-openeuler-22.03`](dockerfiles/nightly/openeuler-22.03/Dockerfile)
-	[`nightly-openeuler-20.03`, `nightly-<version>-openeuler-20.03`](dockerfiles/nightly/openeuler-20.03/Dockerfile)

# 仓颉是什么？

仓颉（Cangjie）是一门通用编程语言，面向全场景智能应用开发。它在语法层面融合了面向对象、函数式和命令式范式，并针对现代应用的并发、内存管理与互操作需求进行了设计。仓颉工具链（`cjc` 编译器与 `cjpm` 包管理器）由华为主导开发。

> [https://cangjie-lang.cn](https://cangjie-lang.cn)

# 如何使用这个镜像

## 在仓颉项目中创建 `Dockerfile`

```dockerfile
FROM zxilly/cangjie:1.0

WORKDIR /usr/src/app

COPY cjpm.toml ./
RUN cjpm update

COPY . .
RUN cjpm build --release

CMD ["./target/release/bin/main"]
```

然后构建并运行镜像：

```console
$ docker build -t my-cangjie-app .
$ docker run -it --rm --name my-running-app my-cangjie-app
```

## 在镜像中直接运行单个命令

对于只有一两个源文件的项目，可以直接挂载源码目录到镜像中执行：

```console
$ docker run -it --rm --name my-running-build -v "$PWD":/usr/src/myapp -w /usr/src/myapp zxilly/cangjie:1.0 cjpm build
```

或者进入一个交互式 shell 随意尝试：

```console
$ docker run -it --rm zxilly/cangjie:1.0 bash
```

# 镜像变体

`zxilly/cangjie` 镜像有多种变体，分别满足不同的使用场景。

## `zxilly/cangjie:<version>`

默认变体，基于 `debian:bookworm` 并预装常见的构建与调试工具。如果不确定要选哪个，就用这个。

## `zxilly/cangjie:<version>-slim`

该变体不包含默认 tag 中常见的 Debian 软件包，只保留运行仓颉工具链所必需的最小依赖。除非部署环境中*只*会运行仓颉镜像，并且对体积有严格要求，否则我们建议优先使用默认变体。

当使用这个镜像时，如果你的项目在 `cjpm build` 过程中需要调用外部 C/C++ 依赖或链接系统库，可能会因为缺少头文件或开发包而失败。可能的解决方式：

-	在此镜像中按需预装所需的 Debian 软件包，再执行 `cjpm build`。
-	改用默认变体。默认变体包含了大多数常见的开发依赖，能覆盖绝大多数构建场景。

## `zxilly/cangjie:<version>-bookworm`、`-bullseye`、`-trixie`

基于对应 Debian 发行版的镜像。如果需要将运行环境显式固定在某个 Debian 版本上（例如与运行环境保持一致），使用这些 tag。每个 Debian 版本都同时提供 `slim-` 前缀的精简变体。

## `zxilly/cangjie:<version>-openeuler-24.03`、`-openeuler-22.03`、`-openeuler-20.03`

基于对应 openEuler 发行版的镜像：

-	`openeuler-24.03` → `openeuler/openeuler:24.03-lts-sp2`
-	`openeuler-22.03` → `openeuler/openeuler:22.03-lts-sp4`
-	`openeuler-20.03` → `openeuler/openeuler:20.03-lts-sp4`

适合运行在 openEuler 宿主上、或需要与 openEuler glibc / ABI 匹配的场景。这些变体通过 `dnf` 安装系统依赖，包管理习惯上与 Debian 变体略有不同。

## `zxilly/cangjie:nightly-*`

追踪仓颉官方 nightly 构建，与稳定版一样覆盖全部 base 变体。`nightly` 为默认 base（`bookworm`）的别名，具体版本可通过 `nightly-<version>` 或 `nightly-<version>-<base>` 引用。nightly 版本的工具链行为可能与 LTS/STS 不一致，不建议在生产环境中使用。

# 许可证

镜像中分发的仓颉工具链遵循[仓颉语言的许可条款](https://cangjie-lang.cn)，使用前请自行确认其条款适用于你的使用场景。

本仓库（构建脚本与 `Dockerfile`）以 MIT 协议发布，详见仓库中的 `LICENSE` 文件。

与所有 Docker 镜像一样，这些镜像中很可能也包含其他遵循各自许可证（例如 Bash 等基础软件使用的 GPL 等）的软件。任何在镜像中预先分发的软件，使用时都应视为用户需要确保镜像的使用符合其所包含软件的全部相关许可证。
