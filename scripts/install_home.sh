#!/bin/bash
# 将已验证的 GPT-SoVITS 环境安装到 ~/GPT-SoVITS
# 需要一次提权（写家目录）；脚本内部所有路径都写死为绝对路径
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$SRC/downloads/GPT-SoVITS-main"
DEST="$HOME/GPT-SoVITS"
PYSRC="$SRC/uv-python/cpython-3.11.14-macos-aarch64-none"
UV="$SRC/downloads/uv-aarch64-apple-darwin/uv"
LOG="$SRC/install-home.log"

say() { echo "[$(date '+%H:%M:%S')] $*"; }

say "== 0. 目标目录 $DEST =="
mkdir -p "$DEST"

say "== 1. 复制源码（模型目录稍后单独处理） =="
rsync -a --delete \
  --exclude 'pretrained_models/' \
  --exclude 'text/G2PWModel/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  "$STAGE/" "$DEST/"

say "== 2. 复制预训练模型（优先硬链接，省空间） =="
link_copy() {  # $1=src, $2=dst_parent
  local base; base="$(basename "$1")"
  rm -rf "$2/$base"
  if cp -Rl "$1" "$2/" 2>/dev/null; then say "hardlink $base"; else cp -R "$1" "$2/"; say "copy $base"; fi
}
link_copy "$STAGE/GPT_SoVITS/pretrained_models" "$DEST/GPT_SoVITS"
link_copy "$STAGE/GPT_SoVITS/text/G2PWModel" "$DEST/GPT_SoVITS/text"
link_copy "$SRC/models/extras/nltk_data" "$DEST"

say "== 3. 安装独立 Python 运行时 =="
rm -rf "$DEST/python"
cp -R "$PYSRC" "$DEST/python"

say "== 4. 创建虚拟环境 =="
rm -rf "$DEST/venv"
"$DEST/python/bin/python3.11" -m venv "$DEST/venv"

say "== 5. 安装依赖（复用工作区 wheel 缓存 + 清华 PyPI 镜像） =="
export UV_CACHE_DIR="$SRC/uv-cache"
export UV_PYTHON_INSTALL_DIR="$SRC/uv-python"
export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
export UV_INDEX_URL="$UV_DEFAULT_INDEX"
"$UV" pip install --python "$DEST/venv/bin/python" -r "$SRC/scripts/requirements-mac.txt"

say "== 6. 内置 ffmpeg 并建立命令链接 =="
FF="$("$DEST/venv/bin/python" -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
ln -sf "$FF" "$DEST/venv/bin/ffmpeg"

say "== 7. 安装启动脚本 / 测试素材 / 说明 =="
install -m 755 "$SRC/scripts/start-webui.sh" "$DEST/start-webui.sh"
install -m 755 "$SRC/scripts/start-api.sh" "$DEST/start-api.sh"
install -m 755 "$SRC/scripts/smoke_test.sh" "$DEST/smoke_test.sh"
printf '#!/bin/bash\ncd "$(dirname "$0")"\nexec ./start-webui.sh\n' > "$DEST/启动WebUI.command"
chmod 755 "$DEST/启动WebUI.command"
install -m 644 "$SRC/scripts/使用说明.md" "$DEST/使用说明.md"
rm -rf "$DEST/test"
cp -R "$SRC/test" "$DEST/test"
rm -rf "$DEST/test/out-v2Pro" "$DEST/test/out-v2ProPlus"

say "== 8. 冒烟测试（真实中文合成） =="
"$DEST/smoke_test.sh" "$DEST" v2Pro > "$LOG" 2>&1 && say "冒烟测试通过: $(ls -lh "$DEST/test/out-v2Pro/output.wav" | awk '{print $5}')" || { say "冒烟测试失败，见 $LOG"; tail -20 "$LOG"; exit 1; }

say "== 9. WebUI 启动检查（端口 9874） =="
cd "$DEST"
( "$DEST/start-webui.sh" > "$DEST/webui.log" 2>&1 & echo $! > "$DEST/.webui.pid" )
ok=0
for i in $(seq 1 90); do
  sleep 2
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:9874/ || true)
  if [ "$code" = "200" ]; then ok=1; say "WebUI HTTP 200 (第 ${i} 次探测)"; break; fi
done
kill "$(cat "$DEST/.webui.pid")" 2>/dev/null || true
pkill -f "webui.py zh_CN" 2>/dev/null || true
rm -f "$DEST/.webui.pid"
if [ "$ok" = "1" ]; then say "WebUI 检查通过"; else say "WebUI 未在 180 秒内就绪，见 $DEST/webui.log"; tail -20 "$DEST/webui.log" || true; fi

say "== 完成，安装位置: $DEST =="
du -sh "$DEST" 2>/dev/null || true
