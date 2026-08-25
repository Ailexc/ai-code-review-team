# tools/ — 构建期预下载的多语言工具二进制（缓存）

> **本目录内容不进入 git 版本控制**（体积大：golangci-lint 11.5MB + osv-scanner 32MB）。
> 由 Dockerfile 在构建时 COPY 进镜像，规避国内直连 GitHub 下载慢/断流问题。

## 目录用途

| 文件 | 来源 | 说明 |
|---|---|---|
| `golangci-lint.tar.gz` | golangci-lint v1.61.0 release | Go 规范检查（官方推荐 meta-linter） |
| `osv-scanner` | google/osv-scanner v1.9.2 release | Go/多生态漏洞扫描（go.mod） |

## 如何更新

1. 确认新版 release 资产名（架构为 linux-amd64）
2. 用 ghproxy.net 加速下载到本目录（国内 GitHub 代理）：
   ```bash
   cd backend/tools
   curl -sL --retry 5 -o golangci-lint.tar.gz \
     "https://ghproxy.net/https://github.com/golangci/golangci-lint/releases/download/v<版本>/golangci-lint-<版本>-linux-amd64.tar.gz"
   curl -sL --retry 5 -o osv-scanner \
     "https://ghproxy.net/https://github.com/google/osv-scanner/releases/download/v<版本>/osv-scanner_linux_amd64"
   ```
3. 同步更新 `backend/Dockerfile` 里的 `GOLANGCI_LINT_VERSION` / `OSV_SCANNER_VERSION` ARG

## 缺失时行为

Dockerfile 已做兜底：若 `tools/` 中文件为空/缺失，会在构建期回退到 ghproxy.net 直接下载。
