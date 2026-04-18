# 快速参考

-	**维护者**：  
	[Zxilly/cangjie-images](https://github.com/Zxilly/cangjie-images)

-	**问题反馈**：  
	[https://github.com/Zxilly/cangjie-images/issues](https://github.com/Zxilly/cangjie-images/issues)

-	**支持架构**：  
	`amd64`、`arm64`

# 支持的 tag 及对应 Dockerfile

稳定版 Dockerfile 位于 [`versions/`](https://github.com/Zxilly/cangjie-images/tree/master/versions)，nightly Dockerfile 在发布阶段按需生成。

-	`1.0.5`、`1.0.5-bookworm`、`1.0`、`lts`、`latest`
-	`1.0.5-slim-bookworm`、`lts-slim-bookworm`、`lts-slim`
-	`1.0.5-bullseye`、`1.0.5-trixie`
-	`1.0.5-openeuler-24.03`、`1.0.5-openeuler-22.03`、`1.0.5-openeuler-20.03`
-	`1.0.5-slim-openeuler-24.03`、`1.0.5-slim-openeuler-22.03`、`1.0.5-slim-openeuler-20.03`
-	`nightly`、`nightly-<version>`、`nightly-<version>-<base>`

# 什么是仓颉？

仓颉是华为开发的面向应用开发的通用编程语言，兼顾安全性、并发性与实用性。

> [cangjie-lang.cn](https://cangjie-lang.cn/)

# 如何使用这个镜像

## 在应用中使用

```dockerfile
FROM zxilly/cangjie:1.0.5

WORKDIR /workspace
COPY . .

RUN cjpm build --release

CMD ["./target/release/myapp"]
```

构建并运行：

```console
$ docker build -t my-cangjie-app .
$ docker run -it --rm my-cangjie-app
```

## 在容器内编译

```console
$ docker run --rm -v "$PWD":/workspace -w /workspace zxilly/cangjie:lts cjpm build --release
```

# 镜像变体

## `zxilly/cangjie:<version>`

默认变体，基于 Debian bookworm。不确定用哪个时优先选这个。tag 中的 `bookworm`、`bullseye`、`trixie` 表示所用的 Debian 发行版代号。

## `zxilly/cangjie:<version>-slim-*`

仅包含运行仓颉工具链所需的最小依赖，镜像更小。如需额外系统工具，需自行安装。

## `zxilly/cangjie:<version>-openeuler-<release>`

基于 openEuler 用户态，适合需要与 openEuler 环境保持一致的场景。当前支持 `24.03`、`22.03`、`20.03`。`slim-openeuler-*` 变体同样更小，预装工具更少。

## `zxilly/cangjie:nightly`

跟随上游每日构建，适合提前验证兼容性，不建议生产使用。使用 `nightly-<version>` 可固定某次快照。

# 许可证

本镜像由 [Zxilly/cangjie-images](https://github.com/Zxilly/cangjie-images) 自动构建发布，仓库本身采用 MIT 许可证。

与所有 Docker 镜像一样，镜像中还包含其他软件（如仓颉 SDK、基础系统包及间接依赖），它们各自受原始许可证约束。

使用本镜像即代表用户自行承担确认合规性的责任。
