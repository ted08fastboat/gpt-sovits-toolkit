#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从视频/长音频里自动挑一段最像「纯人声」的片段做 GPT-SoVITS 参考音。

比单纯按音量选段更靠谱，思路：
  1. fsmn-vad 找出语音区间（顺带跳过纯音乐段）
  2. 在每个语音区间里滑窗（默认 8 秒），给每个窗口打分：
        score = 高频能量占比(300~3400Hz / 0~300Hz) × RMS
     背景音乐通常低频很重，纯人声窗口的高频占比更高，因此这个分数倾向于选到干净人声
  3. 取分数最高的窗口写成 32k 单声道参考音
  4. 可选：用 SenseVoiceSmall 识别该片段文字，写成 ref.txt

用法:
  ref_from_video.py --wav 16k.wav --clip-out ref.wav [--text-out ref.txt] [--clip-sec 8]
"""
import argparse
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from funasr import AutoModel

TARGET_SR = 32000


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


def speech_score(win, sr):
    """高频占比 × 音量：倾向于纯人声窗口。"""
    n = len(win)
    spec = np.abs(np.fft.rfft(win * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    lf = spec[(freqs >= 40) & (freqs < 300)]
    hf = spec[(freqs >= 300) & (freqs <= 3400)]
    lf_e = float(np.sum(lf ** 2)) + 1e-9
    hf_e = float(np.sum(hf ** 2)) + 1e-9
    ratio = hf_e / lf_e
    rms = float(np.sqrt(np.mean(win ** 2) + 1e-12))
    peak = float(np.abs(win).max())
    pen = 0.4 if peak > 0.985 else 1.0      # 爆音惩罚
    return ratio * (rms ** 0.5) * pen, ratio, rms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True, help="16k 单声道音频")
    ap.add_argument("--clip-out", required=True)
    ap.add_argument("--text-out")
    ap.add_argument("--clip-sec", type=float, default=8.0)
    ap.add_argument("--topk", type=int, default=5, help="打印前 N 个候选窗口供参考")
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
    if not intervals:
        print("❌ 没有检测到语音段")
        return 1
    print("检测到 %d 个语音段" % len(intervals))

    need = int(args.clip_sec * sr)
    windows = []
    for a, b in intervals:
        seg = y[int(a / 1000 * sr):int(b / 1000 * sr)]
        if len(seg) < need:
            if len(seg) >= int(2 * sr):          # 不足目标长度但 >=2 秒，也当候选（用整段）
                windows.append((a / 1000, b / 1000, 0, seg))
            continue
        step = max(1, int(0.5 * sr))
        for off in range(0, len(seg) - need + 1, step):
            windows.append((a / 1000, b / 1000, off, seg[off:off + need]))
    if not windows:
        print("❌ 没有可用窗口")
        return 1

    scored = []
    for a, b, off, win in windows:
        sc, ratio, rms = speech_score(win, sr)
        scored.append((sc, ratio, rms, a + off / sr, win))
    scored.sort(key=lambda x: -x[0])
    print("\n候选窗口（按“纯人声可能性”排序，前 %d）：" % args.topk)
    for sc, ratio, rms, start, win in scored[:args.topk]:
        f0 = librosa.yin(win, fmin=60, fmax=400, sr=sr, frame_length=2048)
        f0 = f0[np.isfinite(f0)]
        f0 = f0[(f0 > 60) & (f0 < 400)]
        med = float(np.median(f0)) if len(f0) else float("nan")
        print("  %6.2fs 起  得分 %.3f  高频占比 %.2f  音量 %.3f  基频 %.0fHz  时长 %.1fs"
              % (start, sc, ratio, rms, med, len(win) / sr))

    sc, ratio, rms, start, win = scored[0]
    out = librosa.resample(win, orig_sr=sr, target_sr=TARGET_SR) if sr != TARGET_SR else win
    os.makedirs(os.path.dirname(os.path.abspath(args.clip_out)), exist_ok=True)
    # 轻微归一化，避免参考音过小
    peak = float(np.abs(out).max())
    if 0 < peak < 0.7:
        out = out * (0.85 / peak)
    sf.write(args.clip_out, out, TARGET_SR)
    f0 = librosa.yin(win, fmin=60, fmax=400, sr=sr, frame_length=2048)
    f0 = f0[np.isfinite(f0)]
    f0 = f0[(f0 > 60) & (f0 < 400)]
    med = float(np.median(f0)) if len(f0) else float("nan")
    tag = "偏低(典型男声)" if med < 140 else ("中性偏低" if med < 160 else ("中性偏高" if med < 185 else "偏高(典型女声)"))
    print("\n✅ 选定 %.2fs 起、%.1f 秒  基频 %.1f Hz → %s" % (start, len(win) / sr, med, tag))
    print("   已写出: %s" % args.clip_out)

    if args.text_out:
        print("\n加载 SenseVoiceSmall 识别文字…")
        asr = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", device="cpu", disable_update=True)
        tmp = "/tmp/_ref_pick_16k.wav"
        sf.write(tmp, win if sr == 16000 else librosa.resample(win, orig_sr=sr, target_sr=16000), 16000)
        r = asr.generate(input=tmp, language="zh", use_itn=True)
        raw = r[0]["text"] if r else ""
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            text = rich_transcription_postprocess(raw).strip()
        except Exception:  # noqa: BLE001
            text = raw.strip()
        print("   识别: %s" % text)
        with open(args.text_out, "w", encoding="utf-8") as f:
            f.write(text)
        print("   已写出: %s" % args.text_out)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
