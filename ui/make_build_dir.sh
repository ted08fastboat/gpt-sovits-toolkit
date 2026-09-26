#!/bin/bash
# 组装 Docker 构建目录：ui/build/
#   build/ = Dockerfile + compose + 应用 + GPT-SoVITS 源码 + jieba 兼容层 + 挂载用的空目录 + .env
# 之后 cd ui/build && docker compose up -d --build 即可
set -eu
# 用法：./make_build_dir.sh [--cuda]
#   --cuda 用 NVIDIA GPU 版（Dockerfile.cuda / docker-compose.cuda.yml，torch 走 cu124）
MODE="cpu"
[ "${1:-}" = "--cuda" ] && MODE="cuda"
UI="$(cd "$(dirname "$0")" && pwd)"
WS="$(dirname "$UI")"
SRC_REPO="$WS/downloads/GPT-SoVITS-main"
PKG="$HOME/Desktop/GPT-SoVITS一键克隆"
OUT="$UI/build"

[ -d "$SRC_REPO" ] || { echo "❌ 找不到源码目录：$SRC_REPO"; exit 1; }

echo "== 清理 $OUT =="
rm -rf "$OUT"
mkdir -p "$OUT"

echo "== 复制 Docker 与说明文件 =="
cp "$UI/docker/entrypoint.sh" "$UI/docker/fetch_assets.py" \
   "$UI/docker/requirements-linux.txt" "$UI/docker/.dockerignore" "$UI/docker/README.md" "$OUT/"
if [ "$MODE" = "cuda" ]; then
  echo "   （GPU 模式：Dockerfile.cuda + docker-compose.cuda.yml）"
  cp "$UI/docker/Dockerfile.cuda" "$OUT/Dockerfile"
  cp "$UI/docker/docker-compose.cuda.yml" "$OUT/docker-compose.yml"
else
  cp "$UI/docker/Dockerfile" "$OUT/Dockerfile"
  cp "$UI/docker/docker-compose.yml" "$OUT/docker-compose.yml"
fi

echo "== 复制应用与兼容层 =="
cp -R "$UI/app" "$OUT/app"
cp -R "$WS/win/jieba_fast" "$OUT/jieba_fast"

echo "== 复制 GPT-SoVITS 源码（不含模型） =="
cp -R "$SRC_REPO" "$OUT/GPT-SoVITS"
rm -rf "$OUT/GPT-SoVITS/GPT_SoVITS/pretrained_models" "$OUT/GPT-SoVITS/GPT_SoVITS/text/G2PWModel" 2>/dev/null || true
# 删掉仓库自带的空权重目录（否则入口脚本的软链接会被塞进这些目录里）
for d in "$OUT/GPT-SoVITS"/GPT_weights* "$OUT/GPT-SoVITS"/SoVITS_weights*; do
  [ -d "$d" ] && rm -rf "$d"
done
# 丢掉开发时残留的 weight.json（里面可能是本机绝对路径，容器里会加载失败）
rm -f "$OUT/GPT-SoVITS/weight.json" "$OUT/GPT-SoVITS/GPT_SoVITS/weight.json" 2>/dev/null || true

echo "== 创建挂载目录 =="
mkdir -p "$OUT/models/pretrained_models" "$OUT/models/G2PWModel" "$OUT/models/nltk_data" \
         "$OUT/weights" "$OUT/references" "$OUT/outputs"

echo "== 放一份现成参考音色（视频人声 + 备用） =="
if [ -d "$PKG/参考音频" ]; then
  cp -R "$PKG/参考音频/." "$OUT/references/" 2>/dev/null || true
fi

if [ "$MODE" = "cuda" ]; then
  echo "== GPU 模式：跳过 PyTorch CPU wheel 预下载（镜像内直接装 cu124）=="
  mkdir -p "$OUT/wheels"
else
echo "== 预下载 PyTorch CPU wheel（阿里云镜像；容器里用 --find-links 离线安装，避开官方源卡死） =="
mkdir -p "$OUT/wheels"
ARCH="$(uname -m)"
BASE="https://mirrors.aliyun.com/pytorch-wheels/cpu"
if [ "$ARCH" = "arm64" ]; then
  WHEELS=("torch-2.6.0%2Bcpu-cp311-cp311-manylinux_2_28_aarch64.whl" "torchaudio-2.6.0-cp311-cp311-linux_aarch64.whl")
else
  WHEELS=("torch-2.6.0%2Bcpu-cp311-cp311-linux_x86_64.whl" "torchaudio-2.6.0-cp311-cp311-linux_x86_64.whl")
fi
for w in "${WHEELS[@]}"; do
  name="$(python3 -c "import urllib.parse,sys;print(urllib.parse.unquote(sys.argv[1]))" "$w")"
  if [ -f "$OUT/wheels/$name" ]; then echo "  已有 $name"; continue; fi
  echo "  下载 $name"
  curl -sSL --retry 3 --retry-delay 2 -o "$OUT/wheels/$name" "$BASE/$w" || echo "  ⚠️ 下载失败，容器构建时会自动回退到在线源"
done
ls -lh "$OUT/wheels" 2>/dev/null | tail -3
fi

echo "== 生成 .env（默认复用本机已有模型/权重，零下载启动） =="
cat > "$OUT/.env" <<EOF
# 复用本机已下好的模型与权重；想让它自己下载就把下面三行 *_DIR 注释掉并把 AUTO_FETCH 改成 1
PRETRAINED_DIR=$HOME/GPT-SoVITS/GPT_SoVITS/pretrained_models
G2PW_DIR=$HOME/GPT-SoVITS/GPT_SoVITS/text/G2PWModel
NLTK_DIR=$HOME/GPT-SoVITS/nltk_data
WEIGHTS_DIR=$HOME/GPT-SoVITS
PORT=8000
AUTO_FETCH=0
HF_ENDPOINT=https://hf-mirror.com
PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
TORCH_INDEX=https://mirrors.aliyun.com/pytorch-wheels/cpu
EOF

echo
echo "✅ 组装完成: $OUT"
du -sh "$OUT" 2>/dev/null || true
echo
echo "下一步："
echo "  cd \"$OUT\" && docker compose up -d --build"
echo "  然后打开 http://localhost:8000"
[ "$MODE" = "cuda" ] && echo "  （GPU 模式：需要 NVIDIA Container Toolkit；验证 docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi）"
