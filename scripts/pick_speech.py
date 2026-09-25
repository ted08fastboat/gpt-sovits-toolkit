#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从一段音频里挑出最适合当 GPT-SoVITS 参考音的连续人声片段。

用法: pick_speech.py <输入wav> <输出wav> [目标秒数=6]

策略:
  1. librosa.effects.split 找有声区间（top_db=30）
  2. 合并间隔 < 0.35 秒的相邻区间，丢弃过短的
  3. 在有声区间里滑动取「目标秒数」的窗口，挑平均能量最高的窗口
  4. 同时输出客观指标：中位基频、峰值、静音占比、音量
"""
import sys

import librosa
import numpy as np
import soundfile as sf


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    target = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0

    y, sr = sf.read(src)
    if y.ndim > 1:
        y = y.mean(1)
    y = np.asarray(y, dtype=np.float32)
    if np.abs(y).max() > 1.5:
        y = y / 32768.0
    if len(y) < sr:
        print("❌ 音频太短")
        return 1

    # 1. 有声区间
    intervals = librosa.effects.split(y, top_db=30)
    if len(intervals) == 0:
        print("❌ 没有检测到有效人声（整段接近静音？）")
        return 1
    # 2. 合并小间隙
    merged = []
    for s, e in intervals:
        if merged and s - merged[-1][1] < int(0.35 * sr):
            merged[-1][1] = e
        else:
            merged.append([s, e])
    need = int(target * sr)
    cands = [m for m in merged if m[1] - m[0] >= need]
    if not cands:
        cands = [max(merged, key=lambda m: m[1] - m[0])]
        print("⚠️ 没有找到 %g 秒的连续人声，改用最长的 %.1f 秒片段" % (target, (cands[0][1] - cands[0][0]) / sr))
        need = cands[0][1] - cands[0][0]

    # 3. 滑动窗口找能量最高的位置
    best = None
    for s, e in cands:
        seg = y[s:e]
        step = max(1, int(0.25 * sr))
        for off in range(0, max(1, len(seg) - need + 1), step):
            w = seg[off:off + need]
            rms = float(np.sqrt(np.mean(w ** 2) + 1e-12))
            peak = float(np.abs(w).max())
            if peak > 0.985:          # 尽量避开爆音
                rms *= 0.5
            if best is None or rms > best[0]:
                best = (rms, s + off, s + off + need)
    if best is None:
        print("❌ 选段失败")
        return 1
    _, a, b = best
    clip = y[a:b]

    sf.write(dst, clip, sr)

    # 4. 指标
    f0 = librosa.yin(clip, fmin=60, fmax=400, sr=sr, frame_length=2048)
    f0 = f0[np.isfinite(f0)]
    f0 = f0[(f0 > 60) & (f0 < 400)]
    med = float(np.median(f0)) if len(f0) else float("nan")
    peak = float(np.abs(clip).max())
    silence = float((np.abs(clip) < 0.005).mean())
    rms_db = 20 * np.log10(max(float(np.sqrt(np.mean(clip ** 2))), 1e-9))
    tag = "偏低(典型男声)" if med < 140 else ("中性偏低" if med < 160 else ("中性偏高" if med < 185 else "偏高(典型女声)"))

    print("✅ 选段: %d 帧起 (%.2fs ~ %.2fs, 共 %.2f 秒)" % (a, a / sr, b / sr, len(clip) / sr))
    print("   中位基频 %.1f Hz  → %s" % (med, tag))
    print("   峰值 %.3f   静音占比 %.1f%%   平均电平 %.1f dBFS" % (peak, silence * 100, rms_db))
    print("   已写出: %s" % dst)
    if peak < 0.05:
        print("   ⚠️ 音量很低，参考音太小声会影响效果，建议换一段")
    if silence > 0.35:
        print("   ⚠️ 静音占比偏高，片段里可能夹了停顿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
