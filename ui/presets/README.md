# 内置示例音色

网页 UI 的「音色库」页会读这里的 `presets.json`，列出可以一键安装的音色。

**音频文件不进仓库**（`.gitignore` 排除了 `*.mp3` / `*.wav`），需要现生成：

```bash
pip install edge-tts
python make_presets.py            # 生成 xiaoxiao.mp3 / yunxi.mp3 / xiaoyi.mp3
```

生成完目录结构应该是：

```
presets/
├─ presets.json
├─ make_presets.py
├─ xiaoxiao.mp3   ← 生成
├─ yunxi.mp3      ← 生成
└─ xiaoyi.mp3     ← 生成
```

然后让容器看到它（compose 里已经挂好）：

```yaml
volumes:
  - ./presets:/data/presets:ro
```

## presets.json 的格式

```json
[
  {
    "id": "demo-xiaoxiao",
    "name": "示例·晓晓",
    "file": "xiaoxiao.mp3",
    "text": "今天的天气很好，适合出去散步。我们下午三点在公园门口见面吧。",
    "note": "女声，语气温和，适合日常对话与播报"
  }
]
```

- `file`：本地文件名（相对本目录）
- `url`：也可以填 http 直链，这时类型显示为「网络」，点安装才下载
- `text`：参考音频里说的那句话。**填准了音色还原度会明显更好**，留空则走零样本模式

改完刷新网页即可看到新条目，不用重启容器。

## 关于这些示例音色

三条音频是用 edge-tts（微软在线语音）合成的我们自己写的句子，仅作为开箱测试用。
真要长期用某个音色，建议换成你自己录的 5~10 秒干净人声。
