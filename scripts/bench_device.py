#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一句台词下比较 CPU / MPS 的合成耗时（加载一次、跑多次取中位）。"""
import glob
import os
import sys
import time

REPO = os.path.expanduser("~/GPT-SoVITS")
UI_APP = "/Users/zhengjiezhou/Documents/deepseek agent/gptsovits/ui/app"
sys.path.insert(0, UI_APP)
import synth  # noqa: E402

TEXT = "这是一句用来测试推理速度的台词，长度大约二十个字左右。"
REF_WAV = os.path.join(REPO, "test", "ref.wav")
REF_TXT = os.path.join(REPO, "test", "ref.txt")
OUT = "/tmp/bench_%s" % os.environ.get("DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)


def find(pat):
    hits = sorted(glob.glob(os.path.join(REPO, pat)))
    return hits[0] if hits else None


gpt = find("GPT_weights_v2Pro/*.ckpt") or find("GPT_weights_v2/*.ckpt")
sovits = find("SoVITS_weights_v2Pro/*.pth") or find("SoVITS_weights_v2/*.pth")
ref_text = open(REF_TXT, encoding="utf-8").read().strip()

eng = synth.Engine(REPO)
t0 = time.time()
eng.preload()
load = time.time() - t0
print("设备=%s | 模型加载 %.1fs | 权重=%s + %s" % (os.environ.get("DEVICE", "auto"), load,
                                                 os.path.basename(gpt), os.path.basename(sovits)))

lat = []
for i in range(3):
    t = time.time()
    audio, sr = eng.synth(TEXT, REF_WAV, ref_text, gpt, sovits, variant="默认")
    dt = time.time() - t
    dur = len(audio) / sr
    lat.append(dt)
    eng.save_wav(audio, sr, os.path.join(OUT, "run%d.wav" % (i + 1)))
    print("  第%d次: 耗时 %5.2fs  音频 %4.2fs  RTF=%.2f  峰值 %.3f"
          % (i + 1, dt, dur, dt / dur, float(abs(audio).max())))
print("中位耗时 %.2fs（3 次: %s）" % (sorted(lat)[1], ", ".join("%.2f" % x for x in lat)))
sys.stdout.flush()
os._exit(0)
