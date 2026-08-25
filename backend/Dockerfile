FROM python:3.11-slim

# ===== 国内镜像源固化（2026-08-25 实测：阿里云 pip/apt 0.2~0.5s、淘宝 npm 0.44s）=====
# 不依赖运行时网络：构建期一次固化，避免每次构建踩 GitHub/官方源慢速
ARG APT_MIRROR=mirrors.aliyun.com
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    git \
    nodejs \
    npm \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 配置 npm 使用淘宝镜像（npm install 走国内源）
RUN npm config set registry https://registry.npmmirror.com

# ===== 多语言标准工具（真实支持，非模拟）=====
# - ESLint 9：JS/TS 规范检查事实标准（全局安装 + typescript-eslint 解析器）
# - golangci-lint：Go 官方推荐 meta-linter（单二进制）
# - OSV-Scanner：Google 官方多生态漏洞扫描器（覆盖 go.mod；npm audit 覆盖 JS）
# 优先 COPY 宿主机 tools/ 预下载的二进制（构建期零 GitHub 依赖）；
# 缺失时回退到 ghproxy.net 加速下载（国内 GitHub 代理）。
ARG GOLANGCI_LINT_VERSION=1.61.0
ARG OSV_SCANNER_VERSION=v1.9.2
RUN npm install -g eslint@9 typescript @typescript-eslint/parser @typescript-eslint/eslint-plugin \
    && mkdir -p /tools
COPY tools/golangci-lint.tar.gz /tools/golangci-lint.tar.gz
COPY tools/osv-scanner /tools/osv-scanner
RUN if [ -s /tools/golangci-lint.tar.gz ]; then \
        tar -xz --strip-components=1 -C /usr/local/bin -f /tools/golangci-lint.tar.gz "golangci-lint-${GOLANGCI_LINT_VERSION}-linux-amd64/golangci-lint"; \
    else \
        curl -sSfL --retry 3 "https://ghproxy.net/https://github.com/golangci/golangci-lint/releases/download/v${GOLANGCI_LINT_VERSION}/golangci-lint-${GOLANGCI_LINT_VERSION}-linux-amd64.tar.gz" \
            | tar -xz --strip-components=1 -C /usr/local/bin "golangci-lint-${GOLANGCI_LINT_VERSION}-linux-amd64/golangci-lint"; \
    fi \
    && if [ -s /tools/osv-scanner ]; then \
        cp /tools/osv-scanner /usr/local/bin/osv-scanner; \
    else \
        curl -sSfL --retry 3 -o /usr/local/bin/osv-scanner \
            "https://ghproxy.net/https://github.com/google/osv-scanner/releases/download/${OSV_SCANNER_VERSION}/osv-scanner_linux_amd64"; \
    fi \
    && chmod +x /usr/local/bin/osv-scanner \
    && rm -rf /tools

# 配置 pip 使用国内镜像源（阿里云），加速依赖安装（CrewAI/Semgrep 依赖树庞大）
# 注：清华/阿里镜像对 uv 二进制包同步异常（仅远古 0.0.5/0.1.0），故直接用 pip 安装
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_NO_CACHE_DIR=1

# 先复制项目元数据与主包，安装依赖（依赖层仅在 pyproject.toml/app 变化时重建）
COPY pyproject.toml .
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e ".[dev]"

# Semgrep 规则本地化：构建时从官方仓库克隆（离线扫描，避免每次联网下载 registry 规则）
# 直连失败时回退 ghproxy.net 加速（国内 GitHub 代理）
RUN (git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/semgrep/semgrep-rules.git /tmp/semgrep-rules \
     || git clone --depth 1 --filter=blob:none --sparse \
        https://ghproxy.net/https://github.com/semgrep/semgrep-rules.git /tmp/semgrep-rules) \
    && cd /tmp/semgrep-rules \
    && git sparse-checkout set python javascript typescript java go \
    && mkdir -p /app/app/data \
    && cp -r /tmp/semgrep-rules /app/app/data/semgrep-rules \
    && rm -rf /tmp/semgrep-rules

# 复制源代码
COPY . .

WORKDIR /app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
