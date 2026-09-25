#!/bin/bash
# 把第三方训练好的 GPT(.ckpt) + SoVITS(.pth) 权重装进 ~/GPT-SoVITS 并验证
# 用法: install_user_weights.sh [来源目录]   默认 ~/GPT-SoVITS/user_weights
set -u
DEST="$HOME/GPT-SoVITS"
SRC="${1:-$DEST/user_weights}"
PY="$DEST/venv/bin/python"

echo "===== 来源目录: $SRC ====="
shopt -s nullglob
ckpts=("$SRC"/*.ckpt "$SRC"/*/*.ckpt)
pths=("$SRC"/*.pth "$SRC"/*/*.pth)
if [ ${#ckpts[@]} -eq 0 ] && [ ${#pths[@]} -eq 0 ]; then
  echo "没有找到 .ckpt / .pth 文件"; exit 1
fi
for f in "${ckpts[@]}"; do printf 'GPT    : %s (%s)\n' "$f" "$(du -h "$f" | cut -f1)"; done
for f in "${pths[@]}";  do printf 'SoVITS : %s (%s)\n' "$f" "$(du -h "$f" | cut -f1)"; done

# ---- SoVITS 版本识别（与官方 process_ckpt.get_sovits_version_from_path_fast 一致）----
# 注意：官方标记是 ASCII 两字节（b"05"），xxd 输出的是十六进制，所以要按 3035 这种形式比对
detect_pth() {
  local f="$1" head2 size
  head2=$(xxd -p -l 2 "$f")
  case "$head2" in
    3030) echo "v1";;         # b"00"
    3031) echo "v2";;         # b"01"
    3032) echo "v3";;         # b"02"
    3033) echo "v3";;         # b"03" = v3 LoRA
    3034) echo "v4";;         # b"04"
    3035) echo "v2Pro";;      # b"05"
    3036) echo "v2ProPlus";;  # b"06"
    *)                        # 504b = "PK" 普通 torch.save，按体积判断
      size=$(stat -f %z "$f")
      if   [ "$size" -lt $((82978*1024)) ];   then echo "v1"
      elif [ "$size" -lt $((700*1024*1024)) ]; then echo "v2"
      else echo "v3"; fi;;
  esac
}
dir_for() {  # $1=version -> 权重子目录名（v1 无后缀）
  case "$1" in
    v1) echo "weights";;
    *)  echo "weights_$1";;
  esac
}

VERS=()
for f in "${pths[@]}"; do
  v=$(detect_pth "$f")
  echo "识别到 SoVITS 版本: $v  <- $(basename "$f")"
  VERS+=("$v")
done
# 取第一个 SoVITS 的版本作为这对权重的版本
PAIR_VER="${VERS[0]:-v2Pro}"
SUF=$(dir_for "$PAIR_VER")
SOVITS_DIR="$DEST/SoVITS_$SUF"
GPT_DIR="$DEST/GPT_$SUF"
mkdir -p "$SOVITS_DIR" "$GPT_DIR"

echo
echo "===== 复制权重 ====="
NEW_PTH=""
for f in "${pths[@]}"; do cp -f "$f" "$SOVITS_DIR/"; NEW_PTH="$SOVITS_DIR/$(basename "$f")"; echo "-> $NEW_PTH"; done
NEW_CKPT=""
for f in "${ckpts[@]}"; do cp -f "$f" "$GPT_DIR/"; NEW_CKPT="$GPT_DIR/$(basename "$f")"; echo "-> $NEW_CKPT"; done
[ -n "$NEW_PTH" ] || { for f in "$SOVITS_DIR"/*.pth; do NEW_PTH="$f"; done; }
[ -n "$NEW_CKPT" ] || { for f in "$GPT_DIR"/*.ckpt; do NEW_CKPT="$f"; done; }

echo
echo "===== 默认加载这对权重（写 weight.json，键名 $PAIR_VER）====="
cd "$DEST" || exit 1
PAIR_VER="$PAIR_VER" NEW_PTH="$NEW_PTH" NEW_CKPT="$NEW_CKPT" "$PY" - <<'EOF'
import json, os, re
p = "./weight.json"
rel = lambda x: os.path.relpath(x, os.getcwd())
d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"GPT": {}, "SoVITS": {}}
ver = os.environ["PAIR_VER"]
if os.environ.get("NEW_CKPT"): d.setdefault("GPT", {})[ver] = rel(os.environ["NEW_CKPT"])
if os.environ.get("NEW_PTH"):  d.setdefault("SoVITS", {})[ver] = rel(os.environ["NEW_PTH"])
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("weight.json:", json.dumps(d, ensure_ascii=False, indent=1))
EOF

echo
echo "===== WebUI 模型列表里会出现 ====="
"$PY" - <<'EOF' 2>/dev/null
from config import get_weights_names
s, g = get_weights_names()
print("SoVITS:", [x for x in s if "weights" in str(x)])
print("GPT   :", [x for x in g if "weights" in str(x)])
EOF

echo
echo "===== 用这对权重做一次真实合成验证 ====="
OUT="$DEST/test/out-user"
mkdir -p "$OUT"
version="$PAIR_VER" gpt_path="$NEW_CKPT" sovits_path="$NEW_PTH" \
PATH="$DEST/venv/bin:$PATH" PYTHONPATH="$DEST:$DEST/GPT_SoVITS" \
HF_ENDPOINT="https://hf-mirror.com" NLTK_DATA="$DEST/nltk_data" \
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 PYTORCH_ENABLE_MPS_FALLBACK=1 \
"$PY" GPT_SoVITS/inference_cli.py \
  --gpt_model "$NEW_CKPT" --sovits_model "$NEW_PTH" \
  --ref_audio "$DEST/test/ref.wav" --ref_text "$DEST/test/ref.txt" \
  --ref_language 中文 --target_text "$DEST/test/target.txt" --target_language 中文 \
  --output_path "$OUT" 2>&1 | grep -E "loading sovits|All keys|Audio saved|Error|Traceback|error" 

echo
if [ -f "$OUT/output.wav" ]; then
  echo "✅ 验证通过: $OUT/output.wav ($(du -h "$OUT/output.wav" | cut -f1))"
else
  echo "❌ 合成未产出文件，请把上面的报错发我"
fi
