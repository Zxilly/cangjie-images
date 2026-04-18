# 快速参考

-	**维护者**：
	[Zxilly](https://github.com/Zxilly/cangjie-images)（非官方）

-	**问题反馈**：
	[https://github.com/Zxilly/cangjie-images/issues](https://github.com/Zxilly/cangjie-images/issues)

-	**镜像地址**：
	[`zxilly/cangjie`](https://hub.docker.com/r/zxilly/cangjie)

-	**支持的架构**：
	`amd64`、`arm64`

# 支持的 tag 以及对应的 `Dockerfile`

-	[`1.0.5`, `1.0`, `lts`, `latest`, `1.0.5-bookworm`, `1.0-bookworm`, `lts-bookworm`](dockerfiles/1.0.5/bookworm/Dockerfile)
-	[`1.0.5-slim-bookworm`, `1.0-slim-bookworm`, `lts-slim-bookworm`](dockerfiles/1.0.5/slim-bookworm/Dockerfile)
-	[`1.0.5-trixie`, `1.0-trixie`, `lts-trixie`](dockerfiles/1.0.5/trixie/Dockerfile)
-	[`1.0.5-slim-trixie`, `1.0-slim-trixie`, `lts-slim-trixie`](dockerfiles/1.0.5/slim-trixie/Dockerfile)
-	[`1.0.5-bullseye`, `1.0-bullseye`, `lts-bullseye`](dockerfiles/1.0.5/bullseye/Dockerfile)
-	[`1.0.5-slim-bullseye`, `1.0-slim-bullseye`, `lts-slim-bullseye`](dockerfiles/1.0.5/slim-bullseye/Dockerfile)
-	[`1.0.5-openeuler-24.03`, `1.0-openeuler-24.03`, `lts-openeuler-24.03`](dockerfiles/1.0.5/openeuler-24.03/Dockerfile)
-	[`1.0.5-openeuler-22.03`, `1.0-openeuler-22.03`, `lts-openeuler-22.03`](dockerfiles/1.0.5/openeuler-22.03/Dockerfile)
-	[`1.0.5-openeuler-20.03`, `1.0-openeuler-20.03`, `lts-openeuler-20.03`](dockerfiles/1.0.5/openeuler-20.03/Dockerfile)
-	[`nightly`, `nightly-<version>`, `nightly-bookworm`, `nightly-<version>-bookworm`](dockerfiles/nightly/bookworm/Dockerfile)
-	[`nightly-slim-bookworm`, `nightly-<version>-slim-bookworm`](dockerfiles/nightly/slim-bookworm/Dockerfile)
-	[`nightly-trixie`, `nightly-<version>-trixie`](dockerfiles/nightly/trixie/Dockerfile)
-	[`nightly-slim-trixie`, `nightly-<version>-slim-trixie`](dockerfiles/nightly/slim-trixie/Dockerfile)
-	[`nightly-bullseye`, `nightly-<version>-bullseye`](dockerfiles/nightly/bullseye/Dockerfile)
-	[`nightly-slim-bullseye`, `nightly-<version>-slim-bullseye`](dockerfiles/nightly/slim-bullseye/Dockerfile)
-	[`nightly-openeuler-24.03`, `nightly-<version>-openeuler-24.03`](dockerfiles/nightly/openeuler-24.03/Dockerfile)
-	[`nightly-openeuler-22.03`, `nightly-<version>-openeuler-22.03`](dockerfiles/nightly/openeuler-22.03/Dockerfile)
-	[`nightly-openeuler-20.03`, `nightly-<version>-openeuler-20.03`](dockerfiles/nightly/openeuler-20.03/Dockerfile)

实际发布的 tag 列表以 [Docker Hub](https://hub.docker.com/r/zxilly/cangjie/tags) 上的内容为准。

# 仓颉是什么？

仓颉（Cangjie）是面向全场景智能应用的通用编程语言，兼顾开发效率与运行性能。

> [https://cangjie-lang.cn](https://cangjie-lang.cn)

# 如何使用这个镜像

## 通过 `Dockerfile` 在项目中使用

```dockerfile
FROM zxilly/cangjie:1.0

WORKDIR /app
COPY . .

RUN cjpm build

CMD ["./target/release/bin/main"]
```

构建并运行：

```console
$ docker build -t my-cangjie-app .
$ docker run --rm my-cangjie-app
```

## 直接启动一个容器

```console
$ docker run --rm -it zxilly/cangjie:1.0 cjc --version
```

## 挂载源码临时编译

```console
$ docker run --rm -v "$PWD":/src -w /src zxilly/cangjie:1.0 cjpm build
```

# 镜像变体

`zxilly/cangjie` 镜像有多个变体，分别满足不同的使用场景。

## `zxilly/cangjie:<version>`

默认变体，基于 `debian:bookworm`。如果不确定要选哪个，选这个。

## `zxilly/cangjie:<version>-slim`

基于 `debian:<suite>-slim`，只包含运行仓颉必需的最小依赖。体积更小，但缺少一些常见的系统工具和库；需要额外依赖时请自行安装。

## `zxilly/cangjie:<version>-bookworm`、`-bullseye`、`-trixie`

基于对应 Debian 发行版的镜像。如果需要将运行环境固定在某个 Debian 版本上，请使用这些 tag。每个 Debian 版本都同时提供 `slim-` 前缀的精简变体。

## `zxilly/cangjie:<version>-openeuler-24.03`、`-openeuler-22.03`、`-openeuler-20.03`

基于对应 openEuler 发行版的镜像：

-	`openeuler-24.03` → `openeuler/openeuler:24.03-lts-sp2`
-	`openeuler-22.03` → `openeuler/openeuler:22.03-lts-sp4`
-	`openeuler-20.03` → `openeuler/openeuler:20.03-lts-sp4`

适合运行在 openEuler 生态或需要与 openEuler 宿主 ABI 匹配的场景。

## `zxilly/cangjie:nightly-*`

追踪仓颉官方 nightly 构建的镜像。与稳定版一样覆盖所有 base 变体（`bookworm`、`slim-bookworm`、`bullseye`、`slim-bullseye`、`trixie`、`slim-trixie`、`openeuler-24.03`、`openeuler-22.03`、`openeuler-20.03`）。`nightly` 为默认 base（`bookworm`）的 alias，精确版本可通过 `nightly-<version>` 或 `nightly-<version>-<base>` 引用。

# Tag 约定

-	`<version>-<base>`：精确 tag，例如 `1.0.5-bookworm`、`1.0.5-openeuler-24.03`
-	`<version>`：等同于 `<version>-bookworm`
-	`<major>.<minor>`：该小版本下最新的补丁版本
-	`lts` / `latest`：最新的 LTS 版本
-	`sts`：最新的 STS 版本
-	`nightly`、`nightly-<version>`：nightly 构建

# 许可证

镜像中分发的仓颉工具链遵循[仓颉语言的许可条款](https://cangjie-lang.cn)。

本仓库（构建脚本与 Dockerfile）以 MIT 协议发布。镜像中包含的其他软件遵循其各自的许可证。
