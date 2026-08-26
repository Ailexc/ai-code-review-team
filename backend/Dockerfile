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

# 配置 pip 使用国内镜像源（阿里云），加速依赖安装（CrewAI/Semgrep 依赖树庞大）
# 注：清华/阿里镜像对 uv 二进制包同步异常（仅远古 0.0.5/0.1.0），故直接用 pip 安装
# 注：不要设置 PIP_NO_CACHE_DIR —— 会禁用 pip 缓存写入，使下方 cache mount 形同虚设
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

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

# ===== 多语言标准工具（真实支持，非模拟）=====
# - ESLint 9：JS/TS 规范检查事实标准（npm 淘宝镜像安装）
# - golangci-lint：Go 官方推荐 meta-linter（Go 工具链 go install，走 goproxy.cn）
# - OSV-Scanner：Google 官方多生态漏洞扫描器（同上，覆盖 go.mod；npm audit 覆盖 JS）
# 关键：全链路国内官方镜像（Go 官方中国镜像 golang.google.cn + goproxy.cn），
# 零 GitHub 依赖，构建稳定可固化。
#
# ⚠️ Go 工具链必须保留在最终镜像中：golangci-lint 运行时做类型检查需要调用 go 命令
# （实测删除后报 "go command required, not found"，静默返回空结果 = 假支持）。
# ENV GOPROXY 同时服务构建期安装与运行时类型检查的模块下载。
#
# 层序说明：本层刻意放在 pip 层之后 —— 未来调整工具版本不会触发 pip 全量重装。
ARG GOLANGCI_LINT_VERSION=v1.61.0
ARG OSV_SCANNER_VERSION=v1.9.2
ARG GO_VERSION=1.23.4
ENV PATH="/usr/local/go/bin:${PATH}" \
    GOPROXY="https://goproxy.cn,direct"
RUN npm install -g eslint@9 typescript @typescript-eslint/parser @typescript-eslint/eslint-plugin \
    && curl -sSfL -o /tmp/go.tgz "https://golang.google.cn/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
    && tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz \
    && go install "github.com/golangci/golangci-lint/cmd/golangci-lint@${GOLANGCI_LINT_VERSION}" \
    && go install "github.com/google/osv-scanner/cmd/osv-scanner@${OSV_SCANNER_VERSION}" \
    && chmod +x /root/go/bin/golangci-lint /root/go/bin/osv-scanner

# 复制源代码
COPY . .

WORKDIR /app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
