#!/bin/bash
# 下载 G2PWModel（中文拼音消歧，必需）、nltk_data（英文 G2P 备用）、open_jtalk 词典（日文备用）
set -u
ROOT="/Users/zhengjiezhou/Documents/deepseek agent/gptsovits"
STAGE="$ROOT/models"
HF="https://hf-mirror.com/XXXXRT/GPT-SoVITS-Pretrained/resolve/main"
mkdir -p "$STAGE/extras"

for f in G2PWModel.zip nltk_data.zip open_jtalk_dic_utf_8-1.11.tar.gz; do
  out="$STAGE/extras/$f"
  if [ -f "$out" ]; then echo "SKIP $f"; continue; fi
  echo "GET $f"
  curl -sSL --fail --retry 3 --retry-delay 3 -m 3600 -C - -o "$out.part" "$HF/$f" \
    && mv -f "$out.part" "$out" && echo "OK $f ($(du -h "$out" | cut -f1))" || echo "FAIL $f"
done

# 解压 G2PWModel 到 text 目录
cd "$STAGE/extras" || exit 1
if [ -f G2PWModel.zip ] && [ ! -d G2PWModel ]; then
  unzip -q -o G2PWModel.zip && echo "UNZIP G2PWModel ok"
  ls
fi
if [ -f nltk_data.zip ] && [ ! -d nltk_data ]; then
  unzip -q -o nltk_data.zip && echo "UNZIP nltk_data ok"
fi
echo "=== extras ==="; du -sh "$STAGE/extras"
