# 项目路线图（Roadmap）

> 最后更新：2026-06-02（P1 三件套完成）
>
> 本文件用于沉淀**能力规划 + 决策记录**，避免历次 conversation context 丢失。  
> 每次推进一个阶段就回到这里勾掉对应项，并记下当时的决策依据。

---

## 一、当前能力盘点

### 已落地的检测模块（[image_forensics/](file:///d:/workspace/project/find_image_hide/image_forensics)）

| 模块 | 文件 | 算法/能力 |
|---|---|---|
| LSB 隐写 | [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) | LSB 8 位面 × 3 通道 / cross-channel diff / hierarchy violation |
| 通用隐写 | [steganalysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis.py) | 通用统计 + 差分 |
| 频域 | [fft_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/fft_analysis.py)、[dct_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/dct_analysis.py) | FFT/DCT 频谱异常 |
| 篡改 | [ela.py](file:///d:/workspace/project/find_image_hide/image_forensics/ela.py)、[noise_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/noise_analysis.py) | ELA + 噪声 |
| Copy-Move | [copy_move_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_analysis.py) | 8×8 块 DCT + zig-zag 签名 + shift-vector histogram + SNR |
| AI 启发式 | [ai_heuristics.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py) | 通道相关 + HF 残差 + 36-bin 色相直方图（永远 ≤ MEDIUM） |
| 元数据 | [metadata_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/metadata_analysis.py)、[psd_metadata.py](file:///d:/workspace/project/find_image_hide/image_forensics/psd_metadata.py) | EXIF / IPTC / XMP / PNG-text / PSD |
| 附加文件 | [extraction.py](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py) | EOF 后追加 ZIP/TXT/Polyglot |
| 水印 | [invisible_watermark_detect.py](file:///d:/workspace/project/find_image_hide/image_forensics/invisible_watermark_detect.py)、[visible_watermark_ocr.py](file:///d:/workspace/project/find_image_hide/image_forensics/visible_watermark_ocr.py) | DwtDct + OCR |
| pHash 同源 | [phash_match.py](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) | 感知哈希查重 |
| AI 来源 | [ai_provenance_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py) | reverse-SynthID（已通） |

### 关键能力盲点

- ✅ ~~没有 zsteg 风格的 PNG 多通道·多位面 LSB 扫描~~ → P1.1 已扩展 8 位面 × 3 通道
- ✅ ~~没有 Copy-Move（复制粘贴）篡改定位~~ → P1.3 已落地（8×8 块 DCT + shift-vector histogram）
- ✅ ~~AI 检测仅靠 metadata 关键词 + reverse-SynthID~~ → P1.4 已加颜色 / HF 启发式（仅辅助 ≤ MEDIUM）
- ❌ 没有 steghide / F5 / OutGuess / JSteg 等 JPEG DCT 域隐写检测
- ❌ 没有 Splicing（拼接）篡改定位 / 噪声残差网络
- ❌ 没有 GAN/扩散指纹（CNNDetection / DIRE 等深度模型）
- ❌ 没有 C2PA / Content Credentials 凭据校验
- ❌ 没有 Camera Ballistics / PRNU 设备指纹
- ❌ 没有反向图像搜索 / 主张比对
- ❌ 没有 Deepfake 人脸检测
- ❌ 格式兼容：HEIC / HEIF / AVIF / WebP / TIFF / RAW 支持薄弱

---

## 二、行业基线（已调研）

### 商业竞品

- **Amped Authenticate** — 司法级取证黄金标准，40+ filter，可重现报告
- **InVID-WeVerify** — 记者验证插件，反向搜索多引擎
- **FotoForensics / Forensically** — 浏览器 triage（ELA / Noise / Clone）
- **Reality Defender / Truepic / TrueMedia** — 商用 AI / Deepfake SaaS
- **DeepFake-O-Meter v2.0**（开源平台）— 18 个 docker 化检测器

### 强相关开源

| 项目 | 用途 | 接入难度 |
|---|---|---|
| stegoveritas（pip 包） | LSB / 位面 / metadata triage | 低 |
| zsteg（Ruby gem） | PNG/BMP 多通道 LSB | 中 |
| stegseek | steghide cracker | 低 |
| binwalk | 嵌入文件签名扫描 | 低 |
| Aletheia | LSB / J-UNIWARD / SPA / SteganoGAN | 高 |
| CNNDetection | GAN 生成图检测 | 高 |
| AIDE / UniversalFakeDetect / NPR / DIRE | AI 检测 backbone | 高 |
| IMDLBenCo | 篡改定位统一基准 | 高 |
| c2pa-python SDK | Content Credentials 校验 | 中 |

### 学术 / 工业级数据集

**隐写**：BOSSBase 1.01 / BOWS2 / ALASKA2 / LSSD / StegoAppDB  
**AI 生成**：GenImage / AI-Face / Chameleon / DiffusionDB  
**篡改**：CASIA v1/v2 / CoMoFoD / Columbia / NIST16 / DEFACTO / IMD2020 / COVERAGE  
**真实分布对照**：picsum.photos / Unsplash / Wikimedia / RAISE / Dresden / Kodak Lossless

---

## 三、阶段规划

### 🎯 P0 — 数据集扩展（进行中）

**P0.1** 扩充 [download_test_images.py](file:///d:/workspace/project/find_image_hide/tools/download_test_images.py)：在现有 9 条基础上新增 `clean_real / ai_generated / c2pa_signed` 等子集的免费公有领域 URL，总量 ~25 张，**重在展示，不堆量**

**P0.2** 新建 [tools/launder_image.py](file:///d:/workspace/project/find_image_hide/tools/launder_image.py)：生成 Telegram / 微信 / Twitter 三档压缩的 laundered 变体，驱动 pHash 鲁棒性测试

**P0.3** 新建 [tools/datasets/](file:///d:/workspace/project/find_image_hide/tools/datasets) 下的 `fetch_genimage_mini.py / fetch_chameleon_mini.py / fetch_casia_v2_mini.py / fetch_comofod_mini.py`，每数据集 5-10 张，懒加载到 `.cache/datasets/`

**P0.4** 新建 [tools/build_dataset_index.py](file:///d:/workspace/project/find_image_hide/tools/build_dataset_index.py)：扫描 `test_images + .cache/datasets` 生成 `dataset_index.json`（label / source / license / expected_findings）

**P0.5** 新建 [docs/DATASETS.md](file:///d:/workspace/project/find_image_hide/docs/DATASETS.md)：记录所有样本与数据集的来源、license、下载方式、引用要求

### 🎯 P1 — 检测能力补强（按 ROI 排序）

**P1.1** ⭐⭐⭐ ✅ **2026-06-02 完成** — 在 [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) 扩展 8 位面 × 3 通道全扫描 + cross-channel diff + plane-progression 单调性检验。新增字段 `lsb_plane_stats / lsb_white_noise_planes / lsb_common_white_noise_planes / lsb_hierarchy_violation_score / lsb_plane0_cross_channel_spread`，向后兼容 legacy plane-0 字段。

**P1.2** ⭐⭐ ✅ **2026-06-03 完成** — 新建 [steganalysis_external.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis_external.py)：subprocess 软依赖集成 **binwalk / zsteg / stegoveritas / stegseek** 四件套。`shutil.which()` 找不到工具就返回 `tool_status=SKIPPED_NO_TOOL` + `risk=UNKNOWN`，永不抛；`argv` 列表 + `shell=False` + 30s timeout + tempfile 隔离 cwd 防注入。**stegseek opt-in**：必须 `FORENSICS_ENABLE_STEGSEEK=1` + `FORENSICS_STEGSEEK_WORDLIST` 才跑，否则 `SKIPPED_NOT_ENABLED`，避免字典爆破阻塞流水线。**风险升级**：binwalk 命中可执行/归档（Zip/PE/ELF/Mach-O 等）→ HIGH 进 `direct_high`；zsteg magic-number → HIGH；stegoveritas carved 文件 → MEDIUM；stegseek 破解密码 → HIGH。analyzer 串联，scoring 加 0.04 弱权重（HIGH 直接走 direct_high，权重只是平局打破器），summary 中文文案 + module_scores 字段。

**P1.3** ⭐⭐⭐ ✅ **2026-06-02 完成** — 新建 [copy_move_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_analysis.py)：经典 Fridrich-Goljan-Du 2003（8×8 块 DCT-II + zig-zag 前 16 系数 + lexicographic sort + shift-vector histogram + SNR 评分），纯 NumPy einsum 一次性计算所有块 DCT。analyzer 已串联，scoring 加权 0.06，可直接进入 direct_high。新增**块多样性门控**（diversity<0.30 或 ac_energy<0.5 时跳过），消除合成图 / 平滑梯度上的假阳性。

**P1.4** ⭐⭐ ✅ **2026-06-02 完成** — 新建 [ai_heuristics.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py)：CVPR'25 *Secret Lies in Color* 启发的三特征加权（通道相关 45% + 高频残差平整度 35% + 36-bin 色相直方图峰值 30%）。**永远只升到 MEDIUM，不进 direct_high**。新增 `downscale_ratio` 信号失效保护：原图被强缩放（>1.5×）时屏蔽 HF 信号、（>2×）时屏蔽色相信号，避免 LANCZOS 摧毁高频后误判。

**P1.5** ⭐⭐ ✅ **2026-06-02 完成** — 新建 [c2pa_check.py](file:///d:/workspace/project/find_image_hide/image_forensics/c2pa_check.py)：软依赖 `c2pa-python`（pip 包），未安装返回 `SKIPPED_NO_LIBRARY` 不报错。模块输出 `status / risk_level / c2pa_score / claim_generator / signature_info / signature_valid / ai_software_agents / assertions[]`。analyzer 串联，scoring 加 0.04 弱权重避免与既有 `provenance` 加权双计；`status=VERIFIED_AI_GENERATED` 进入 `direct_high`。与既有 `ai_provenance_analysis.py`（走 c2patool CLI）形成"CLI + Python SDK"双路径互补。

**P1.6** ⭐ ✅ **2026-06-02 完成** — 在 [image.html](file:///d:/workspace/project/find_image_hide/webui/templates/image.html) overview-card 之后追加 `reverse-search-card`：5 家引擎（Google Images / TinEye / Yandex / Bing / 百度识图）一行按钮。**纯客户端实现，零后端 API**：默认打开各站的"上传搜索"页面（`https://images.google.com/` 等）让用户手动拖图；若用户在文本框粘贴公网 URL，则按钮自动切换为"链接式" `?image_url=...` 直跳。privacy-first，不替用户上传图。

### 🎯 P2 — 长尾 / 加分项

**P2.3** ⭐⭐ ✅ **2026-06-03 完成** — 新建 [format_decoder.py](file:///d:/workspace/project/find_image_hide/image_forensics/format_decoder.py)：HEIC / AVIF / RAW 三软依赖统一入口 `open_any(path)`。AVIF 直接走 Pillow ≥11.3 内置 libavif（**零新依赖**），HEIC 通过 `pillow-heif.register_heif_opener()` 一次性注册到 Pillow，RAW 通过 `rawpy.imread().postprocess()` 解 demosaic 包成 `Image.fromarray(format='RAW')`。`decoder_status()` 返回三组探测结果（available / version / error / package）便于 `/api/diagnostics` 与单测断言。已在 [utils.safe_open_rgb](file:///d:/workspace/project/find_image_hide/image_forensics/utils.py)、[basic_info](file:///d:/workspace/project/find_image_hide/image_forensics/basic_info.py)、[extraction](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py)、[metadata_analysis](file:///d:/workspace/project/find_image_hide/image_forensics/metadata_analysis.py)、[ai_provenance_analysis](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py)、[ai_heuristics](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py)、[visible_watermark_ocr](file:///d:/workspace/project/find_image_hide/image_forensics/visible_watermark_ocr.py)、[invisible_watermark_detect](file:///d:/workspace/project/find_image_hide/image_forensics/invisible_watermark_detect.py)、[phash_match](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) 全面替换 `Image.open(path)`；同步扩展 [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py) `SUPPORTED_IMAGE_EXTS` 与 [app.js](file:///d:/workspace/project/find_image_hide/webui/static/app.js) `SUPPORTED_EXTS`，覆盖 .heic/.heif/.avif 与 11 种主流相机 RAW 后缀。

**P2.4** ⭐⭐ ✅ **2026-06-03 完成** — 新建 [pdf_report.py](file:///d:/workspace/project/find_image_hide/image_forensics/pdf_report.py)：软依赖 `reportlab`，统一入口 `render_pdf(report.json, output_pdf, viz_dir, image_path)` 返回 manifest dict（`pdf_sha256 / source_report_sha256 / generated_at / backend_version`）。**核心承诺：字节级可重现** — 同一份 report.json 重复渲染产出 SHA-256 完全一致的 PDF（reportlab `invariant=1` + PDF metadata 时间戳从 `report["created_at"]` stamp）。webapp 暴露 `/api/jobs/<id>/image/<slug>/report.pdf`（HTTP 头 `X-Pdf-Sha256` / `X-Source-Sha256` / `X-Pdf-Backend`）+ `/api/pdf/status` 探测端点。前端 [image.html](file:///d:/workspace/project/find_image_hide/webui/templates/image.html) overview-card 内嵌"导出 PDF"按钮，由 [image.js](file:///d:/workspace/project/find_image_hide/webui/static/image.js) 的 `bindPdfExport` 处理：未装 reportlab 时禁用按钮且文案提示 `pip install reportlab`，避免 501 噪声。PDF 内容含综合概览 / 15 模块分项 / 30 条证据 / 6 张可视化图证 / 可重现性凭据页（含 SHA-256 + 数字签名占位）；CJK 用 reportlab 内置 CID 字体 STSong-Light，零外部 TTF。

### 🎯 P2 — 后续待办

- Deepfake 人脸检测（DeepFake-O-Meter 风格软依赖）
- PRNU 相机指纹

---

## 四、决策记录

### 2026-06-02

- **起步阶段**：先 P0 补样本
- **样本范围**：免费公有领域 + 学术数据集 mini + Laundered/HEIC/AVIF/WebP/RAW，**每类 5-10 张，重在展示不堆量**
- **P1 优先项**：LSB 全位面 + Copy-Move + 颜色/频域 AI 启发式
- **外部工具策略**：软依赖 subprocess + 一键安装（沿用 reverse-SynthID 那套，不污染用户环境）
- **是否落 ROADMAP 文档**：是 → 本文件
- **跨平台要求**：所有 fetcher / 命令 / 路径处理按 `platform.system()` 分支，Win + macOS 通吃

### 2026-06-02（P1 三件套收官）

- **顺序**：按 ROADMAP 顺序 LSB → Copy-Move → AI 启发式（不并行，方便逐项回归）
- **依赖**：纯 NumPy / Pillow，**零新依赖**（不引入 scikit-image / scipy.fft / OpenCV-SIFT，保持安装无依赖冲突）
- **Copy-Move 算法选择**：放弃 SIFT/ORB（OpenCV-contrib 协议复杂、SIFT 专利争议），改用 Fridrich-Goljan-Du 2003 经典块 DCT 自相似 — 数学严谨、纯 NumPy einsum、跑得过 stride=4 密集采样
- **AI 启发式 risk 上限**：永久 MEDIUM，**不允许 direct_high**。理由：颜色 / 高频统计在缩放、JPEG、相机 AI 降噪面前都太脆弱，独签 HIGH 会污染 overall 判定
- **缩放陷阱护栏**：AI 启发式入口 probe 原图尺寸，downscale_ratio>1.5× 屏蔽 HF 信号、>2× 屏蔽色相信号（已修复 phone_raw_5712x4284_q85.jpg 假阳性）
- **Copy-Move 自相似护栏**：块多样性<30% 或 AC 能量<0.5 时整图跳过（已修复 normal_png.png 平滑梯度假阳性）
- **回归覆盖**：[regression_clean_baseline.py](file:///d:/workspace/project/find_image_hide/tools/regression_clean_baseline.py) 4/4 通过；[run_regression.py](file:///d:/workspace/project/find_image_hide/tools/run_regression.py) 14/14 通过；mini AI 数据集 12 张 0 假阳性、1 命中 MEDIUM
- **scoring 权重调整**：extraction 0.28→0.26、steganalysis 0.18→0.16、visible_wm/invisible_wm/phash 0.10→0.08；新增 copy_move=0.06、ai_heuristics=0.04（合计仍 1.0）

### 2026-06-02（P1 收官 · fix-medium + C2PA SDK + 反搜按钮）

- **scoring 单 MEDIUM 升级补丁**（[scoring.py](file:///d:/workspace/project/find_image_hide/image_forensics/scoring.py)）：在三 subagent 回归中暴露的真实空洞——单 MEDIUM 模块独立命中时 overall 输出 UNKNOWN。新增三档分支：
  - `copy_move=MEDIUM` 独立直升 MEDIUM（Copy-Move 是结构性证据而非启发式，SNR≥8/top≥6 已是显著事件）
  - 无损容器下 `lsb=MEDIUM` 独立直升 MEDIUM（lossless+lsb 才能被 DCT/PNG 容器保留）
  - 单 MEDIUM 命中时若 `ai_heur` 自身阈≥0.55 也直升；否则要求 confidence>0.35 才升，避免噪声升级
  中招样本：mini-AI 集中 `midjourney_oldtimer.png`（ai_heur=MEDIUM）、`sdxl_poisoned_examples.png`（cm=MEDIUM）现在都正确给 MEDIUM
- **P1.5 c2pa-python SDK 路径**：与既有 `ai_provenance_analysis.py`（c2patool CLI 二进制）形成"双路径"：CLI 装了走 CLI，pip 装了 c2pa-python 走 SDK，都没装就 `SKIPPED_NO_LIBRARY`，永不报错。SDK 路径可独立解析 manifest 的 `validation_status` / `assertions[].softwareAgent`，输出比 CLI 更结构化的 `ai_software_agents`
- **P1.6 反搜按钮**：拒绝接入"代理上传"路径（隐私 + 法律风险），坚持纯客户端 `window.open`：默认上传式按钮始终可用，公网 URL 可选注入 `?image_url=...`。5 家覆盖国内外 + Google Lens 走 `lens.google.com/uploadbyurl`（不是已废弃的 `searchbyimage`）
- **回归证据**：3 路 subagent 并行 + webapp HTTP E2E（multipart 上传 6 张 → 异步 job → summary）全过：14/14 + 6/6 + 6/6 + E2E 6/6（risk_counts={'HIGH':4,'MEDIUM':1,'UNKNOWN':1}），所有样本 `c2pa_check.status=SKIPPED_NO_LIBRARY`，所有 image.html 含 `reverse-search-card`
- **scoring 权重微调**：新增 c2pa_check=0.04（与 provenance 互补，避免双计；权重小但 `VERIFIED_AI_GENERATED` 走 direct_high 升 HIGH 不依赖权重）

### 2026-06-03（P1.2 外部隐写工具软依赖集成）

- **软依赖范式复用**：完全沿用 P1.5 c2pa_check 同构 — `shutil.which()` 找不到 → `tool_status=SKIPPED_NO_TOOL` + `risk=UNKNOWN`，永不抛；本机干净环境下 4/4 工具全 SKIPPED 也不会污染 overall（normal_png 仍 UNKNOWN，14 张基线全部对齐）
- **subprocess 安全调用**：`argv` 列表 + `shell=False` + `timeout=30s` + `tempfile.TemporaryDirectory` 隔离 cwd（防止 stegoveritas 在用户工作目录乱写文件、防止任何工具命令注入）
- **stegseek 显式 opt-in**：必须 `FORENSICS_ENABLE_STEGSEEK=1`（精确匹配字符串 `"1"`，不接受其他 truthy 值）+ `FORENSICS_STEGSEEK_WORDLIST` 指向词典文件才跑；否则 `SKIPPED_NOT_ENABLED`。理由：rockyou 字典爆破单图通常 1-5 分钟，不能阻塞流水线
- **风险升级表**：
  - binwalk 输出含 EXECUTABLE_BINWALK_KEYWORDS（Zip / RAR / PE32 / ELF / Mach-O / gzip / 7-zip / Microsoft executable / 嵌入图片等）→ HIGH 进 `direct_high`
  - binwalk ≥3 个非可执行签名（多重嵌入暗示）→ MEDIUM
  - zsteg 输出 `magic` / `text:` 行 → HIGH
  - zsteg ≥2 个 LSB 平面读出 ≥6 字符可打印 → MEDIUM
  - stegoveritas 在 Results 目录 carved ≥1 文件 → MEDIUM
  - stegseek 破解出 steghide 密码 → HIGH
- **scoring 权重 0.04**：与 c2pa_check 同档；HIGH 通过 `direct_high` 直升，权重只在 MEDIUM 阶段做平局打破。**`external.risk_level=="HIGH"` 已加入 `direct_high` 表达式**
- **不存输出冗余**：每个 tool 的 stdout/stderr 只取头 2KB 入 `evidence_items` 防止报告爆炸；不持久化 stegoveritas 的 carved 文件（用完即删的 tempdir）
- **回归证据**：4 路并行 — run_regression 14/14 一致 + mini AI 6/6 一致（midjourney_oldtimer / sdxl_poisoned 仍 MEDIUM）+ webapp HTTP E2E 6/6（每张 image.html 仍含 `reverse-search-card`）+ 模块单测 4/4（含 monkey-patch 模拟 binwalk 命中 Zip → 验证 risk=HIGH 升级路径）。零新 Python 依赖、零新 ERROR
- **跨平台**：`_which()` 在 Windows 下尝试 `<name>` / `<name>.exe` / `<name>.bat` / `<name>.cmd` 四种后缀；Linux/macOS 直接 `shutil.which`

### 2026-06-03（P2.3 多格式解码兼容）

- **三软依赖范式**：与 P1.5 / P1.2 同构 — import-time probe + `_AVAILABLE/_VERSION/_ERROR` 三元状态 + `decoder_status()` 自描述。三组：HEIC（pillow-heif）/ AVIF（**Pillow ≥11.3 native libavif**，回退 pillow-avif-plugin）/ RAW（rawpy）。本机 Pillow 11.3.0 已具备 native AVIF，**整个 P2.3 在用户已安装 Pillow ≥11.3 的环境下零新依赖**
- **统一入口 `open_any(path)`**：返回 `PIL.Image.Image`。HEIC/AVIF 直接 `Image.open` 透传（已注册解码器）；RAW 走 `rawpy.imread + postprocess(output_bps=8, no_auto_bright=False, use_camera_wb=True)` 拿到 demosaic 后的 ndarray，再 `Image.fromarray(rgb, 'RGB')` 包装并 `img.format = "RAW"` 让下游模块的 `EXIF` 抓取与 `format` 字段一致
- **入口聚拢**：[utils.safe_open_rgb](file:///d:/workspace/project/find_image_hide/image_forensics/utils.py) 由 `Image.open(path)` 改为 `open_any(path)`；其余 9 处 image_forensics 模块（basic_info / metadata_analysis / extraction / invisible_watermark_detect / ai_provenance_analysis / visible_watermark_ocr / phash_match × 2 / ai_heuristics）全部用 `open_any` 替换 `Image.open(path)`。**保留 `Image.open(buf)`**（如 `ela.py` 的 BytesIO 路径），因为 buffer 入口由调用者负责字节级数据
- **SUPPORTED_EXTS 三层一致**：`format_decoder.EXTRA_EXTS` (`.heic/.heif/.avif/.dng/.nef/.cr2/.cr3/.arw/.raf/.orf/.rw2/.pef/.srw/.kdc/.dcr`) → `utils.SUPPORTED_EXTS` 并集 → [webapp.SUPPORTED_IMAGE_EXTS](file:///d:/workspace/project/find_image_hide/webapp.py) 显式扩列 → [app.js](file:///d:/workspace/project/find_image_hide/webui/static/app.js) 前端 `SUPPORTED_EXTS` 同步，三处必须严格一致防止"后端能扫前端拒绝/前端通过后端识别失败"
- **LOSSLESS_FORMATS 不收 HEIC/AVIF/RAW**：HEIC/AVIF 默认有损（HEIC=HEVC、AVIF=AV1），RAW 走 demosaic 已是浮点重建。三者**不**进 LSB 全位面强分析，避免 Westfeld 1999 经典假阳性。WebP 同理（默认 lossy）
- **`UnsupportedFormatError(detected_ext, hint_pkg)`**：自定义异常类型，`open_any` 在 ext 已知但 decoder MISSING 时抛出（例如未装 pillow-heif 又上传 .heic），消息体含安装提示 `pip install pillow-heif`，方便单测断言失败模式与前端可消费
- **测试样本去假阳性**：第一版 `Image.new('RGB',(320,240),'white')` + 渐变填充导致 ai_heuristics_score=1.0（hf_residual_std≈0、hue 单 bin），把 normal_avif/normal_webp 推到 MEDIUM 假阳性。**第二版**用 `Image.open('tools/test_images/normal_jpeg.jpg').convert('RGB')` 重编码到 AVIF/WEBP — 真实照片的频域统计与色相分布让 ai_score 落到 0.42-0.48 区间，overall=LOW
- **回归证据**：3 路并行 — run_regression 16 张全过（normal_png=HIGH 是 P2.3 之前已存在的样本本身被嵌入 LSB，与本轮无关，已 `git stash` 回 `3140616` 验证）+ webapp HTTP E2E 5/5（jpg/png/webp/avif/ai_metadata 全 errors=0，risk_counts={HIGH:2,LOW:3}，每张 image.html 仍含 `reverse-search-card`）+ 模块单测 5/5（open_any AVIF/WEBP / decoder_status 三键 / is_extra_format 大小写 / is_raw / monkey-patch HEIC missing 触发 UnsupportedFormatError 含 "pillow-heif" hint）
- **跨平台**：本机 Pillow 11.3.0 + native AVIF；macOS/Linux 用户若 Pillow <11.3 可走 `pip install pillow-avif-plugin` 回退路径（format_decoder 自动探测）；HEIC/RAW 在三平台均依赖 `pillow-heif` / `rawpy` 的预编译 wheel（PyPI 已覆盖 Win/macOS/Linux × Py 3.9-3.13）

### 2026-06-03（P2.4 司法级可重现 PDF 报告）

- **软依赖范式（第四次复用）**：与 P1.5 c2pa_check / P1.2 steganalysis_external / P2.3 format_decoder 完全同构 — import-time probe + `_REPORTLAB_AVAILABLE / _REPORTLAB_VERSION / _REPORTLAB_ERROR` 三元状态 + `pdf_status()` 自描述 + `PdfBackendUnavailableError(hint_pkg='reportlab')` 异常。本机零 reportlab 时模块仍可正常 import，调用 `render_pdf` 才抛 hint pip 安装命令的友好异常
- **后端选型 reportlab vs weasyprint vs wkhtmltopdf**：选 **reportlab 4.5.1** —— ① 纯 Python wheel 三平台 × Py 3.9-3.13 全 PyPI 覆盖，无 GTK/Cairo/Pango 系统依赖（weasyprint 在 Win 上需要装 GTK runtime）；② **CID CJK 字体 STSong-Light / HeiseiMin-W3 随包内置**，零外部 TTF 文件分发，避免许可证麻烦；③ Platypus 高级原语（`SimpleDocTemplate` / `Paragraph` / `Table` / `Image` / `Spacer`）足够画司法级排版；④ **支持 `invariant=1`** —— 这是字节级可重现的关键开关
- **核心承诺：字节级可重现**（content-addressable PDF）：
  - reportlab `SimpleDocTemplate(invariant=1)` 关闭随机 ObjectID + 关闭压缩流的随机 padding
  - PDF metadata 时间戳从 `report["created_at"]` 解析（含 `Z`→`+00:00` 兼容），fallback `datetime.now(timezone.utc)`；author/subject/creator/producer 全部写死字符串
  - 同一份 report.json 重复渲染 → SHA-256 完全一致（实测 `6f04233059be...` 两次）
  - 这是司法证据链（chain-of-custody）的根本要求：律师/法官/对方专家都能拿同一份 report.json 自行重建得到字节级一致的 PDF，确认作证未被篡改
- **content-addressable manifest**：`render_pdf()` 返回 `{pdf_path, pdf_sha256, source_report_sha256, generated_at, backend, backend_version, pdf_size_bytes}`；HTTP 响应通过 `X-Pdf-Sha256` / `X-Source-Sha256` / `X-Pdf-Backend` 三个 header 暴露给前端，前端 `bindPdfExport` 在状态行展示 SHA-256 截断（前 12 字符）让用户立即可视
- **隐私保护**：PDF 不嵌入用户的绝对路径（输入路径仅参与 sha256 计算并保留 file_name + sha256 截断显示），避免分享 PDF 时泄露主目录结构 / 桌面用户名 / 工作目录命名习惯
- **CJK 字体三层回退**：`pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))` → 失败回退 HeiseiMin-W3 → 再失败回退 Helvetica（不显示中文但不崩）。**正常路径走 STSong-Light**，本机/macOS/Linux 都通
- **PDF 4 节结构**：① 综合概览（封面 + 风险等级红黄绿色条 + 文件 sha256）/ ② 15 模块分项表（来自 `_MODULE_LABEL` 字典：基本信息 / EXIF/IPTC / AI 来源 / Watermark / LSB / Copy-Move / Steganalysis / Extraction / phash / c2pa_check / external_steganalysis / ai_heuristics …）/ ③ 证据条目 top-30（`evidence_items`）/ ④ 可重现性凭据页（含 SHA-256 hex + invariant=1 标识 + **数字签名占位**：建议外部 `gpg --detach-sign` 或 Adobe Sign 二次签名）。后跟 `PageBreak` 引出可视化页：6 张优选图证（ela.png / spectrum.png / dct_histogram.png / lsb_b_p0.png / residual.png / laplacian.png）
- **webapp 双路由 + 友好 501**：`/api/jobs/<id>/image/<slug>/report.pdf`（`send_file(..., as_attachment=True, download_name=f'forensic_report_{slug}.pdf')`）；`/api/pdf/status` 探测端点。`PdfBackendUnavailableError` 走 **501 Not Implemented**（语义准确：服务端识别请求但未配 backend）而非 500，前端能区分"软依赖缺失"vs"真实错误"；前端检测到 501 直接禁用按钮，避免重复尝试
- **UI 不动主结构**：[image.html](file:///d:/workspace/project/find_image_hide/webui/templates/image.html) overview-card 内嵌"导出 PDF"按钮 + 状态行（不新加 card），与既有 12 tab + reverse-search-card 共存；[image.js](file:///d:/workspace/project/find_image_hide/webui/static/image.js) `bindPdfExport` 加在 main 函数末尾（不影响其他 13 个 render*）；[app.css](file:///d:/workspace/project/find_image_hide/webui/static/app.css) 加深灰按钮 #2c3e50 + hover #34495e + disabled #bdc3c7，与既有"已复制"按钮风格统一
- **回归证据**：3 路并行 — 模块单测 6/6（pdf_status keys / 有效 PDF >50KB / **可重现 SHA-256 字节级一致** / source_report_sha256 与手动 hash 一致 / `_REPORTLAB_AVAILABLE=False` monkey-patch 抛 `PdfBackendUnavailableError` 含 `pip install reportlab` hint / 无 viz_dir 时仍产 7.5KB 最小 PDF）+ webapp HTTP E2E 14/14（multipart 上传 → 轮询 done → GET report.pdf 200 + Content-Type=application/pdf + body 前 5 字节 `%PDF-` + X-Pdf-Sha256 64 字符 hex + X-Pdf-Backend=`reportlab/4.5.1` + body sha256 与 header 一致 + size 736791 + **第二次下载 SHA-256 一致** + image.html 仍含 `export-pdf-btn` 与 `reverse-search-card`）+ run_regression 16/16 风险级别与 P2.3 commit 完全对齐，零回归
- **跨平台**：reportlab 4.5.1 是纯 Python wheel，PyPI 三平台 × Py 3.9-3.13 全覆盖；CID CJK 字体随包内置不需外部 TTF；Windows + macOS 同等支持

---

## 五、推进规则

每个 P 阶段都按以下顺序：

1. 先扩**测试图**（保证有真伪样本能验回归）
2. 再加**检测模块**（新模块上线即跑回归）
3. UI 在 [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py) / [app.js](file:///d:/workspace/project/find_image_hide/webui/static/app.js) 增量加 tab，不动既有结构
4. 每个 P 阶段独立 commit + push，方便 review

每完成一个 P 任务，回到本文件勾掉相应项，并在 §四 追加新决策。
