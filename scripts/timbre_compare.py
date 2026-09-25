#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比较合成音频与各参考音的音色接近程度（MFCC 均值向量的距离 + 基频）。

用法: timbre_compare.py <参考A> <参考B> ... -- <被测1> <被测2> ...
输出: 每个被测音频与每个参考音的 MFCC 距离（越小越像）与中位基频
"""
import sys

import librosa
import numpy as np
import soundfile as sf


def load(path):
    y, sr = sf.read(path)
    if y.ndim > 1:
        y = y.mean(1)
    y = np.asarray(y, dtype=np.float32)
    if np.abs(y).max() > 1.5:
        y = y / 32768.0
    return y, sr


def profile(path):
    y, sr = load(path)
    # 去头尾静音
    y, _ = librosa.effects.trim(y, top_db=30)
    if len(y) < sr // 2:
        return None
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, n_fft=1024, hop_length=256)
    # 倒谱均值归一化，去掉信道/音量影响，留下音色特征
    v = mfcc.mean(axis=1)
    v = v - v.mean()
    f0 = librosa.yin(y, fmin=60, fmax=400, sr=sr, frame_length=2048)
    f0 = f0[np.isfinite(f0)]
    f0 = f0[(f0 > 60) & (f0 < 400)]
    return v, (float(np.median(f0)) if len(f0) else float("nan"))


def main():
    argv = sys.argv[1:]
    if "--" not in argv:
        print(__doc__)
        return 2
    i = argv.index("--")
    refs, tests = argv[:i], argv[i + 1:]

    rp = [(p.split("/")[-1], profile(p)) for p in refs]
    tp = [(p.split("/")[-1], profile(p)) for p in tests]
    rp = [(n, v, f) for n, (v, f) in [(n, r) for n, r in rp] if v is not None]

    print("%-34s %s" % ("被测音频", "  ".join("%-22s" % n[:22] for n, _, _ in rp)))
    print("%-34s %s" % ("", "  ".join("%-22s" % "MFCC距离/被测基频Hz" for _ in rp)))
    for name, prof in tp:
        if prof is None:
            print("%-34s (读取失败)" % name[:34])
            continue
        v, f0 = prof
        cells = []
        for rn, rv, rf in rp:
            d = float(np.linalg.norm(v - rv))
            cells.append("%6.2f / %6.1f" % (d, f0))
        print("%-34s %s" % (name[:34], "  ".join("%-22s" % c for c in cells)))
    print("\n说明：MFCC 距离越小 = 音色越接近该参考音；斜杠后是被测音频自己的中位基频(Hz)。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
