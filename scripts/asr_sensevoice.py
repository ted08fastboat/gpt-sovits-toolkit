#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 funasr 的 fsmn-vad + SenseVoiceSmall：对音频做语音活动检测，挑出人声片段并识别文字。

用法:
  asr_sensevoice.py --wav full16k.wav [--clip-out ref.wav] [--clip-sec 6] [--text-out ref.txt]
                   [--list-only]

流程：
  1. fsmn-vad 找语音区间（毫秒时间戳）——比按音量选段可靠，能跳过纯音乐段
  2. 选最长的语音区间（长度不足则取最长者），在其中取 --clip-sec 秒窗口
  3. 用 SenseVoiceSmall 识别该窗口文字（rich_transcription_postprocess 清洗标记）
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
EXPECT_SR = 16000


def load_mono(path, sr=None):
    y, got = sf.read(path)
    if y.ndim > 1:
        y = y.mean(1)
    y = np.asarray(y, dtype=np.float32)
    if np.abs(y).max() > 1.5:
        y = y / 32768.0
    if sr and got != sr:
        y = librosa.resample(y, orig_sr=got, target_sr=sr)
        got = sr
    return y, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True, help="16k 单声道整段音频")
    ap.add_argument("--clip-out", help="挑出的参考音频输出路径（32k 单声道）")
    ap.add_argument("--clip-sec", type=float, default=6.0)
    ap.add_argument("--text-out", help="识别文字输出路径")
    ap.add_argument("--list-only", action="store_true", help="只打印语音区间")
    args = ap.parse_args()

    y, sr = load_mono(args.wav, EXPECT_SR)
    print("音频时长 %.1f 秒，采样率 %d" % (len(y) / sr, sr))

    print("加载 fsmn-vad …")
    vad = AutoModel(model="fsmn-vad", device="cpu", disable_update=True)
    res = vad.generate(input=args.wav)
    intervals = []
    for item in res:
        for seg in item.get("value", []):
            if isinstance(seg, (list, tuple)) and len(seg) == 2:
                intervals.append((float(seg[0]), float(seg[1])))
    if not intervals:
        print("❌ VAD 没有检测到语音段")
        return 1

    intervals.sort()
    print("\n检测到 %d 个语音段：" % len(intervals))
    for i, (a, b) in enumerate(intervals, 1):
        dur = (b - a) / 1000.0
        print("  %2d) %7.2fs ~ %7.2fs  时长 %5.2fs" % (i, a / 1000, b / 1000, dur))
    if args.list_only:
        return 0

    # 选最长且足够长的段；优先 >= 目标时长
    enough = [x for x in intervals if (x[1] - x[0]) / 1000.0 >= args.clip_sec]
    cand = max(enough or intervals, key=lambda x: x[1] - x[0])
    a, b = cand
    seg = y[int(a / 1000 * sr):int(b / 1000 * sr)]
    need = int(args.clip_sec * sr)
    if len(seg) <= need:
        clip = seg
    else:
        # 取能量最高的窗口
        step = max(1, int(0.25 * sr))
        best, best_rms = 0, -1.0
        for off in range(0, len(seg) - need + 1, step):
            rms = float(np.sqrt(np.mean(seg[off:off + need] ** 2) + 1e-12))
            if rms > best_rms:
                best, best_rms = off, rms
        clip = seg[best:best + need]

    print("\n采用区间: %.2fs ~ %.2fs  → 取 %.2f 秒" % (a / 1000, b / 1000, len(clip) / sr))

    if args.clip_out:
        out = librosa.resample(clip, orig_sr=sr, target_sr=TARGET_SR) if sr != TARGET_SR else clip
        os.makedirs(os.path.dirname(os.path.abspath(args.clip_out)), exist_ok=True)
        sf.write(args.clip_out, out, TARGET_SR)
        peak = float(np.abs(clip).max())
        f0 = librosa.yin(clip, fmin=60, fmax=400, sr=sr, frame_length=2048)
        f0 = f0[np.isfinite(f0)]
        f0 = f0[(f0 > 60) & (f0 < 400)]
        med = float(np.median(f0)) if len(f0) else float("nan")
        tag = "偏低(典型男声)" if med < 140 else ("中性偏低" if med < 160 else ("中性偏高" if med < 185 else "偏高(典型女声)"))
        print("已写出参考音频: %s" % args.clip_out)
        print("  中位基频 %.1f Hz → %s   峰值 %.3f   静音占比 %.1f%%"
              % (med, tag, peak, float((np.abs(clip) < 0.005).mean()) * 100))

    print("\n加载 SenseVoiceSmall（首次会从 ModelScope 下载，约 900MB）…")
    asr = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", device="cpu", disable_update=True)
    tmp = "/tmp/_asr_clip16k.wav"
    sf.write(tmp, clip if sr == EXPECT_SR else librosa.resample(clip, orig_sr=sr, target_sr=EXPECT_SR), EXPECT_SR)
    r = asr.generate(input=tmp, language="zh", use_itn=True)
    raw = r[0]["text"] if r else ""
    text = rich_transcription_postprocess(raw).strip()
    print("识别原文: %s" % raw)
    print("清洗结果: %s" % text)
    if args.text_out and text:
        with open(args.text_out, "w", encoding="utf-8") as f:
            f.write(text)
        print("已写出文本: %s" % args.text_out)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
