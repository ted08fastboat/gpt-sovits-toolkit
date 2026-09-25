# 声音工坊 · GPT-SoVITS 语音克隆 UI（Docker）

把本地跑通的 GPT-SoVITS 语音克隆流程封装成一个 Web UI，用容器一条命令起服务。

## 一、准备

1. 装好 Docker：
   - macOS / Windows：安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - Linux：`curl -fsSL https://get.docker.com | sh`
2. 组装构建目录（把 Dockerfile、应用、仓库源码放到一起）：

```bash
cd /path/to/gpt-sovits-toolkit/ui
./make_build_dir.sh          # 生成 ui/build/，里面自带 .env（默认复用本机已有模型与权重）
```

## 二、启动

```bash
cd ui/build
docker compose up -d --build     # 首次构建约 5~15 分钟（下载 torch/依赖约 1.5GB）
```

打开 **http://localhost:8000** 即可。常用命令：

```bash
docker compose logs -f          # 看日志（模型下载/加载进度都在这）
docker compose restart          # 重启
docker compose down             # 停止并删除容器（数据都在挂载目录里，不会丢）
```

## 三、数据从哪来

| 内容 | 来源 | 说明 |
|---|---|---|
| 预训练模型（BERT/HuBERT/v2Pro/G2PW 等，约 3.2GB） | `PRETRAINED_DIR` / `G2PW_DIR` / `NLTK_DIR`，或 `./models` | 复用本机已有目录 = 秒起；留空并设 `AUTO_FETCH=1` 则容器首次启动自动从 hf-mirror 下载 |
| 音色权重（`GPT_weights_*/`、`SoVITS_weights_*/`） | `WEIGHTS_DIR`（默认 `./weights`） | 容器启动时会把这些目录软链进仓库；UI 的「音色权重」下拉会自动列出 |
| 参考音色（wav + 同名 txt） | `./references` | 也可以在 UI 里直接上传（支持 wav/mp3/m4a，自动转码） |
| 合成结果 | `./outputs` | UI 里可试听/下载/删除，文件同时落在这个目录 |

`.env` 里把三个 `*_DIR` 指向本机 `~/GPT-SoVITS/...`，就能**零下载**直接起（推荐，模型已在本地）。

## 四、GPU（可选）

镜像默认是 **CPU 版 torch**（体积小、任何机器可跑）。要用 NVIDIA 显卡：

1. 装好 NVIDIA 驱动 + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
2. 把 `Dockerfile` 里装 torch 那行换成 CUDA 版：
   ```dockerfile
   RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu121 torch==2.6.0 torchaudio==2.6.0
   ```
3. 打开 `docker-compose.yml` 末尾 `deploy:` 那几行注释
4. `docker compose up -d --build`

## 四点五、关于依赖下载（国内网络）

`make_build_dir.sh` 会在宿主机先把 PyTorch CPU wheel 下到 `build/wheels/`（走阿里云镜像，约 93MB），
容器构建时用 `--find-links` 离线安装——因为 `download.pytorch.org` 在国内经常卡死。
`wheels/` 里架构不匹配（比如拿到 amd64 机器上构建）时，pip 会自动跳过并回退到在线源，不会构建失败。

## 五、UI 里能做什么

- **合成**：输入台词 → 选参考音色、权重、参数风格（默认/更稳/更活）、语速、切分方式 → 开始合成（CPU 上短句约 5~20 秒，模型已常驻内存，不用每次等加载）
- **参考音色**：上传音频（wav/mp3/m4a）+ 填逐字文字、试听、切换默认、改文字、删除
- **输出管理**：在线播放、下载、删除
- **引擎日志**：模型加载/切换/合成耗时都可见

## 六、常见问题

1. **端口被占用**：改 `.env` 里 `PORT=8001` 再 `docker compose up -d`
2. **合成报错找不到模型**：看 `docker compose logs` 里 fetch 的结果；常见是 `lid.176.bin`（语种检测）或 `G2PWModel`（中文多音字）缺失，重跑 `docker compose restart` 会补齐
3. **权重没出现在下拉里**：目录名必须以 `GPT_weights` / `SoVITS_weights` 开头，文件扩展名是 `.ckpt` / `.pth`
4. **Linux 下输出文件属主是 root**：容器默认以 root 运行（要写 `/repo/weight.json`）。如需改属主：`sudo chown -R $USER outputs references`
5. **内存**：模型常驻约 2~3GB，建议给 Docker 至少 6GB 内存
6. **Apple Silicon**：默认构建 arm64 镜像，CPU 推理正常；不涉及 GPU

## 七、声明

- GPT-SoVITS 本体为 MIT 协议开源项目：https://github.com/RVC-Boss/GPT-SoVITS
- 音色权重可能包含他人声音（例如真人或角色），**转发/商用前请确认授权**，不得用于冒充他人、诈骗等用途
