#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从视频/长音频里挑出「干净人声」做参考音 —— 以 ASR 结果为判据。

流程：
  1. fsmn-vad 找语音区间，取最长的若干段
  2. 每段里滑 8 秒窗口（或整段）
  3. 对每个窗口跑 SenseVoiceSmall：
       · 结果带 🎼 等音乐/事件标记 → 淘汰（说明这段主要是音乐/伴奏）
       · 文字太短、或某个字重复超过 5 次 → 淘汰（乱码特征）
  4. 在通过筛选的窗口里，选识别文字最长的一个
  5. 写出 32k 参考音 + ref.txt

用法:
  ref_pick_asr.py --wav 16k.wav --clip-out ref.wav [--text-out ref.txt] [--clip-sec 8]
"""
import argparse
import os
import re
import sys

import librosa
import numpy as np
import soundfile as sf
from funasr import AutoModel

TARGET_SR = 32000
MUSIC_MARKS = ("🎼", "🎵", "🎶", "🎤", "😭", "😆")


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


def cjk_len(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def looks_garbage(text):
    if cjk_len(text) < 5:
        return True
    for ch in set(text):
        if text.count(ch) > 5 and ch.strip():
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--clip-out", required=True)
    ap.add_argument("--text-out")
    ap.add_argument("--clip-sec", type=float, default=8.0)
    args = ap.parse_args()

    y, sr = load_mono(args.wav)
    print("音频 %.1f 秒 @ %d Hz" % (len(y) / sr, sr))

    print("加载 fsmn-vad …")
    vad = AutoModel(model="fsmn-vad", device="cpu", disable_update=True)
    res = vad.generate(input=args.wav)
    intervals = []
    for item in res:
        for seg in item.get("value", []):
            if isinstance(seg, (list, tuple)) and len(seg) == 2:
                intervals.append((float(seg[0]), float(seg[1])))
    intervals.sort(key=lambda x: -(x[1] - x[0]))
    print("语音段 %d 个，最长的 5 段：%s" % (
        len(intervals), ["%.1f-%.1fs(%.1fs)" % (a / 1000, b / 1000, (b - a) / 1000) for a, b in intervals[:5]]))

    need = int(args.clip_sec * sr)
    cands = []   # (start_sec, window)
    for a, b in intervals[:6]:
        seg = y[int(a / 1000 * sr):int(b / 1000 * sr)]
        if len(seg) < int(2.0 * sr):
            continue
        if len(seg) <= need:
            cands.append((a / 1000, seg))
        else:
            step = max(1, int((len(seg) - need) // 2)) if len(seg) > need else need
            for off in range(0, len(seg) - need + 1, max(1, step)):
                cands.append(((a + off / sr * 1000) / 1000, seg[off:off + need]))
    print("待评估窗口 %d 个" % len(cands))
    if not cands:
        return 1

    print("加载 SenseVoiceSmall（缓存已存在，秒开）…")
    asr = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", device="cpu", disable_update=True)
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        clean = rich_transcription_postprocess
    except Exception:  # noqa: BLE001
        clean = lambda s: s  # noqa: E731

    results = []
    for i, (start, win) in enumerate(cands, 1):
        tmp = "/tmp/_pick_%d.wav" % i
        sf.write(tmp, win if sr == 16000 else librosa.resample(win, orig_sr=sr, target_sr=16000), 16000)
        r = asr.generate(input=tmp, language="zh", use_itn=True)
        raw = r[0]["text"] if r else ""
        text = clean(raw).strip()
        f0 = librosa.yin(win, fmin=60, fmax=400, sr=sr, frame_length=2048)
        f0 = f0[np.isfinite(f0)]
        f0 = f0[(f0 > 60) & (f0 < 400)]
        med = float(np.median(f0)) if len(f0) else float("nan")
        bad_music = any(m in raw for m in MUSIC_MARKS)
        bad_text = looks_garbage(text)
        flag = "淘汰(音乐)" if bad_music else ("淘汰(乱码)" if bad_text else "候选")
        print("  [%d] %6.2fs 起 %.1fs 基频%.0fHz  %-10s %s" % (i, start, len(win) / sr, med, flag, text[:36]))
        if not bad_music and not bad_text:
            results.append((cjk_len(text), start, win, text, med, raw))

    if not results:
        print("\n❌ 所有窗口都被判为音乐/乱码。这段音频可能整段都带强伴奏，")
        print("   建议：换视频里有清唱/纯说话的片段，或先用 UVR5（WebUI 里那个人声分离标签页）分离人声。")
        return 1

    results.sort(key=lambda x: -x[0])
    _, start, win, text, med, raw = results[0]
    tag = "偏低(典型男声)" if med < 140 else ("中性偏低" if med < 160 else ("中性偏高" if med < 185 else "偏高(典型女声)"))
    out = librosa.resample(win, orig_sr=sr, target_sr=TARGET_SR) if sr != TARGET_SR else win
    peak = float(np.abs(out).max())
    if 0 < peak < 0.7:
        out = out * (0.85 / peak)
    os.makedirs(os.path.dirname(os.path.abspath(args.clip_out)), exist_ok=True)
    sf.write(args.clip_out, out, TARGET_SR)
    print("\n✅ 选定 %.2fs 起、%.1f 秒  基频 %.1f Hz → %s" % (start, len(win) / sr, med, tag))
    print("   文字(%d 字): %s" % (cjk_len(text), text))
    print("   已写出参考音: %s" % args.clip_out)
    if args.text_out:
        with open(args.text_out, "w", encoding="utf-8") as f:
            f.write(text)
        print("   已写出文本: %s" % args.text_out)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
