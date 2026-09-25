#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 UVR5 把人声从伴奏里分离出来（HP2_all_vocals 模型），供 GPT-SoVITS 当参考音。

用法: vocals_split.py <输入wav> <输出人声wav> [模型名=HP2_all_vocals] [agg=10]
"""
import os
import shutil
import sys
import tempfile

DEST = os.path.expanduser("~/GPT-SoVITS")
sys.path.insert(0, DEST)
sys.path.insert(0, os.path.join(DEST, "GPT_SoVITS"))
os.chdir(DEST)

# tools/uvr5/webui.py 在导入时会读 sys.argv：
# argv[1]=device, argv[2]=is_half, argv[3]=port, argv[4]=is_share
sys.argv = ["uvr5", "cpu", "False", "9873", "False"]

from tools.uvr5.webui import uvr  # noqa: E402


def main():
    src = os.path.abspath(sys.argv[1])
    dst = os.path.abspath(sys.argv[2])
    model = sys.argv[3] if len(sys.argv) > 3 else "HP2_all_vocals"
    agg = int(sys.argv[4]) if len(sys.argv) > 4 else 10

    tmp = tempfile.mkdtemp(prefix="uvr_")
    inp = os.path.join(tmp, "in")
    voc = os.path.join(tmp, "vocal")
    ins = os.path.join(tmp, "ins")
    for d in (inp, voc, ins):
        os.makedirs(d, exist_ok=True)
    name = "input.wav"
    shutil.copy2(src, os.path.join(inp, name))

    print("运行 UVR5 人声分离：model=%s agg=%d" % (model, agg))
    uvr(model, inp, voc, [name], ins, agg, "wav")

    cand = [f for f in os.listdir(voc) if f.endswith(".wav")]
    if not cand:
        print("❌ 没有产出人声文件")
        return 1
    out = os.path.join(voc, sorted(cand)[-1])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(out, dst)
    print("✅ 人声已写出: %s  (%.1f KB)" % (dst, os.path.getsize(dst) / 1024))
    print("   伴奏(未使用): %s" % sorted(os.listdir(ins))[:1])
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
