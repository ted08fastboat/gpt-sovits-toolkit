# 声音工坊 · GPT-SoVITS 语音克隆 UI（CPU 推理版）
# 多架构：linux/amd64 与 linux/arm64 均可构建（Apple Silicon 上也就是 arm64）
FROM python:3.11-slim

# 国内镜像（想用官方源：docker build --build-arg PIP_INDEX=https://pypi.org/simple）
ARG PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
# 官方索引 download.pytorch.org 在国内常卡死，默认用阿里云镜像（内容一致，含 +cpu 版）
ARG TORCH_INDEX=https://mirrors.aliyun.com/pytorch-wheels/cpu

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_ENDPOINT=https://hf-mirror.com \
    TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
    REPO_ROOT=/repo \
    REF_DIR=/data/references \
    OUT_DIR=/data/outputs \
    NLTK_DATA=/repo/nltk_data \
    PORT=8000 \
    PRELOAD=1 \
    version=v2Pro

# 系统依赖：ffmpeg（音视频转码）、libsndfile（soundfile 读写）、libgomp（torch/numba 线程）
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg libsndfile1 libgomp1 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# PyTorch CPU 版（linux/amd64 与 linux/arm64 都有 2.6.0+cpu wheel，约 200MB）
# 若官方索引不可达，自动回退到 PIP_INDEX 上的常规版本
# 优先用随包预下载的 wheel（build/wheels，见 make_build_dir.sh），
# 没有或架构不匹配时依次回退：阿里云镜像 → 官方 CPU 索引 → PyPI 镜像
COPY wheels/ /wheels/
RUN pip install --no-cache-dir --find-links /wheels torch==2.6.0 torchaudio==2.6.0 \
 || pip install --no-cache-dir --index-url ${TORCH_INDEX} torch==2.6.0 torchaudio==2.6.0 \
 || pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 torchaudio==2.6.0 \
 || pip install --no-cache-dir -i ${PIP_INDEX} torch==2.6.0 torchaudio==2.6.0

# 其余依赖
COPY requirements-linux.txt /tmp/requirements-linux.txt
RUN pip install --no-cache-dir -i ${PIP_INDEX} -r /tmp/requirements-linux.txt

# 可选依赖：opencc（若该平台无 wheel 则退化到纯 Python 实现）、ASR（funasr）
RUN pip install --no-cache-dir -i ${PIP_INDEX} opencc || pip install --no-cache-dir -i ${PIP_INDEX} opencc-python-reimplemented
RUN pip install --no-cache-dir -i ${PIP_INDEX} imageio-ffmpeg
RUN pip install --no-cache-dir -i ${PIP_INDEX} funasr modelscope || echo "（ASR 依赖安装失败，不影响合成）"

# 代码：GPT-SoVITS 仓库 + 本 UI
COPY GPT-SoVITS /repo
COPY app /app/voiceui
COPY fetch_assets.py entrypoint.sh /app/voiceui/
# jieba_fast 兼容层（部分平台无 wheel，用纯 Python 版顶替）
COPY jieba_fast /repo/jieba_fast
RUN chmod +x /app/voiceui/entrypoint.sh \
 && mkdir -p /data/weights /data/references /data/outputs \
            /repo/GPT_SoVITS/pretrained_models /repo/GPT_SoVITS/text/G2PWModel /repo/nltk_data

WORKDIR /app/voiceui
EXPOSE 8000
VOLUME ["/data"]

# 健康检查：等 UI 起来
HEALTHCHECK --start-period=90s --interval=30s --timeout=5s --retries=3 \
  CMD curl -fs http://127.0.0.1:${PORT}/api/state || exit 1

ENTRYPOINT ["/app/voiceui/entrypoint.sh"]
