#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT-SoVITS 合成引擎（进程内常驻，模型只加载一次，供 Web UI 反复调用）。

要点：
  · inference_webui 在导入时会加载一次默认权重（CPU 上约 10~60 秒），之后切换权重只需几秒
  · change_sovits_weights 是 generator：必须排空才会真正执行（官方 CLI 的坑）
  · 支持运行时切换推理设备（cpu / cuda / mps）：改 DEVICE 环境变量 + 重新加载模块实现
  · 上游代码只认 CUDA，这里在导入前自动打补丁（ensure_device_support），
    因此原生、Docker、Windows 三种交付形态都不需要人工改上游代码
"""
import importlib
import os
import re
import shutil
import sys
import threading
import time

import numpy as np
import soundfile as sf

VARIANTS = {
    "默认": (20, 0.6, 0.6, 1.0),
    "更稳": (15, 0.9, 0.7, 1.0),
    "更活": (25, 0.6, 0.85, 1.0),
}

DEVICE_LABELS = {
    "cuda": "GPU · NVIDIA CUDA",
    "mps": "GPU · Apple Metal(MPS)",
    "cpu": "CPU",
}
DEVICE_NOTES = {
    "cuda": "NVIDIA 显卡的官方主推路径，自动启用 fp16，通常比 CPU 快 3~10 倍",
    "mps": "Apple 芯片的 Metal 后端；实测比 CPU 慢约 40%（自回归解码 + 算子回退），建议仅作试验",
    "cpu": "默认选项；Apple Silicon 上实测比 MPS 更快（RTF≈0.75）",
}

# ---- 给上游 inference_webui.py 打的设备补丁（幂等）----
PATCH_MARK = "支持 DEVICE 环境变量（cpu / cuda / mps）"
OLD_RE = re.compile(
    r'^if torch\.cuda\.is_available\(\):\n    device = "cuda"\nelse:\n    device = "cpu"$',
    re.M,
)
NEW_SNIPPET = '''# --- patch_device: 支持 DEVICE 环境变量（cpu / cuda / mps）---
_device_env = os.environ.get("DEVICE", "").strip().lower()
if _device_env in ("cuda", "mps", "cpu"):
    device = _device_env
elif torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"
print("推理设备:", device)
# --- /patch_device ---'''


def ensure_device_support(repo_root):
    """让上游支持 DEVICE 环境变量。返回 already / patched / unsupported / failed / missing。"""
    path = os.path.join(repo_root, "GPT_SoVITS", "inference_webui.py")
    try:
        with open(path, encoding="utf-8") as f:
            s = f.read()
    except OSError:
        return "missing"
    if PATCH_MARK in s:
        return "already"
    m = OLD_RE.search(s)
    if not m:
        return "unsupported"
    try:
        shutil.copy2(path, path + ".bak-device")
        with open(path, "w", encoding="utf-8") as f:
            f.write(s[:m.start()] + NEW_SNIPPET + s[m.end():])
        return "patched"
    except OSError:
        return "failed"


class Engine:
    def __init__(self, repo_root, device=None):
        self.repo_root = os.path.abspath(repo_root)
        self.lock = threading.RLock()
        self.loaded = None          # (gpt, sovits)
        self._mods = None
        self.patch_state = None
        self.log = []
        if device:
            os.environ["DEVICE"] = device

    # ---------- 设备 ----------
    def available_devices(self):
        import torch
        mps_ok = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        cuda_ok = torch.cuda.is_available()
        out = []
        for dev in ("cuda", "mps", "cpu"):
            avail = {"cuda": cuda_ok, "mps": mps_ok, "cpu": True}[dev]
            item = {"id": dev, "label": DEVICE_LABELS[dev], "available": avail, "note": DEVICE_NOTES[dev]}
            if dev == "cuda" and cuda_ok:
                try:
                    item["name"] = torch.cuda.get_device_name(0)
                    item["count"] = torch.cuda.device_count()
                except Exception:  # noqa: BLE001
                    pass
            out.append(item)
        return out

    def current_device(self):
        if self._mods:
            mod = sys.modules.get("GPT_SoVITS.inference_webui")
            if mod is not None:
                return getattr(mod, "device", "?")
        import torch
        env = os.environ.get("DEVICE", "").strip().lower()
        if env in DEVICE_LABELS:
            return env
        return "cuda" if torch.cuda.is_available() else "cpu"

    def set_device(self, dev, progress=None):
        """切换推理设备（会重新加载模型到新设备）。"""
        dev = (dev or "").strip().lower()
        if dev not in DEVICE_LABELS:
            raise ValueError("不支持的设备：%s（可选 cpu / cuda / mps）" % dev)
        avail = {d["id"]: d["available"] for d in self.available_devices()}
        if not avail.get(dev):
            raise RuntimeError("%s 当前不可用" % DEVICE_LABELS[dev])
        with self.lock:
            if self._mods and dev == self.current_device():
                return dev
            t0 = time.time()
            os.environ["DEVICE"] = dev
            if self._mods:
                if progress:
                    progress(0, "正在把模型加载到 %s …" % DEVICE_LABELS[dev])
                self._reload()
            self.log.append("切换推理设备 → %s（%.1fs）" % (dev, time.time() - t0))
            return self.current_device()

    # ---------- 内部：懒加载 / 重载 ----------
    def _import(self):
        if self._mods:
            return self._mods
        os.chdir(self.repo_root)
        for p in (self.repo_root, os.path.join(self.repo_root, "GPT_SoVITS")):
            if p not in sys.path:
                sys.path.insert(0, p)
        os.environ.setdefault("language", "zh_CN")
        os.environ.setdefault("version", "v2Pro")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

        self.patch_state = ensure_device_support(self.repo_root)
        if self.patch_state == "patched":
            self.log.append("已自动为上游打上 DEVICE 补丁（原文件备份为 inference_webui.py.bak-device）")
        elif self.patch_state in ("unsupported", "failed"):
            self.log.append("⚠️ 上游代码与本补丁不匹配：设备只能由启动时的 DEVICE 环境变量决定")

        import torch
        try:
            torch.set_num_threads(max(1, (os.cpu_count() or 4)))
        except Exception:  # noqa: BLE001
            pass

        self._mods = self._bind()
        self.log.append("模型已就绪（设备 %s）" % self.current_device())
        return self._mods

    def _bind(self):
        """导入 inference_webui 并抓取需要的函数引用。"""
        import GPT_SoVITS.inference_webui as iw  # noqa: N813
        return {
            "module": iw,
            "change_gpt_weights": iw.change_gpt_weights,
            "change_sovits_weights": iw.change_sovits_weights,
            "get_tts_wav": iw.get_tts_wav,
            "i18n": iw.i18n,
        }

    def _reload(self):
        """改完 DEVICE 后重新执行模块（重新把模型加载到新设备）。"""
        mod = sys.modules.get("GPT_SoVITS.inference_webui")
        self._mods = None
        self.loaded = None
        if mod is None:
            self._import()
            return
        importlib.reload(mod)
        self._mods = self._bind()

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
        for _ in m["change_sovits_weights"](sovits, m["i18n"]("中文"), m["i18n"]("中文")):
            pass                      # generator 必须排空
        self.loaded = (gpt, sovits)
        self.log.append("切换权重 %s + %s（%.1fs）"
                        % (os.path.basename(gpt), os.path.basename(sovits), time.time() - t0))

    # ---------- 对外：合成 ----------
    def synth(self, text, ref_wav, ref_text, gpt, sovits, variant="默认", speed=None, cut="按标点符号切",
              progress=None):
        """返回 (numpy float 音频, 采样率)。progress(done, msg) 可为 None。"""
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
                progress(i + 1, "")
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
        self.log.append("合成完成 %.1fs，%.2fs 音频（设备 %s）"
                        % (time.time() - t0, len(audio) / sr, self.current_device()))
        return audio, sr

    def save_wav(self, audio, sr, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sf.write(path, audio, sr)
        return path
