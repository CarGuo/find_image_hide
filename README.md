# Image Forensics Inspector

一个跨平台（Windows + macOS）本地命令行 + 浏览器 UI 的图片取证分析工具，用于**批量扫描本地目录下所有图片**，输出统一的风险等级与可视化证据。所有分析在本机完成，不会上传到任何外部服务。

工具会同时给出：

- 基础信息：文件大小、SHA256、感知哈希 pHash、MIME；
- 元数据：EXIF / XMP / IPTC / PNG 文本块 / JPEG comment / 图库黑名单（Shutterstock、Getty 等关键词）；
- 隐藏内容提取：附加在图像数据末尾的 trailing data（zip / 文本 / 文件签名）+ LSB 比特流文本提取；
- 隐写检测：Westfeld χ² POV、滑动 χ²、SPA 像素对统计；
- 可见水印 OCR：通过 Tesseract 读图上的 Getty / Shutterstock / 仅供预览 等可见水印（可选）；
- 反查参考库：感知哈希 Hamming 距离匹配本地参考目录（可选）；
- AI 来源凭证：C2PA（如系统中存在 `c2patool`）+ 关键词扫描（OpenAI / Gemini / SD / MJ / Adobe Firefly 等）；
- FFT 频域：灰度 + RGB 频谱图、对称峰值检测；
- DCT：8x8 DCT 系数 heatmap、与 Laplace 自然分布的 K-S 检验；
- LSB：R/G/B 位平面图、熵 / 平衡度 / 邻域相关；
- 噪声残差：Gaussian residual、Laplacian、局部噪声不一致度；
- ELA 误差水平分析：再压缩误差，定位拼接 / 修图区域；
- 综合启发式风险评分：LOW / MEDIUM / HIGH / UNKNOWN，每个 tab 按风险染色。
- **司法级可重现 PDF 报告**：单图详情页一键导出，**字节级可重现**（同 `report.json` 永远产同 SHA-256 PDF），含 6 张图证 + 30 条证据 + 数字签名占位，soft-dep `reportlab`，详见 [P2.4 验收清单](file:///d:/workspace/project/find_image_hide/docs/P2.4_ACCEPTANCE.md)。

> **重要免责声明**
> 本工具不能证明图片绝对包含或绝对没有水印，也不能证明图片绝对是或绝对不是 AI 生成。所有评分都是 heuristic，不构成法律鉴定结论。SynthID 不在常规 EXIF/XMP 中，本工具默认不做本地 SynthID 判定。

---

## ⚠️ 能力诚实声明（请先看这一段）

为避免误解 / 期望错配，下面把每个模块按"裸环境跑得动 vs. 装依赖才能跑 vs. 启发式信号"三档分类。**绿档可信、黄档需要装东西、橙档只是信号源不是判决器。**

### 🟢 A 档：开箱即用，真实可用（仅需 [requirements.txt](file:///d:/workspace/project/find_image_hide/requirements.txt)）

| 模块 | 文件 | 能力强弱 |
|---|---|---|
| 基本信息 + 元数据 | [basic_info.py](file:///d:/workspace/project/find_image_hide/image_forensics/basic_info.py) / [metadata_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/metadata_analysis.py) | 强：EXIF/IPTC/XMP/PNG text、Shutterstock/Getty/AI 产品名关键字命中 |
| FFT / DCT / LSB / Noise / ELA | [fft_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/fft_analysis.py) / [dct_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/dct_analysis.py) / [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) / [noise_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/noise_analysis.py) / [ela.py](file:///d:/workspace/project/find_image_hide/image_forensics/ela.py) | 中-强：经典统计/频域指标，对**朴素 LSB、JPEG 拼接、强压缩异常**敏感 |
| 隐藏内容提取 | [extraction.py](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py) | 强：尾部 zip / EOI 后文本 / append 文件可直接检出 |
| Copy-Move 检测 | [copy_move_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_analysis.py) | 中：ORB + 块匹配，**典型 PS 复制粘贴篡改可检出** |
| pHash 反查 | [phash_match.py](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) | 强（前提：设置 `FORENSICS_PHASH_REFERENCE_DIR`） |
| AI 来源溯源（元数据线路）| [ai_provenance_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py) | 强（前提：图里**还存有**元数据 / C2PA） |
| 司法级 PDF 报告 | [pdf_report.py](file:///d:/workspace/project/find_image_hide/image_forensics/pdf_report.py) | 强：字节级可重现（仅需 `pip install reportlab`） |

### 🟡 B 档：装上才有，没装会优雅降级（不报错、字段标 SKIPPED）

| 模块 | 需要装 | 不装时表现 |
|---|---|---|
| 隐形水印（DwtDct）解码 | `pip install invisible-watermark opencv-python` | `status: UNAVAILABLE` |
| C2PA pure-Python 校验 | `pip install c2pa-python` | `status: SKIPPED_NO_LIBRARY` |
| 外部隐写工具聚合 | 系统装 `binwalk` / `zsteg` / `stegoveritas` / `stegseek` 其中之一 | 对应 tool `SKIPPED_NO_TOOL`，**全没装时整模块 UNKNOWN** |
| 可见水印 OCR | 系统装 `tesseract` 二进制 | OCR 段 SKIPPED，其它模块照跑 |

> 这一档是"用不了"吐槽的主要来源。**这不是假功能，是软依赖**——可以在 [analyzer.py L65-L78](file:///d:/workspace/project/find_image_hide/image_forensics/analyzer.py#L65-L78) 看到所有模块都包了 try/except，缺包返回 UNKNOWN 而不是崩。

### 🟠 C 档：启发式信号源（明确标注 `limitations`）

| 模块 | 真实定位 | 注意事项 |
|---|---|---|
| [steganalysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis.py) | 卡方 POV / SPA 经典隐写分析 | **对现代自适应隐写（HUGO/WOW/S-UNIWARD）无效**，要靠 B 档外部工具或深度模型 |
| [ai_heuristics.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py) | 频域 + 噪声阈值打分 | **不是训练好的判别模型**，对最新生成模型（Flux/Sora 截图/Midjourney v6）准确率没保证 |
| SynthID 频域探针（在 [analyzer.py L218-L234](file:///d:/workspace/project/find_image_hide/image_forensics/analyzer.py#L218-L234)） | reverse-SynthID 启发式 | Google 没开源真正解码，**权威验证只能走 Google 官方接口** |

---

## ✅ 适合 / ❌ 不适合的使用场景

### ✅ 强烈推荐使用

| 场景 | 推荐理由 |
|---|---|
| 取证 / 合规：需要一份"我用 18 个维度都查过，证据链留底"的报告 | [report.json](file:///d:/workspace/project/find_image_hide/image_forensics/analyzer.py#L237-L241) + 字节级可重现 PDF + 中文 evidence 描述，比 SaaS 黑盒分值更有审计价值 |
| 安全 / CTF：图里藏了 zip / 可执行 / steghide 加密 payload | [extraction.py](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py) + [steganalysis_external.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis_external.py) 调 binwalk/zsteg/stegseek，**这是最硬的命中场景** |
| 判别带 C2PA 签名的 AI 图（ChatGPT 出图 / Adobe Firefly / Leica M11-P）| [c2pa_check.py](file:///d:/workspace/project/find_image_hide/image_forensics/c2pa_check.py) 解 manifest → `VERIFIED_AI_GENERATED`，**真·硬证** |
| 检查 SDXL/SD2 **原图**是否带默认 invisible-watermark | [invisible_watermark_detect.py L136-L283](file:///d:/workspace/project/find_image_hide/image_forensics/invisible_watermark_detect.py#L136-L283) 字典命中 `sdv2/sdxl` 给 HIGH |
| 反查"洗图"：判断一张图是不是从你本地参考库里改尺寸 / 重压缩出来的 | 设 `FORENSICS_PHASH_REFERENCE_DIR` → [phash_match.py](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) Hamming ≤ 8 命中 |
| 检测 PS 拼接 / 复制粘贴篡改 | ELA + Copy-Move + Noise 三路同时报警，**这是经典强项** |
| 完全离线 / 涉密环境 | 100% 本地，不向外发任何请求，源码全开可审计 |

### ❌ 不适合的场景（请用别的工具）

| 场景 | 为什么不适合 | 建议替代 |
|---|---|---|
| **判别一张"被微信/小红书转过、剥光元数据"的 AI 图** | 本项目没有训练好的 CNN/ViT 判别模型，[ai_heuristics.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py) 只是手写阈值；C 档置信度 ~0.4 不足以拍板 | Hive AI / Optic AI-or-Not（SaaS），或自己接 UniversalFakeDetect / NPR 预训练模型 |
| 现代自适应隐写（HUGO / WOW / S-UNIWARD）检测 | [steganalysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis.py) 是 2000s 经典统计法，对自适应隐写几乎无效 | Yedroudj-Net / SRNet / ZhuNet（深度学习 SOTA） |
| 视频取证 / 反向图搜 | 本项目纯图像，不做视频 / 不做外网图搜 | InVID Verification Plugin |
| 大规模运营审核（每天百万张过 AI/违规判别）| 启发式 + 重 IO，单图秒级 | 上专门的内容审核 SaaS |
| 司法磁盘镜像分析 | 本项目是单图取证，不做磁盘 carving | Autopsy / Ghiro |

### 📊 关于"准确率数字"——必须坦白

**本 README 不给任何准确率百分比。** 原因是项目内置了 [tools/datasets/](file:///d:/workspace/project/find_image_hide/tools/datasets) 下的 GenImage mini / CASIA v2 mini / COMOFOD / Chameleon 拉取脚本和 [tools/run_regression.py](file:///d:/workspace/project/find_image_hide/tools/run_regression.py)，但**作者尚未把完整回归报告钉死到仓库里**。任何不在公开数据集上跑过混淆矩阵就报出来的"准确率 95%"都是耍流氓。

如果你要真实数字，请自己跑：

```bash
python tools/datasets/fetch_genimage_mini.py     # 拉真实 AI 图集
python tools/datasets/fetch_casia_v2_mini.py     # 拉真实篡改图集
python tools/run_regression.py                   # 出混淆矩阵
```

跑完结果会在 [tools/regression_clean_baseline/](file:///d:/workspace/project/find_image_hide/tools/regression_clean_baseline) 下。**作者计划下一步把回归结果作为 CI 产物固化**（见 [docs/ROADMAP.md](file:///d:/workspace/project/find_image_hide/docs/ROADMAP.md)）。

---

## 路线图：如何补 AI 检测短板

`ai_heuristics` 是手写阈值，要让它能稳定打中"被剥光元数据的现代 AI 出图"，唯一硬办法是接入预训练判别模型。候选：

- **NPR (CVPR 2024)**：ResNet50 底座，~100MB 权重，CPU ~200ms/图
- **UniversalFakeDetect (CVPR 2023)**：CLIP ViT-L/14 底座，~1GB 权重，CPU ~1s/图，泛化更好

接入方式建议走 optional extras（`pip install .[ai]`），保持主包"纯本地、轻量"的定位。目前**未集成**，欢迎 PR。

---

## 快速开始

### 依赖

- Python **3.10+**（Windows 上推荐官方安装包，macOS 上 `brew install python@3.11`）；
- 可选：`c2patool`（用于读取 / 验证 C2PA）。如果没有装，工具仍可运行，C2PA 字段会标记 `c2pa_tool_available=false`；
- 可选：`tesseract`（用于读取图片上的可见水印）。未安装时 OCR 段会显示明确的安装指引，不影响其他模块；
- 可选：`reportlab`（**P2.4 PDF 报告导出**，`pip install reportlab`）。未安装时详情页「导出 PDF」按钮自动 `disabled` + tooltip 提示安装命令，永不抛 500；
- 可选：环境变量 `FORENSICS_PHASH_REFERENCE_DIR`（用于 pHash 参考库反查；指向一个本地目录即可）。

### Windows

```powershell
# 在项目根目录
.\start.bat            # 仅启动 Web UI
.\start.bat --demo     # 自动准备样本 + 跑一次完整 demo + 启动 Web UI（推荐首次使用）
```

脚本会自动创建 `.venv`、安装依赖、启动 Web UI 在 http://127.0.0.1:5050 ，并自动用默认浏览器打开。

### macOS

```bash
chmod +x start.sh
./start.sh             # 仅启动 Web UI
./start.sh --demo      # 自动准备样本 + 跑一次完整 demo + 启动 Web UI（推荐首次使用）
```

### 一键 Demo（最快上手方式）

无需手填路径，直接体验全部检测能力：

```bash
python demo.py                 # 仅准备样本 + 跑分析（CLI 输出每张图风险等级）
python demo.py --serve         # 同上 + 启动 Web UI 并自动打开浏览器
python demo.py --no-download   # 离线模式，只用合成样本
```

也可以在 Web UI 首页点击「**一键运行 Demo**」按钮，等价于 `POST /api/demo`：自动扫描内置 [tools/test_images](file:///d:/workspace/project/find_image_hide/tools/test_images)，覆盖正常图、LSB 隐写、附加 ZIP / 文本、AI 元数据、版权图（Shutterstock / Getty 元数据 + 可见水印）、洗图反查（pHash 命中本地参考库）等典型场景。

> 真实样本来自 picsum.photos / Wikimedia Commons / NASA 等公开免费来源（见 [tools/download_test_images.py](file:///d:/workspace/project/find_image_hide/tools/download_test_images.py)）；可见水印 / 版权图样本基于这些真实图叠加生成（见 [tools/make_test_images.py](file:///d:/workspace/project/find_image_hide/tools/make_test_images.py)）。

### 手动启动（任意平台）

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python webapp.py --host 127.0.0.1 --port 5050
```

> **关于端口**：默认端口是 `5050`。早期版本默认用 5000，但 macOS Monterey 起 5000 端口被系统的 AirPlay Receiver 占用，浏览器访问会被系统服务直接 403 拦截；Windows 上 5000 通常没被系统占用，但为了跨平台脚本一致，统一改成 5050。如果 5050 也被占，可手动指定其它端口，例如 `python webapp.py --port 5060`，并把浏览器地址同步改成 `http://127.0.0.1:5060`。

> **从手机 / Android 浏览器访问同一台电脑上的 Web UI**：默认 `--host 127.0.0.1` 只监听本机回环，手机访问不到。改为 `python webapp.py --host 0.0.0.0 --port 5050`，再让手机和电脑接到同一 Wi-Fi，用电脑的局域网 IP 访问，例如 `http://192.168.1.23:5050`。注意一旦绑到 `0.0.0.0`，同一网络下其它设备也能访问，**不要放到公网**，且最好仅在受信任网络下临时启用。

---

## 使用方式

启动后浏览器访问 http://127.0.0.1:5050 ，首页一共有三种触发扫描的方式：

### 方式一：把文件夹直接拖进来（推荐，最直观）

1. 启动 Web UI；
2. 从 Windows 资源管理器或 macOS Finder 里，把要扫描的整个文件夹拖到首页的虚线方框里；
3. 浏览器会递归读取该文件夹下所有支持的图片（JPG / PNG / WebP / BMP / TIFF / GIF），并以 multipart 一次性 POST 到本机 `/api/scan_upload`；
4. 上传过程中页面会显示进度条；上传完成后自动跳转到对应的 job 页，分析任务会立刻在后台开始；
5. 点方框的话也可以打开"选择文件夹"对话框（基于 `<input type="file" webkitdirectory>`），效果与拖拽一致；
6. 子目录结构会被保留：上传的文件被放到 `analysis_output/<job_id>/_uploaded/<原相对路径>` 下。

注意：

- 浏览器出于安全模型不会暴露被拖入文件的本地绝对路径，因此这种方式必然要"上传到本机后端"。整条数据流都在 127.0.0.1 内，不出网；
- 默认上传体积上限为 1 GB（[webapp.py 中的 `MAX_UPLOAD_BYTES`](file:///d:/workspace/project/find_image_hide/webapp.py#L24-L24)）。如果一次要扫的图集超过这个大小，请改用方式二；
- 服务端会自动忽略不支持的扩展名，并把跳过的文件数返回给前端展示。

### 方式二：填一个本机绝对路径

适合"原图就放在本机一个目录里、不想再上传一遍"的情况：

1. 在首页"方式二：填本地目录路径"卡片里输入目录绝对路径（Windows 例：`D:\photos`，macOS 例：`/Users/me/Pictures`）；
2. 勾选是否递归扫描，设置 worker 并发数；
3. 点「开始扫描」，进入扫描结果页（支持文件名筛选、风险等级筛选）；
4. 点击单条记录的「详情」查看每张图的 12 个分析模块。

### 方式三：一键 Demo

首页第三张卡片直接点「一键运行 Demo」即可，跑项目自带的样本集。

不论用哪种方式，详情页都会包含：

- 综合评估（badge：高风险 / 中风险 / 低风险 / 未知）；
- 12 个 tab：隐藏内容提取 / 版权 · 图库 / 隐写检测 / 元数据 / AI 来源 / 频域 (FFT) / DCT 频域 / LSB 位平面 / 噪声残差 / ELA 误差 / 证据汇总 / 原始 JSON；
- 每个 tab 按各自模块的风险等级染色（红 / 黄 / 绿 / 灰），命中风险时还会显示小圆点；
- 每个 tab 顶部都有一段中文通俗解释，告诉你这一步在做什么、什么样的指标可疑；
- OCR / pHash 等可选模块未启用时会展示中文友好引导卡，包含完整的三步安装步骤。

所有结果保存在 `analysis_output/<job_id>/` 下，**目录扫描期间数据不会上传**到任何外部服务；只有"方式一"会让本地浏览器把文件 POST 给本机 webapp 进程。

### 命令行（仅 CLI）

```bash
# 单张图
python analyze_image.py --input ./test.jpg --output ./analysis_output

# 批量目录
python analyze_image.py --input ./photos --output ./analysis_output --recursive --workers 4
```

输出目录结构：

```
analysis_output/
  summary.json                     # 整批汇总
  _uploaded/                       # 仅当通过 Web UI 拖拽上传时存在
  <slug>__<hash>/
    report.json                    # 单图完整报告
    ai_provenance.json
    visualizations/
      spectrum.png, r/g/b_spectrum.png
      dct_mean_heatmap.png, dct_histogram.png
      lsb_r.png, lsb_g.png, lsb_b.png
      residual.png, laplacian.png
```

---

## HTTP API 速览

webapp 启动后会暴露以下 HTTP 接口（仅监听 127.0.0.1）：

| Method | Path | 用途 |
| --- | --- | --- |
| POST | `/api/scan` | 提交一个**本机绝对路径**的扫描任务，body 为 `{ "directory": "...", "recursive": true, "workers": 2 }` |
| POST | `/api/scan_upload` | 拖拽 / 选择文件夹后，前端用 multipart 上传文件，字段为 `files[]` 与配套的 `paths[]`（保留相对路径），可选 `recursive`、`workers` |
| POST | `/api/demo` | 一键运行内置 demo |
| GET | `/api/jobs/<job_id>` | 查询 job 状态、已完成 / 总数 / 最新 50 条结果 |
| GET | `/api/jobs/<job_id>/summary` | 取整批 `summary.json` |
| GET | `/api/jobs/<job_id>/image/<slug>/report` | 取单图完整 report |
| GET | `/jobs/<job_id>` | 任务页（HTML） |
| GET | `/jobs/<job_id>/image/<slug>` | 单图详情页（HTML） |
| GET | `/api/jobs/<job_id>/image/<slug>/report.pdf` | **P2.4** 司法级 PDF 报告（字节级可重现），响应头 `X-Pdf-Sha256` / `X-Source-Sha256` / `X-Pdf-Backend` / `X-Pdf-Viz-Count` |
| GET | `/api/pdf/status` | **P2.4** PDF backend 探测，返回 `{available, version, error, package}` |

`/api/scan_upload` 对路径做了严格清洗（拒绝 `..`、去掉盘符与起始斜杠、扩展名白名单），文件最终落到 `analysis_output/<job_id>/_uploaded/` 下，不会逃出该目录。

---

## 司法级 PDF 报告（P2.4）

> 全部细节、最快验收路径、字节级可重现性自验脚本见 [docs/P2.4_ACCEPTANCE.md](file:///d:/workspace/project/find_image_hide/docs/P2.4_ACCEPTANCE.md)。

### 功能

- 单图详情页综合概览卡内嵌「**导出 PDF**」按钮，点一下浏览器自动下载 `forensic_report_<slug>.pdf`
- PDF 含 4 节：综合概览（封面 + 风险等级红黄绿色条 + 文件 SHA-256）/ 15 模块分项表 / 证据条目 top-30 / 可重现性凭据页（SHA-256 + 数字签名占位）+ 6 张可视化图证（ELA / 频谱 / DCT / LSB / 残差 / Laplacian）
- 中文走 reportlab 内置 CID 字体 STSong-Light，**零外部 TTF 文件**，三平台开箱即用

### 字节级可重现承诺

同一份 `report.json` 在任意机器、任意时刻重复渲染，PDF SHA-256 完全一致——这是司法证据链（chain-of-custody）的根本要求。律师 / 法官 / 对方专家都能拿同一份 `report.json` 自行重建得到字节级一致的 PDF，确认作证未被篡改。

实现：[reportlab](file:///d:/workspace/project/find_image_hide/image_forensics/pdf_report.py) `SimpleDocTemplate(invariant=1)` 关闭随机 ObjectID + 时间戳从 `report["created_at"]` stamp + author/subject/creator/producer 全部写死。

### HTTP 头 chain-of-custody

每次下载响应都带这些头，外部脚本能直接消费：

| 头 | 值 |
|---|---|
| `X-Pdf-Sha256` | 64 字符 hex，PDF 字节 hash |
| `X-Source-Sha256` | 64 字符 hex，`report.json` 字节 hash |
| `X-Pdf-Backend` | `reportlab/4.5.1` |
| `X-Pdf-Viz-Count` | 实际嵌入的图证数（0-6） |
| `X-Image-Sha256`（可选） | 仅在调用方传 image_path 时输出 |
| `X-Source-Inputs-Sha256`（可选） | `sha256(report_sha:image_sha)` 复合 hash，与上同条件 |

### 软依赖友好降级

未装 reportlab 时 `/api/pdf/status` 返回 `{available: false, error: "..."}`，前端 [bindPdfExport](file:///d:/workspace/project/find_image_hide/webui/static/image.js#L818-L860) 自动把按钮 `disabled` 并在 tooltip 提示 `pip install reportlab`，**永不抛 500**。

### 验收

最快路径：装 reportlab → `python webapp.py` → 浏览器跑 demo → 进任意图详情 → 点导出 PDF。完整 8 块验收清单（含字节级可重现性自验脚本）见 [docs/P2.4_ACCEPTANCE.md](file:///d:/workspace/project/find_image_hide/docs/P2.4_ACCEPTANCE.md)。

---

## 作为 Agent Skill 集成（OpenClaw / Hermes / Trae / Claude）

本项目已自带一份标准 **Skill 描述文件**，让 OpenClaw、Hermes、Trae、Claude 等支持 SKILL.md 协议的 Agent 能够把本工具当作一个内置能力直接调用。

- Skill 入口：[.trae/skills/image-forensics-inspector/SKILL.md](file:///d:/workspace/project/find_image_hide/.trae/skills/image-forensics-inspector/SKILL.md)
- 协议参考：`skill-creator`（frontmatter `name` + `description`，body 是 markdown 文档）

### Skill 路由触发条件（写在 frontmatter `description` 里）

Agent 在以下意图下应自动命中并调用本 Skill：

- "这张图是不是 AI 生成 / 有没有 C2PA"
- "PNG/JPG 里是不是藏了 zip / 文本 / 可执行 / LSB payload"
- "这张图是不是被 PS 拼接 / 复制粘贴篡改过"
- "图上有没有 Shutterstock / Getty / Adobe Firefly 水印"
- "拿这张图反查我本地的参考图库（pHash）"
- "出一份字节级可重现的司法级 PDF 报告"
- 批量给一个文件夹打风险等级（LOW / MEDIUM / HIGH）

### 三种调用模式（Agent 按自身能力挑一种）

| 模式 | 适合谁 | 入口 |
|---|---|---|
| **Mode A — CLI** | 任何能 spawn 子进程的 Agent（最稳） | [analyze_image.py](file:///d:/workspace/project/find_image_hide/analyze_image.py)，stdout 直接吐 JSON |
| **Mode B — Python API** | Python 进程内嵌的 Agent | `from image_forensics.analyzer import analyze_image` / `from image_forensics.batch import analyze_directory` |
| **Mode C — Local HTTP** | Hermes / 非 Python Agent / 跨进程编排 | [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py) 提供完整 REST 接口（见上方「HTTP API 速览」） |
| **Mode D — Demo** | 验收 / 端到端演示 | [demo.py](file:///d:/workspace/project/find_image_hide/demo.py) |

### Agent 必须复述给用户的"诚实约束"

Skill 文档里特意把 Agent 容易越界的几条硬约束写死，避免被滥用作"AI 判官 / 隐写判决器"：

- 不能凭 `ai_heuristics` 拍板"这是 AI 图"——只有 `VERIFIED_AI_GENERATED` / `VERIFIED_AI_EDITED`（C2PA 验证通过）才是硬证；
- 经典 χ²/SPA 对现代自适应隐写（HUGO/WOW/S-UNIWARD）无效；
- 没有官方 SynthID 本地解码器；
- JPEG 上 LSB 置信度自动下调；
- 本工具只读，不去除水印、不伪造 C2PA。

### 注册到全局（让 Agent 在任意 cwd 都能发现）

默认 Skill 放在项目自身 [.trae/skills/](file:///d:/workspace/project/find_image_hide/.trae/skills) 下，**仅当 Agent 工作区设到本项目时**会被自动发现。如果你希望 OpenClaw / Hermes 等 Agent 在任何工作目录都能调用，把 [image-forensics-inspector/](file:///d:/workspace/project/find_image_hide/.trae/skills/image-forensics-inspector) 整个目录拷贝（或软链接）到对应 Agent 的全局 skills 目录，例如：

- Trae：`%USERPROFILE%\.trae-cn\builtin\global\skills\`
- 其它 Agent：参考其文档约定的 skills 注册目录

完整 Skill 文档（capability inventory / 输出契约 / 4 条 agent recipe / 安全边界）请直接看 [SKILL.md](file:///d:/workspace/project/find_image_hide/.trae/skills/image-forensics-inspector/SKILL.md)。

---

## report.json schema 速览

```json
{
  "schema_version": "0.1.0",
  "input": { "file_name": "...", "format": "PNG", "sha256": "...", ... },
  "overall": {
    "risk_level": "LOW|MEDIUM|HIGH|UNKNOWN",
    "confidence": 0.0,
    "summary": "...",
    "module_scores": { "fft": 0.0, "dct": 0.0, "lsb": 0.0, "noise": 0.0, "metadata": 0.0, "provenance": 0.0 }
  },
  "metadata": { ... },
  "ai_provenance": { "status": "NO_PROVENANCE_FOUND", ... },
  "frequency_analysis": { ... },
  "dct_analysis": { ... },
  "lsb_analysis": { ... },
  "noise_analysis": { ... },
  "evidence_items": [ ... ]
}
```

---

## AI Provenance / C2PA 说明

- 如果系统中存在 `c2patool`（PATH 可见），工具会自动调用并解析 manifest；
- 否则只做关键词扫描（`OpenAI` / `Gemini` / `Imagen` / `SynthID` / `Stable Diffusion` / `Midjourney` / ...）；
- 状态码：
  - `VERIFIED_AI_GENERATED` / `VERIFIED_AI_EDITED`：C2PA 验证通过 + action 表明生成 / 编辑；
  - `PROVENANCE_PRESENT_BUT_UNVERIFIED`：有 C2PA 但未验证；
  - `POSSIBLE_AI_BUT_UNVERIFIED`：仅有元数据关键词；
  - `NO_PROVENANCE_FOUND`：没有任何来源凭证。

---

## 安全 / 隐私

- webapp 默认只监听 `127.0.0.1`，不接受来自局域网或公网的请求。如果手动用 `--host 0.0.0.0`，请自己评估风险，工具不做任何鉴权；
- 所有图片处理、hash 计算、元数据读取都在本机完成，不会发往外部服务；
- C2PA 验证依赖系统中是否安装了 `c2patool`，本工具不会替你向 C2PA 服务做远程查询；
- pHash 反查仅与你在 `FORENSICS_PHASH_REFERENCE_DIR` 指向的本地目录比对，不会查云端图库；
- 拖拽上传场景：浏览器把文件 POST 给本机 webapp，整段 TCP 都在 127.0.0.1，不出本机；
- 上传体积默认上限 1 GB，超过会被 Flask 拒绝。若需要扫更大数据集，请改用「方式二：填本机绝对路径」。

---

## 限制

- 这个工具不会移除、破解或绕过任何水印；
- 不会伪造 C2PA 或 provenance metadata；
- 不能替代官方 SynthID 检测；
- FFT / DCT / LSB / Noise 异常都是统计启发式，不能直接证明 SynthID 或私有水印的存在；
- JPEG 等有损格式上 LSB 分析的可信度被自动降低；
- 拖拽上传依赖 Chromium / WebKit 系浏览器的 `webkitGetAsEntry` 能力，老版本浏览器可能只能拿到顶层文件；这种情况下请改用「方式二」。

---

## 目录结构

```
find_image_hide/
  requirements.txt
  analyze_image.py            # CLI 入口
  webapp.py                   # Flask Web UI（含 /api/scan、/api/scan_upload、/api/demo）
  demo.py                     # 一键 demo
  start.bat / start.sh        # 跨平台启动脚本
  image_forensics/            # 分析引擎
    basic_info.py
    metadata_analysis.py
    ai_provenance_analysis.py
    fft_analysis.py
    dct_analysis.py
    lsb_analysis.py
    noise_analysis.py
    extraction.py             # trailing data + LSB 文本流提取
    steganalysis.py           # χ² POV / SPA 等
    visible_watermark_ocr.py
    phash_match.py
    ela.py
    scoring.py
    analyzer.py
    batch.py
    pdf_report.py             # P2.4 司法级可重现 PDF 报告（reportlab soft-dep）
    utils.py
  tools/
    download_test_images.py   # 真实公开样本下载
    make_test_images.py       # 合成 + 版权图样本
    check_results.py          # 期望表回归
    test_images/              # demo 样本（运行后生成）
    phash_reference/          # demo 参考库（运行后生成）
  webui/
    templates/                # Jinja2 模板（index.html / job.html / image.html）
    static/                   # app.css / app.js / image.js / job.js
  analysis_output/            # 扫描结果（运行时生成）
    <job_id>/
      _uploaded/              # 拖拽上传场景下的原始文件副本
      summary.json
      <slug>__<hash>/...
```
