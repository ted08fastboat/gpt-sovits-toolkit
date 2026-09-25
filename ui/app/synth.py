#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT-SoVITS 合成引擎（进程内常驻，模型只加载一次，供 Web UI 反复调用）。

要点：
  · inference_webui 在导入时会加载一次默认权重（约 30~60 秒），之后切换权重只需几秒
  · change_sovits_weights 是 generator：必须排空才会真正执行（官方 CLI 的坑）
  · 权重路径可来自环境变量 gpt_path / sovits_path，用于指定初始权重
"""
import os
import threading
import time

import numpy as np
import soundfile as sf

VARIANTS = {
    "默认": (20, 0.6, 0.6, 1.0),
    "更稳": (15, 0.9, 0.7, 1.0),
    "更活": (25, 0.6, 0.85, 1.0),
}


class Engine:
    def __init__(self, repo_root, device=None):
        self.repo_root = os.path.abspath(repo_root)
        self.lock = threading.RLock()
        self.loaded = None          # (gpt, sovits)
        self._mods = None
        self.device = device
        self.log = []

    # ---------- 内部：懒加载 ----------
    def _import(self):
        if self._mods:
            return self._mods
        os.chdir(self.repo_root)
        import sys
        for p in (self.repo_root, os.path.join(self.repo_root, "GPT_SoVITS")):
            if p not in sys.path:
                sys.path.insert(0, p)
        os.environ.setdefault("language", "zh_CN")
        os.environ.setdefault("version", "v2Pro")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

        import torch
        torch.set_num_threads(max(1, (os.cpu_count() or 4)))

        from GPT_SoVITS.inference_webui import (  # noqa: E402
            change_gpt_weights,
            change_sovits_weights,
            get_tts_wav,
            i18n,
        )
        self._mods = {
            "torch": torch,
            "change_gpt_weights": change_gpt_weights,
            "change_sovits_weights": change_sovits_weights,
            "get_tts_wav": get_tts_wav,
            "i18n": i18n,
        }
        self.log.append("模型已就绪（%s）" % ("cuda" if torch.cuda.is_available() else "cpu"))
        return self._mods

    def preload(self):
        """启动时预热，避免第一次合成等太久。"""
        with self.lock:
            self._import()

    def ensure_weights(self, gpt, sovits):
        m = self._import()
        gpt = os.path.abspath(gpt)
        sovits = os.path.abspath(sovits)
        if self.loaded == (gpt, sovits):
            return
        t0 = time.time()
        m["change_gpt_weights"](gpt)
        # generator 必须排空
        for _ in m["change_sovits_weights"](sovits, m["i18n"]("中文"), m["i18n"]("中文")):
            pass
        self.loaded = (gpt, sovits)
        self.log.append("切换权重 %s + %s（%.1fs）" % (os.path.basename(gpt), os.path.basename(sovits), time.time() - t0))

    # ---------- 对外：合成 ----------
    def synth(self, text, ref_wav, ref_text, gpt, sovits, variant="默认", speed=None, cut="按标点符号切",
              progress=None):
        """返回 (numpy float 音频, 采样率)。progress(done, total) 可为 None。"""
        m = self._import()
        self.ensure_weights(gpt, sovits)
        top_k, top_p, temp, sp = VARIANTS.get(variant, VARIANTS["默认"])
        if speed:
            sp = float(speed)
        t0 = time.time()
        gen = m["get_tts_wav"](
            ref_wav_path=ref_wav,
            prompt_text=ref_text or "",
            prompt_language=m["i18n"]("中文"),
            text=text,
            text_language=m["i18n"]("中文"),
            how_to_cut=m["i18n"](cut),
            top_k=top_k,
            top_p=top_p,
            temperature=temp,
            speed=sp,
        )
        chunks = []
        for i, item in enumerate(gen):
            chunks.append(item)
            if progress:
                progress(i + 1, 0)
        if not chunks:
            raise RuntimeError("合成没有返回音频")
        sr, audio = chunks[-1]
        audio = np.asarray(audio)
        if audio.dtype.kind == "i":
            audio = audio.astype(np.float32) / 32768.0
        # 保守增益，避免底模输出过小
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if 0 < peak < 0.7:
            audio = np.clip(audio * min(3.0, 0.89 / peak), -1.0, 1.0)
        self.log.append("合成完成 %.1fs，%.2fs 音频" % (time.time() - t0, len(audio) / sr))
        return audio, sr

    def save_wav(self, audio, sr, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sf.write(path, audio, sr)
        return path
