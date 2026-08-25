FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

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
RUN git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/semgrep/semgrep-rules.git /tmp/semgrep-rules \
    && cd /tmp/semgrep-rules \
    && git sparse-checkout set python javascript typescript java go \
    && mkdir -p /app/app/data \
    && cp -r /tmp/semgrep-rules /app/app/data/semgrep-rules \
    && rm -rf /tmp/semgrep-rules

# 复制源代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
