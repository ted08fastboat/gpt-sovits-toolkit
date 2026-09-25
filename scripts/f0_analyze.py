#!/usr/bin/env python3
"""粗略估计语音的基频(F0)中位数，用来判断音色偏男/偏女（客观辅助，不能代替耳朵听）。"""
import sys
import numpy as np
import soundfile as sf
import librosa


def analyze(path, seconds=2.5):
    y, sr = sf.read(path)
    if y.ndim > 1:
        y = y.mean(1)
    y = np.asarray(y, dtype=np.float32)
    peak = np.abs(y).max()
    if peak > 1.5:
        y = y / 32768.0
    # 从能量最强处附近取 2.5 秒
    if len(y) > sr * seconds:
        win = int(sr * seconds)
        energy = np.convolve(np.abs(y), np.ones(win) / win, mode="same")
        c = int(np.argmax(energy))
        s = max(0, min(c - win // 2, len(y) - win))
        y = y[s:s + win]
    if np.abs(y).max() < 1e-4:
        return None
    f0 = librosa.yin(y, fmin=60, fmax=400, sr=sr, frame_length=2048)
    f0 = f0[np.isfinite(f0)]
    f0 = f0[(f0 > 60) & (f0 < 400)]
    if len(f0) == 0:
        return None
    return float(np.median(f0)), float(np.percentile(f0, 10)), float(np.percentile(f0, 90))


def tag(med):
    if med < 140:
        return "偏低（典型男声）"
    if med < 160:
        return "中性偏低（男声/低沉女声）"
    if med < 185:
        return "中性偏高"
    return "偏高（典型女声）"


if __name__ == "__main__":
    print("%-30s %8s %8s %8s  %s" % ("文件", "中位F0", "10%", "90%", "判断"))
    for p in sys.argv[1:]:
        r = analyze(p)
        name = p.split("/")[-1]
        if r is None:
            print("%-30s %8s" % (name, "无有效浊音"))
            continue
        med, p10, p90 = r
        print("%-30s %7.1fHz %7.0f %7.0f  %s" % (name[:30], med, p10, p90, tag(med)))
