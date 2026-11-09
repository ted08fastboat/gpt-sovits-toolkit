#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent / AstrBot 接入层 —— 给「声音工坊」补一组标准语音接口。

原有 UI 用的是「提交任务 + 轮询」的异步模型，程序调用不方便。
这里在同一进程内复用已经常驻显存的合成引擎，暴露两个业界通行协议：

  ① OpenAI 兼容  POST /v1/audio/speech
       body: {"model":"tts-1","input":"要念的文字","voice":"音色名",
              "speed":1.0,"response_format":"wav"|"mp3"|"opus"}
       AstrBot / LangChain / 各类 agent 框架都能直接吃。

  ② GPT-SoVITS 官方 api_v2 兼容  POST /tts
       body: {"text","text_lang","ref_audio_path","prompt_lang","prompt_text",...}
       AstrBot 内置的 GPT-SoVITS 供应商用这个。

辅助接口：
  GET /health          模型是否就绪、可用音色、运行时长
  GET /v1/voices       音色列表（也支持 /voices）
  GET /v1/models       OpenAI 兼容模型列表
  GET /v1/audio/voices 音色列表（部分客户端的探测路径）

鉴权：设置环境变量 AGENT_API_KEY 后，请求需带
      Authorization: Bearer <key>  或  X-API-Key: <key>
      （/health 永远放行，方便探活）
"""
import io
import os
import subprocess
import threading
import time
from typing import Optional
from urllib.parse import quote

import soundfile as sf
from fastapi import Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

_START_TS = time.time()

# response_format -> (ffmpeg 参数, content-type)
_AUDIO_FORMATS = {
    "mp3": (["-f", "mp3", "-b:a", "96k"], "audio/mpeg"),
    "opus": (["-f", "ogg", "-c:a", "libopus", "-b:a", "48k"], "audio/ogg"),
    "ogg": (["-f", "ogg", "-c:a", "libopus", "-b:a", "48k"], "audio/ogg"),
    "aac": (["-f", "adts", "-c:a", "aac", "-b:a", "96k"], "audio/aac"),
    "flac": (["-f", "flac"], "audio/flac"),
    "pcm": (["-f", "s16le", "-acodec", "pcm_s16le"], "audio/pcm"),
}

MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "600"))
SAVE_OUTPUTS = os.environ.get("TTS_SAVE_OUTPUTS", "0") == "1"


def _trim(text: str) -> str:
    """超长文本按句末标点截断，避免一次性合成几分钟音频。"""
    text = (text or "").strip()
    if len(text) <= MAX_CHARS:
        return text
    head = text[:MAX_CHARS]
    for sep in ("。", "！", "？", "；", "\n", ".", "!", "?", ";", "，", ","):
        idx = head.rfind(sep)
        if idx > MAX_CHARS * 0.5:
            return head[: idx + 1]
    return head


def _hdr_voice(name: str) -> str:
    """HTTP 头只能是 latin-1，中文音色名先做 URL 编码。"""
    return quote(str(name), safe="")


def install_compat(app, engine, ref_dir, out_dir, state_loader, weights_getter=None):
    """在主 app 上挂载所有对外接口。engine/state_loader 由 main.py 注入。"""
    lock = getattr(engine, "lock", None) or threading.Lock()

    # ------------------------------------------------------------ 内部工具
    def _state():
        try:
            return state_loader() or {}
        except Exception:  # noqa: BLE001
            return {}

    def _list_refs():
        import glob
        out = []
        for wav in sorted(glob.glob(os.path.join(ref_dir, "**", "*.wav"), recursive=True)):
            name = os.path.relpath(wav, ref_dir)
            try:
                info = sf.info(wav)
                dur = round(info.frames / info.samplerate, 2)
            except Exception:  # noqa: BLE001
                dur = None
            out.append({"id": name, "name": name, "stem": os.path.splitext(name)[0],
                        "path": wav, "dur": dur,
                        "text": _read_sidecar(wav)})
        return out

    def _read_sidecar(wav):
        txt = os.path.splitext(wav)[0] + ".txt"
        if os.path.exists(txt):
            try:
                with open(txt, encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:  # noqa: BLE001
                return ""
        return ""

    def _resolve_voice(voice):
        """voice 可以是音色名/文件名/序号/音色目录内相对路径；空则用当前默认。"""
        refs = _list_refs()
        if not refs:
            raise HTTPException(400, "容器里没有任何参考音色，请先在 UI 上传")
        if voice is None or str(voice).strip() == "" or str(voice).strip().lower() in ("default", "alloy", "auto"):
            state = _state()
            want = state.get("ref")
            for r in refs:
                if want and r["id"] == want:
                    return r
            return refs[0]
        v = str(voice).strip()
        if v.isdigit():
            idx = int(v)
            if 0 <= idx < len(refs):
                return refs[idx]
        low = v.lower()
        for r in refs:
            if low in (r["id"].lower(), r["stem"].lower(), os.path.basename(r["id"]).lower(),
                       os.path.splitext(os.path.basename(r["id"]))[0].lower()):
                return r
        for r in refs:  # 再来一轮模糊匹配（音色名很长时好用）
            if low in r["id"].lower() or low in r["stem"].lower():
                return r
        raise HTTPException(
            400,
            "未知音色 %r，可用：%s" % (v, "、".join(r["id"] for r in refs)),
        )

    def _weights():
        state = _state()
        gpt = state.get("gpt")
        sovits = state.get("sovits")
        if (not gpt or not sovits) and weights_getter:  # 回退到 UI 的默认权重推导逻辑
            try:
                gpt, sovits = weights_getter()
            except Exception:  # noqa: BLE001
                pass
        if not gpt or not sovits:
            raise HTTPException(500, "容器里没有可用的权重，请先检查 /repo 下的 GPT_weights / SoVITS_weights")
        return os.path.join(engine.repo_root, gpt), os.path.join(engine.repo_root, sovits)

    def _synth(text, voice, speed=None, variant=None):
        text = _trim(text)
        if not text:
            raise HTTPException(400, "text/input 不能为空")
        ref = _resolve_voice(voice)
        gpt, sovits = _weights()
        try:
            with lock:
                audio, sr = engine.synth(
                    text=text,
                    ref_wav=ref["path"],
                    ref_text=ref["text"],
                    gpt=gpt,
                    sovits=sovits,
                    variant=variant or "默认",
                    speed=speed,
                    cut="按标点符号切",
                )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, "合成失败：%s" % exc) from exc

        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV")
        wav = buf.getvalue()
        if SAVE_OUTPUTS:
            try:
                fn = "api_%s.wav" % time.strftime("%Y%m%d_%H%M%S")
                with open(os.path.join(out_dir, fn), "wb") as f:
                    f.write(wav)
            except Exception:  # noqa: BLE001
                pass
        dur = len(audio) / float(sr)
        try:  # 记进合成日志本（失败不影响出声）
            from ui_api import record as _record
            _record(text, ref["id"], dur, "", "接口")
        except Exception:  # noqa: BLE001
            pass
        return wav, dur, ref["id"]

    def _encode(wav_bytes, fmt):
        fmt = (fmt or "wav").lower().lstrip(".")
        if fmt in ("wav", "wave", ""):
            return wav_bytes, "audio/wav"
        spec = _AUDIO_FORMATS.get(fmt)
        if not spec:
            return wav_bytes, "audio/wav"
        args, ctype = spec
        try:
            proc = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0", *args, "pipe:1"],
                input=wav_bytes, capture_output=True, timeout=120,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout, ctype
        except Exception:  # noqa: BLE001
            pass
        return wav_bytes, "audio/wav"

    # ------------------------------------------------------------ 鉴权
    def _check(authorization: Optional[str], x_api_key: Optional[str]):
        key = os.environ.get("AGENT_API_KEY", "").strip()
        if not key:
            return
        got = ""
        if authorization and authorization.lower().startswith("bearer "):
            got = authorization[7:].strip()
        elif x_api_key:
            got = x_api_key.strip()
        if got != key:
            raise HTTPException(401, "鉴权失败：请在 Authorization: Bearer <key> 中带上正确的 AGENT_API_KEY")

    # ------------------------------------------------------------ 探活 / 能力
    @app.get("/health")
    @app.get("/v1/health")
    def health():
        refs = _list_refs()
        try:
            gpt, sovits = _weights()
            w_gpt, w_sovits = os.path.relpath(gpt, engine.repo_root), os.path.relpath(sovits, engine.repo_root)
        except HTTPException:
            w_gpt = w_sovits = None
        mods = getattr(engine, "_mods", None)
        device = "cpu"
        if mods:
            try:
                device = "cuda" if mods["torch"].cuda.is_available() else "cpu"
            except Exception:  # noqa: BLE001
                pass
        return {
            "status": "ok",
            "service": "gpt-sovits-voiceui",
            "ready": bool(getattr(engine, "loaded", None) or mods),
            "device": device,
            "default_voice": _state().get("ref") or (refs[0]["id"] if refs else None),
            "voices": [r["id"] for r in refs],
            "gpt": w_gpt,
            "sovits": w_sovits,
            "max_chars": MAX_CHARS,
            "auth_required": bool(os.environ.get("AGENT_API_KEY", "").strip()),
            "uptime_sec": round(time.time() - _START_TS, 1),
            "log": engine.log[-5:],
        }

    @app.get("/v1/models")
    def models():
        return {"object": "list",
                "data": [{"id": "gpt-sovits-v2pro", "object": "model", "owned_by": "local"},
                         {"id": "tts-1", "object": "model", "owned_by": "local"}]}

    @app.get("/v1/voices")
    @app.get("/voices")
    @app.get("/v1/audio/voices")
    def voices():
        refs = _list_refs()
        return {"default": _state().get("ref") or (refs[0]["id"] if refs else None),
                "voices": [{"id": r["id"], "name": r["stem"], "dur": r["dur"], "text": r["text"]} for r in refs]}

    # ------------------------------------------------------------ OpenAI TTS 兼容
    @app.post("/v1/audio/speech")
    def openai_speech(
        payload: dict = Body(default={}),
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None),
    ):
        _check(authorization, x_api_key)
        text = payload.get("input") or payload.get("text") or ""
        voice = payload.get("voice") or payload.get("speaker")
        fmt = payload.get("response_format") or "wav"
        speed = payload.get("speed")
        try:
            speed = float(speed) if speed not in (None, "") else None
        except (TypeError, ValueError):
            speed = None
        variant = payload.get("variant")
        if not variant and payload.get("model") in ("默认", "更稳", "更活"):
            variant = payload.get("model")

        wav, dur, used = _synth(text, voice, speed=speed, variant=variant)
        data, ctype = _encode(wav, fmt)
        if (fmt or "wav").lower() not in ("wav", "wave", ""):
            # 非 wav 时把真实格式写进头，便于调用方拿文件后缀
            return Response(content=data, media_type=ctype,
                            headers={"X-Voice": _hdr_voice(used), "X-Duration": "%.2f" % dur,
                                     "X-Audio-Format": fmt.lower()})
        return Response(content=data, media_type=ctype,
                        headers={"X-Voice": _hdr_voice(used), "X-Duration": "%.2f" % dur})

    # ------------------------------------------------------------ GPT-SoVITS api_v2 兼容
    @app.post("/tts")
    def gsv_tts(
        payload: dict = Body(default={}),
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None),
    ):
        _check(authorization, x_api_key)
        text = payload.get("text") or payload.get("input") or ""
        # ref_audio_path 可能是容器内绝对路径，也可能只是文件名
        ref = payload.get("ref_audio_path") or payload.get("ref") or payload.get("voice")
        if isinstance(ref, str) and ref.strip():
            ref = os.path.basename(ref.strip())
        prompt_text = payload.get("prompt_text") or None
        speed = payload.get("speed_factor") or payload.get("speed")

        if prompt_text:
            # 调用方显式给了参考文本：临时按它合成（不动磁盘上的 .txt）
            vocal = _resolve_voice(ref)
            gpt, sovits = _weights()
            text_trim = _trim(text)
            if not text_trim:
                raise HTTPException(400, "text 不能为空")
            try:
                with lock:
                    audio, sr = engine.synth(
                        text=text_trim, ref_wav=vocal["path"], ref_text=str(prompt_text),
                        gpt=gpt, sovits=sovits, variant="默认",
                        speed=float(speed) if speed else None, cut="按标点符号切",
                    )
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(500, "合成失败：%s" % exc) from exc
            buf = io.BytesIO()
            sf.write(buf, audio, sr, format="WAV")
            dur = len(audio) / float(sr)
            try:
                from ui_api import record as _record
                _record(text_trim, vocal["id"], dur, "", "接口")
            except Exception:  # noqa: BLE001
                pass
            return Response(content=buf.getvalue(), media_type="audio/wav",
                            headers={"X-Voice": _hdr_voice(vocal["id"]), "X-Duration": "%.2f" % dur})

        wav, dur, used = _synth(text, ref, speed=float(speed) if speed else None)
        return Response(content=wav, media_type="audio/wav",
                        headers={"X-Voice": _hdr_voice(used), "X-Duration": "%.2f" % dur})

    # ------------------------------------------------------------ 一次性 JSON 接口（给不会处理二进制的 agent）
    @app.post("/api/v1/say")
    def say_json(
        payload: dict = Body(default={}),
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None),
    ):
        """返回 base64 音频 + 时长，纯 JSON，方便某些 agent/工具链直接消费。"""
        import base64
        _check(authorization, x_api_key)
        wav, dur, used = _synth(payload.get("text") or payload.get("input"),
                                payload.get("voice"), speed=payload.get("speed"),
                                variant=payload.get("variant"))
        return JSONResponse({
            "ok": True,
            "voice": used,
            "duration_sec": round(dur, 2),
            "format": "wav",
            "audio_base64": base64.b64encode(wav).decode(),
        })

    return app
