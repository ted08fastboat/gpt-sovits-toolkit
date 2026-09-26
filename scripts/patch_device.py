#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 GPT-SoVITS 的推理路径加上 DEVICE 环境变量支持（cpu / cuda / mps）。

背景：官方 GPT_SoVITS/inference_webui.py 里设备判断写死为
    device = "cuda" if torch.cuda.is_available() else "cpu"
所以 Apple Silicon（MPS 可用）上也只会走 CPU。本脚本把它改成：

    DEVICE=cpu|cuda|mps  显式指定（不设则保持原逻辑）
    is_half 依旧只在 CUDA 下为 True（MPS/CPU 走 fp32，避免 fp16 算子问题）

用法：
    python patch_device.py /path/to/GPT-SoVITS          # 打补丁（自动备份）
    python patch_device.py /path/to/GPT-SoVITS --revert  # 还原备份

打完后可用：
    DEVICE=mps PYTORCH_ENABLE_MPS_FALLBACK=1 python tts_clone.py ...
"""
import argparse
import os
import shutil
import sys

TARGET_REL = os.path.join("GPT_SoVITS", "inference_webui.py")
BAK_SUFFIX = ".bak-device"

OLD = '''if torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"'''

NEW = '''# --- patch_device.py: 支持 DEVICE 环境变量（cpu / cuda / mps）---
_device_env = os.environ.get("DEVICE", "").strip().lower()
if _device_env in ("cuda", "mps", "cpu"):
    device = _device_env
elif torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"
print("推理设备:", device, "(可用: cuda=%s, mps=%s)" % (
    torch.cuda.is_available(),
    getattr(getattr(torch, "backends", None), "mps", None) and torch.backends.mps.is_available(),
))
# --- /patch_device.py ---'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="GPT-SoVITS 仓库根目录")
    ap.add_argument("--revert", action="store_true", help="从备份还原")
    args = ap.parse_args()

    path = os.path.join(os.path.abspath(args.repo), TARGET_REL)
    bak = path + BAK_SUFFIX
    if not os.path.exists(path):
        print("❌ 找不到 %s" % path)
        return 1

    if args.revert:
        if not os.path.exists(bak):
            print("❌ 没有备份可还原: %s" % bak)
            return 1
        shutil.copy2(bak, path)
        print("✅ 已还原: %s" % path)
        return 0

    s = open(path, encoding="utf-8").read()
    if "patch_device.py: 支持 DEVICE 环境变量" in s:
        print("ℹ️  已经打过补丁，无需重复")
        return 0
    if OLD not in s:
        print("❌ 未找到官方设备判断代码（可能是版本不同），请手动检查 %s" % path)
        print("   期望片段:\n%s" % OLD)
        return 1

    shutil.copy2(path, bak)
    open(path, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
    print("✅ 已打补丁: %s" % path)
    print("   备份: %s" % bak)
    print("   用法: DEVICE=mps PYTORCH_ENABLE_MPS_FALLBACK=1 ...（或 DEVICE=cuda / DEVICE=cpu）")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
