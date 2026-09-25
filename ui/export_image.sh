#!/bin/bash
# 把构建好的镜像导出成离线包，方便拷到别的机器（不需要重新构建、不需要联网装依赖）
#
# 用法:
#   ./export_image.sh                # 导出镜像 + 权重 + 参考音色（约 1.6GB，模型让他们首次启动自动下）
#   ./export_image.sh --with-models  # 连预训练模型一起打包（+3.5GB，目标机器完全离线可用）
set -eu
UI_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER="${DOCKER:-docker}"
IMG="${IMAGE:-gptsovits-voiceui:latest}"
OUT="${OUT_DIR:-$HOME/Desktop/gptsovits-voiceui-离线镜像包}"
WITH_MODELS=0
[ "${1:-}" = "--with-models" ] && WITH_MODELS=1

echo "== 检查镜像 =="
ARCH="$("$DOCKER" image inspect "$IMG" --format '{{.Architecture}}')"
SIZE="$("$DOCKER" image inspect "$IMG" --format '{{.Size}}')"
echo "镜像 $IMG  架构 $ARCH  大小 $((SIZE/1024/1024)) MB"

mkdir -p "$OUT/models/pretrained_models" "$OUT/models/G2PWModel" "$OUT/models/nltk_data" \
         "$OUT/weights" "$OUT/references" "$OUT/outputs"

echo "== 1/5 导出镜像（gzip 压缩，约 1~3 分钟）=="
TARBALL="$OUT/gptsovits-voiceui-${ARCH}.tar.gz"
rm -f "$OUT"/gptsovits-voiceui-*.tar.gz
"$DOCKER" save "$IMG" | gzip -1 > "$TARBALL"
echo "  -> $TARBALL  $(du -h "$TARBALL" | cut -f1)"

echo "== 2/5 写入目标机器用的 docker-compose.yml（直接用导入的镜像，不再 build）=="
cat > "$OUT/docker-compose.yml" <<'YML'
services:
  voiceui:
    image: gptsovits-voiceui:latest
    ports:
      - "${PORT:-8000}:8000"
    environment:
      PORT: "8000"
      AUTO_FETCH: "${AUTO_FETCH:-1}"      # 1=首次启动自动下模型；模型目录已备好就设 0
      HF_ENDPOINT: "${HF_ENDPOINT:-https://hf-mirror.com}"
      PRELOAD: "1"
      version: "v2Pro"
    volumes:
      # 想直接用机器上已有的模型目录，就在 .env 里填绝对路径
      - ${PRETRAINED_DIR:-./models/pretrained_models}:/repo/GPT_SoVITS/pretrained_models
      - ${G2PW_DIR:-./models/G2PWModel}:/repo/GPT_SoVITS/text/G2PWModel
      - ${NLTK_DIR:-./models/nltk_data}:/repo/nltk_data
      - ${WEIGHTS_DIR:-./weights}:/data/weights
      - ./references:/data/references
      - ./outputs:/data/outputs
    restart: unless-stopped
YML

echo "== 3/5 写入一键导入脚本 =="
cat > "$OUT/load_and_run.sh" <<'SH'
#!/bin/bash
set -eu
cd "$(dirname "$0")"
TARBALL="$(ls gptsovits-voiceui-*.tar.gz 2>/dev/null | head -1)"
[ -n "$TARBALL" ] || { echo "❌ 找不到镜像文件 gptsovits-voiceui-*.tar.gz"; exit 1; }
echo "导入镜像（3.9GB，约 1~2 分钟）…"
gunzip -c "$TARBALL" | docker load
mkdir -p models/pretrained_models models/G2PWModel models/nltk_data weights references outputs
echo "启动容器…"
docker compose up -d
sleep 5
docker compose ps
echo
echo "✅ 打开 http://localhost:8000 使用（首次启动会自动下载模型，日志：docker compose logs -f）"
SH
chmod +x "$OUT/load_and_run.sh"

cat > "$OUT/load_and_run.bat" <<'BAT'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set TARBALL=
for %%f in (gptsovits-voiceui-*.tar.gz) do set TARBALL=%%f
if "%TARBALL%"=="" (echo 找不到镜像文件 gptsovits-voiceui-*.tar.gz & pause & exit /b 1)
echo 导入镜像（3.9GB，约 1~2 分钟）...
docker load -i "%TARBALL%"
if not exist models\pretrained_models mkdir models\pretrained_models
if not exist models\G2PWModel mkdir models\G2PWModel
if not exist models\nltk_data mkdir models\nltk_data
if not exist weights mkdir weights
if not exist references mkdir references
if not exist outputs mkdir outputs
docker compose up -d
docker compose ps
echo.
echo 打开 http://localhost:8000 使用（首次启动会自动下载模型）
pause
BAT

echo "== 4/5 带上音色权重与参考音色 =="
for d in GPT_weights_v2Pro SoVITS_weights_v2Pro GPT_weights_v2 SoVITS_weights_v2; do
  if [ -d "$HOME/GPT-SoVITS/$d" ]; then
    mkdir -p "$OUT/weights/$d"
    cp -f "$HOME/GPT-SoVITS/$d"/*.ckpt "$HOME/GPT-SoVITS/$d"/*.pth "$OUT/weights/$d/" 2>/dev/null || true
    echo "  weights/$d"
  fi
done
if [ -d "$UI_DIR/build/references" ]; then
  cp -R "$UI_DIR/build/references/." "$OUT/references/" 2>/dev/null || true
  echo "  references/（视频人声等参考音色）"
fi

if [ "$WITH_MODELS" = "1" ]; then
  echo "== 4.5/5 复制预训练模型（约 3.5GB，请耐心等）=="
  cp -R "$HOME/GPT-SoVITS/GPT_SoVITS/pretrained_models/." "$OUT/models/pretrained_models/" 2>/dev/null || true
  cp -R "$HOME/GPT-SoVITS/GPT_SoVITS/text/G2PWModel/." "$OUT/models/G2PWModel/" 2>/dev/null || true
  cp -R "$HOME/GPT-SoVITS/nltk_data/." "$OUT/models/nltk_data/" 2>/dev/null || true
fi

echo "== 5/5 写入说明 =="
cat > "$OUT/README.md" <<'MD'
# 声音工坊（GPT-SoVITS 语音克隆 UI）· 离线镜像包

## 目标机器需要什么
- 已装 Docker（Docker Desktop / Docker Engine + compose 插件）
- 磁盘空间：镜像约 4GB + 模型约 3.5GB + 你的音频
- **架构要一致**：本包是在 Apple Silicon（arm64）上导出的；导到 x86_64 服务器上会提示镜像架构不匹配。
  需要在 x86_64 上跑的话，把那台机器的源码目录拷过去，用 `docker compose up -d --build` 自己构建一份。

## 三步跑起来
```bash
# Linux / macOS
./load_and_run.sh

# Windows：双击 load_and_run.bat
```
然后打开 **http://localhost:8000**。首次启动若 `models/` 是空的，容器会自动从 hf-mirror 下载
预训练模型（约 3.2GB，日志 `docker compose logs -f` 可看进度）。

## 目录说明
```
gptsovits-voiceui-<arch>.tar.gz   镜像（docker load 导入）
docker-compose.yml                目标机器用的编排文件（不 build，直接用镜像）
load_and_run.sh / .bat            一键导入并启动
weights/                          音色权重（GPT_weights_* / SoVITS_weights_*）
references/                       参考音色（wav + 同名 txt）
outputs/                          合成结果（也在这里取文件）
models/                           预训练模型（为空则首次启动自动下载）
```

## 常用命令
```bash
docker compose logs -f      # 看日志（模型下载/加载进度）
docker compose restart      # 重启
docker compose down         # 停止
docker compose up -d        # 再启动
```

## 注意
- 音色权重可能包含他人声音，转发/使用前请确认授权，不得用于冒充他人。
- 想换端口：在 `.env` 里写 `PORT=8001`（没有该文件就新建）。
- 想复用目标机器上已有的模型/权重（省掉下载）：在 `.env` 里写
  `PRETRAINED_DIR=/绝对路径/pretrained_models`、`G2PW_DIR=...`、`NLTK_DIR=...`、`WEIGHTS_DIR=/绝对路径/父目录`，
  并把 `AUTO_FETCH=0`。
- 想彻底离线：把模型目录（pretrained_models / G2PWModel / nltk_data）也拷进 `models/`，
  并把 `AUTO_FETCH` 设为 `0`。
MD

echo
echo "✅ 导出完成: $OUT"
du -sh "$OUT"/* | sort -h
echo
echo "拷给对方后，对方执行 ./load_and_run.sh（Windows 双击 load_and_run.bat）"
