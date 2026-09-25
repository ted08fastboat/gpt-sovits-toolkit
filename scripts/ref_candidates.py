#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从指定时间区间里各取一段参考音频，并识别文字（一次加载模型，处理多个候选）。

用法:
  ref_candidates.py --wav full16k.wav --outdir 目录 --pick 34.40:56.43 --pick 3.93:20.48 [--clip-sec 6]
输出:
  outdir/候选A.wav ... 以及每段的 中位基频 / 峰值 / 识别文字
"""
import argparse
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

TARGET_SR = 32000
LABELS = "ABCDEFGH"


def load_mono(path, sr=16000):
    y, got = sf.read(path)
    if y.ndim > 1:
        y = y.mean(1)
    y = np.asarray(y, dtype=np.float32)
    if np.abs(y).max() > 1.5:
        y = y / 32768.0
    if got != sr:
        y = librosa.resample(y, orig_sr=got, target_sr=sr)
    return y, sr


def best_window(seg, need, sr):
    if len(seg) <= need:
        return seg
    step = max(1, int(0.25 * sr))
    best, best_rms = 0, -1.0
    for off in range(0, len(seg) - need + 1, step):
        rms = float(np.sqrt(np.mean(seg[off:off + need] ** 2) + 1e-12))
        if rms > best_rms:
            best, best_rms = off, rms
    return seg[best:best + need]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--pick", action="append", required=True, help="起始:结束（秒），可多次")
    ap.add_argument("--clip-sec", type=float, default=6.0)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    y, sr = load_mono(args.wav)
    need = int(args.clip_sec * sr)

    clips = []
    for i, spec in enumerate(args.pick):
        a, b = [float(x) for x in spec.split(":")]
        seg = y[int(a * sr):int(b * sr)]
        if len(seg) < int(1.5 * sr):
            print("跳过 %.2fs~%.2fs：太短" % (a, b))
            continue
        clip = best_window(seg, need, sr)
        label = LABELS[i] if i < len(LABELS) else str(i)
        out = os.path.join(args.outdir, "候选%s.wav" % label)
        out32 = librosa.resample(clip, orig_sr=sr, target_sr=TARGET_SR) if sr != TARGET_SR else clip
        sf.write(out, out32, TARGET_SR)
        f0 = librosa.yin(clip, fmin=60, fmax=400, sr=sr, frame_length=2048)
        f0 = f0[np.isfinite(f0)]
        f0 = f0[(f0 > 60) & (f0 < 400)]
        med = float(np.median(f0)) if len(f0) else float("nan")
        tag = "偏低(典型男声)" if med < 140 else ("中性偏低" if med < 160 else ("中性偏高" if med < 185 else "偏高(典型女声)"))
        clips.append((label, spec, out, clip, med, tag))
        print("候选%s  %s 秒  → %s" % (label, spec, out))
        print("   中位基频 %.1f Hz → %s  峰值 %.3f  静音占比 %.1f%%"
              % (med, tag, float(np.abs(clip).max()), float((np.abs(clip) < 0.005).mean()) * 100))

    if not clips:
        print("没有可用候选")
        return 1

    print("\n加载 SenseVoiceSmall 识别各候选文字…")
    asr = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", device="cpu", disable_update=True)
    for label, spec, out, clip, med, tag in clips:
        tmp = "/tmp/_cand_%s.wav" % label
        sf.write(tmp, clip, sr)
        r = asr.generate(input=tmp, language="zh", use_itn=True)
        text = rich_transcription_postprocess(r[0]["text"]).strip() if r else ""
        with open(os.path.join(args.outdir, "候选%s.txt" % label), "w", encoding="utf-8") as f:
            f.write(text)
        print("\n候选%s  %s 秒  基频 %.0fHz" % (label, spec, med))
        print("   文字: %s" % text)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
