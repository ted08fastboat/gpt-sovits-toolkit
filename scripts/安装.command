#!/bin/bash
# ===============================================================
#  GPT-SoVITS 离线整合包 · 安装器（Apple Silicon Mac）
#  双击运行：把环境装到 ~/GPT-SoVITS，自动修复路径，并做一次合成自检
# ===============================================================
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/GPT-SoVITS"
OLD_PREFIX="/Users/zhengjiezhou/GPT-SoVITS"

echo "=============================================================="
echo "  GPT-SoVITS 离线整合包 · 安装程序"
echo "=============================================================="
echo "包目录  : $HERE"
echo "安装到  : $TARGET"
echo

# ---------- 0. 平台检查 ----------
if [ "$(uname -s)" != "Darwin" ]; then
  echo "❌ 这个包是 macOS 版，当前系统是 $(uname -s)。"; read -r -p "按回车关闭…" _; exit 1
fi
ARCH="$(uname -m)"
if [ "$ARCH" != "arm64" ]; then
  echo "❌ 这个包只支持 Apple Silicon（M 系列，arm64），当前是 $ARCH。"
  echo "   Intel Mac / Windows 需要单独的包，请找打包的人要对应版本。"
  read -r -p "按回车关闭…" _; exit 1
fi
FREE_GB=$(( $(df -g "$HOME" | awk 'NR==2{print $4}') ))
echo "系统    : macOS $(sw_vers -productVersion) / $ARCH"
echo "可用空间: ${FREE_GB} GB"
if [ "$FREE_GB" -lt 8 ]; then
  echo "❌ 可用空间不足 8GB，至少需要约 6GB。"; read -r -p "按回车关闭…" _; exit 1
fi
echo

# ---------- 1. 解除下载隔离属性 ----------
xattr -dr com.apple.quarantine "$HERE" 2>/dev/null || true

# ---------- 2. 复制环境 ----------
SRC="$HERE/GPT-SoVITS"
if [ ! -d "$SRC" ]; then
  echo "❌ 包内找不到 GPT-SoVITS 目录，压缩包可能没解压完整。"
  read -r -p "按回车关闭…" _; exit 1
fi
if [ -e "$TARGET" ]; then
  echo "⚠️  $TARGET 已存在。"
  read -r -p "输入 y 回车 = 备份旧目录后覆盖；直接回车 = 退出：" ans
  if [ "${ans:-}" != "y" ]; then echo "已取消。"; read -r -p "按回车关闭…" _; exit 1; fi
  mv "$TARGET" "$TARGET.bak-$(date +%Y%m%d-%H%M%S)"
  echo "旧目录已备份为 $TARGET.bak-…"
fi
echo "正在复制文件（约 5GB，机械硬盘可能较慢）…"
ditto "$SRC" "$TARGET" || { echo "❌ 复制失败"; read -r -p "按回车关闭…" _; exit 1; }
echo "✅ 复制完成"

# ---------- 3. 修复 venv 里的绝对路径 ----------
echo
echo "正在修复 Python 环境路径…"
[ -f "$TARGET/venv/pyvenv.cfg" ] && sed -i '' "s|$OLD_PREFIX|$TARGET|g" "$TARGET/venv/pyvenv.cfg"
# venv/bin 下的入口脚本 shebang、activate 脚本里的 VIRTUAL_ENV 等
grep -rl "$OLD_PREFIX" "$TARGET/venv/bin" 2>/dev/null | while IFS= read -r f; do
  sed -i '' "s|$OLD_PREFIX|$TARGET|g" "$f" 2>/dev/null || true
done
# site-packages 里少数含路径的文本文件（如 users.pth）
grep -rl "$OLD_PREFIX" "$TARGET/venv/lib" --include="*.pth" --include="*.cfg" --include="*.pth.txt" 2>/dev/null | while IFS= read -r f; do
  sed -i '' "s|$OLD_PREFIX|$TARGET|g" "$f" 2>/dev/null || true
done
# 重建解释器与 ffmpeg 软链接
ln -sfn "$TARGET/python/bin/python3.11" "$TARGET/venv/bin/python3.11"
ln -sfn "python3.11" "$TARGET/venv/bin/python"
FFBIN=$(ls "$TARGET"/venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-* 2>/dev/null | head -1)
[ -n "$FFBIN" ] && ln -sfn "$FFBIN" "$TARGET/venv/bin/ffmpeg"
echo "✅ 路径修复完成"

# ---------- 4. 自检 ----------
echo
echo "正在做一次合成自检（CPU 推理，约 1 分钟）…"
printf '%s' "安装完成，现在可以用这个声音说话了。" > "$TARGET/test/verify.txt"
if ( cd "$TARGET" && env PATH="$TARGET/venv/bin:$PATH" PYTHONPATH="$TARGET:$TARGET/GPT_SoVITS" \
      HF_ENDPOINT="https://hf-mirror.com" NLTK_DATA="$TARGET/nltk_data" \
      TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 PYTORCH_ENABLE_MPS_FALLBACK=1 language=zh_CN \
      "$TARGET/venv/bin/python" "$TARGET/tts_clone.py" \
        --text-file "$TARGET/test/verify.txt" --out-dir "$TARGET/test/out-verify" \
        --ref-wav "$TARGET/test/ref.wav" --ref-text-file "$TARGET/test/ref.txt" \
        --variants 1 --prefix verify 2>&1 | tail -3 ) && [ -f "$TARGET/test/out-verify/verify_v1-默认.wav" ]; then
  echo "✅ 自检通过：$TARGET/test/out-verify/verify_v1-默认.wav"
  afplay "$TARGET/test/out-verify/verify_v1-默认.wav" 2>/dev/null || true
else
  echo "⚠️ 自检没有生成音频，请把上面的输出发给打包的人。"
fi

# ---------- 5. 桌面包 ----------
PKG="$HERE/GPT-SoVITS一键克隆"
if [ -d "$PKG" ]; then
  DST="$HOME/Desktop/GPT-SoVITS一键克隆"
  [ -e "$DST" ] && mv "$DST" "$DST.bak-$(date +%Y%m%d-%H%M%S)"
  ditto "$PKG" "$DST"
  echo "✅ 一键克隆工具已放到桌面：$DST"
fi

echo
echo "=============================================================="
echo "  安装完成"
echo "=============================================================="
echo "  启动 WebUI : 双击桌面「GPT-SoVITS WebUI.command」"
echo "               或终端运行 $TARGET/start-webui.sh"
echo "  一键克隆   : 双击桌面「GPT-SoVITS一键克隆/一键克隆.command」"
echo "  使用说明   : $TARGET/使用说明.md"
echo "  （本整合包已含全部模型与依赖，可完全离线运行）"
echo
read -r -p "按回车关闭窗口…" _
