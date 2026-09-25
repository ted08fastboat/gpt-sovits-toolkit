#!/usr/bin/env python3
"""GPT-SoVITS 克隆合成命令行工具（单条 / 批量，支持多变体）。

权重通过环境变量指定（由包装脚本 say.sh 设置）：
    version / gpt_path / sovits_path

单条：
    python tts_clone.py --text-file 台词.txt --out-dir 输出目录 \
        --ref-wav 参考音频 --ref-text-file 参考文本 [--variants 2]
批量（每行一句，整批只加载一次模型）：
    python tts_clone.py --batch-file 台词.txt --out-dir 输出目录 \
        --ref-wav 参考音频 --ref-text-file 参考文本 [--prefix batch]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "GPT_SoVITS"))

import soundfile as sf  # noqa: E402
from GPT_SoVITS.inference_webui import get_tts_wav, i18n  # noqa: E402

# (名称, top_k, top_p, temperature, speed)
VARIANTS = [
    ("v1-默认", 20, 0.6, 0.6, 1.0),
    ("v2-更稳", 15, 0.9, 0.7, 1.0),
    ("v3-更活", 25, 0.6, 0.85, 1.0),
]


def synthesize(text, ref_wav, ref_text, ref_lang, text_lang, out_path, cut, params):
    top_k, top_p, temp, speed = params
    gen = get_tts_wav(
        ref_wav_path=ref_wav,
        prompt_text=ref_text,
        prompt_language=i18n(ref_lang),
        text=text,
        text_language=i18n(text_lang),
        how_to_cut=i18n(cut),
        top_k=top_k,
        top_p=top_p,
        temperature=temp,
        speed=speed,
    )
    last = None
    for sr, audio in gen:  # get_tts_wav 是 generator，必须迭代到底
        last = (sr, audio)
    if last is None:
        raise RuntimeError("合成没有返回音频（检查参考音频/文本是否为空）")
    sr, audio = last
    # 官方底模零样本输出常偏小（峰值 0.2 左右），这里统一做一次保守增益，
    # 避免听起来忽大忽小；峰值已接近满刻度则不动
    peak = float(abs(audio).max())
    scale = 1.0
    if peak > 1.5:  # int16
        peak16 = peak
        if peak16 < 0.70 * 32768:
            scale = min(3.0, 0.89 * 32768 / max(peak16, 1.0))
        if scale > 1.001:
            audio = (audio.astype("float32") * scale).clip(-32768, 32767).astype(audio.dtype)
    else:
        if peak < 0.70:
            scale = min(3.0, 0.89 / max(peak, 1e-6))
        if scale > 1.001:
            audio = (audio * scale).clip(-1.0, 1.0)
    sf.write(out_path, audio, sr)
    dur = len(audio) / sr
    peak = float(abs(audio).max())
    if peak > 1.5:
        peak = peak / 32768.0
    return sr, dur, peak, scale


def read_lines(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", help="单条台词（UTF-8 文本文件）")
    ap.add_argument("--batch-file", help="批量台词，每行一句（以 # 开头忽略）")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ref-wav", required=True)
    ap.add_argument("--ref-text-file", required=True, help="参考音频对应的文字")
    ap.add_argument("--ref-lang", default="中文")
    ap.add_argument("--text-lang", default="中文")
    ap.add_argument("--cut", default="按标点符号切")
    ap.add_argument("--variants", type=int, default=2, help="单条模式下生成几个变体（1-3）")
    ap.add_argument("--speed", type=float, default=None, help="统一覆盖语速，如 0.95 / 1.05")
    ap.add_argument("--prefix", default="clone")
    args = ap.parse_args()

    if not args.text_file and not args.batch_file:
        sys.exit("需要 --text-file 或 --batch-file 之一")

    os.makedirs(args.out_dir, exist_ok=True)
    if not os.path.exists(args.ref_wav):
        sys.exit("参考音频不存在: %s" % args.ref_wav)
    ref_text = ""
    if os.path.exists(args.ref_text_file):
        ref_text = open(args.ref_text_file, encoding="utf-8").read().strip()

    print("参考音频: %s" % args.ref_wav)
    print("参考文本: %s" % (ref_text[:60] if ref_text else "(空 → ref_free 模式)"))
    print("权重    : gpt=%s | sovits=%s" % (os.environ.get("gpt_path"), os.environ.get("sovits_path")))
    print("输出目录: %s" % os.path.abspath(args.out_dir))

    t0 = time.time()
    made = []
    if args.batch_file:
        lines = read_lines(args.batch_file)
        if not lines:
            sys.exit("批量台词文件里没有有效行: %s" % args.batch_file)
        print("批量模式：共 %d 句\n" % len(lines))
        for idx, line in enumerate(lines, 1):
            out = os.path.join(args.out_dir, "%s_%03d.wav" % (args.prefix, idx))
            p = VARIANTS[0][1:]
            if args.speed:
                p = (p[0], p[1], p[2], args.speed)
            sr, dur, peak, gain = synthesize(line, args.ref_wav, ref_text, args.ref_lang,
                                             args.text_lang, out, args.cut, p)
            made.append(out)
            print("[%d/%d] %5d Hz %5.2fs 峰值 %.3f 增益 x%.2f  %s  <- %s" % (idx, len(lines), sr, dur, peak, gain, os.path.basename(out), line[:24]))
    else:
        text = open(args.text_file, encoding="utf-8").read().strip()
        if not text:
            sys.exit("台词为空")
        print("合成台词: %s\n" % text[:80])
        n = max(1, min(3, args.variants))
        for name, top_k, top_p, temp, speed in VARIANTS[:n]:
            if args.speed:
                speed = args.speed
            out = os.path.join(args.out_dir, "%s_%s.wav" % (args.prefix, name))
            sr, dur, peak, gain = synthesize(text, args.ref_wav, ref_text, args.ref_lang,
                                             args.text_lang, out, args.cut, (top_k, top_p, temp, speed))
            made.append(out)
            print("✅ %-8s %5d Hz %5.2fs 峰值 %.3f 增益 x%.2f -> %s" % (name, sr, dur, peak, gain, out))

    print("\n完成 %d 个文件，用时 %.1f 秒" % (len(made), time.time() - t0))
    # 有些环境下 torch/onnxruntime 在解释器退出阶段析构会触发
    # "recursive_mutex lock failed" 而 abort（文件其实已写好）。
    # 这里显式刷新后直接退出，绕过析构竞争。
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
