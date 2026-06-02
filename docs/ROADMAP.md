# 项目路线图（Roadmap）

> 最后更新：2026-06-02
>
> 本文件用于沉淀**能力规划 + 决策记录**，避免历次 conversation context 丢失。  
> 每次推进一个阶段就回到这里勾掉对应项，并记下当时的决策依据。

---

## 一、当前能力盘点

### 已落地的检测模块（[image_forensics/](file:///d:/workspace/project/find_image_hide/image_forensics)）

| 模块 | 文件 | 算法/能力 |
|---|---|---|
| LSB 隐写 | [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) | LSB 平面熵 / 卡方 / SPA |
| 通用隐写 | [steganalysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis.py) | 通用统计 + 差分 |
| 频域 | [fft_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/fft_analysis.py)、[dct_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/dct_analysis.py) | FFT/DCT 频谱异常 |
| 篡改 | [ela.py](file:///d:/workspace/project/find_image_hide/image_forensics/ela.py)、[noise_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/noise_analysis.py) | ELA + 噪声 |
| 元数据 | [metadata_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/metadata_analysis.py)、[psd_metadata.py](file:///d:/workspace/project/find_image_hide/image_forensics/psd_metadata.py) | EXIF / IPTC / XMP / PNG-text / PSD |
| 附加文件 | [extraction.py](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py) | EOF 后追加 ZIP/TXT/Polyglot |
| 水印 | [invisible_watermark_detect.py](file:///d:/workspace/project/find_image_hide/image_forensics/invisible_watermark_detect.py)、[visible_watermark_ocr.py](file:///d:/workspace/project/find_image_hide/image_forensics/visible_watermark_ocr.py) | DwtDct + OCR |
| pHash 同源 | [phash_match.py](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) | 感知哈希查重 |
| AI 来源 | [ai_provenance_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py) | reverse-SynthID（已通） |

### 关键能力盲点

- ❌ 没有 zsteg 风格的 PNG 多通道·多位面 LSB 扫描（仅 b1, rgb, lsb, xy）
- ❌ 没有 steghide / F5 / OutGuess / JSteg 等 JPEG DCT 域隐写检测
- ❌ 没有 Copy-Move（复制粘贴）篡改定位
- ❌ 没有 Splicing（拼接）篡改定位 / 噪声残差网络
- ❌ AI 检测仅靠 metadata 关键词 + reverse-SynthID，缺 GAN/扩散指纹
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

**P1.1** ⭐⭐⭐ 在 [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) 新增 `scan_all_planes()`：枚举 b1-b8 × {r,g,b,a,rgb,bgr} × {xy,yx} 24+ 组合，逼近 zsteg 命中场景

**P1.2** 新增 [steganalysis_external.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis_external.py)：subprocess 集成 stegoveritas / binwalk / stegseek，软依赖、有则用、无则跳

**P1.3** ⭐⭐⭐ 新增 [copy_move_detect.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_detect.py)：SIFT/ORB 特征点匹配 + RANSAC，输出可视化 mask

**P1.4** ⭐⭐ 在 [ai_provenance_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py) 增加颜色直方图均匀度（CVPR'25 *Secret Lies in Color*） + 高频残差启发式

**P1.5** 新增 [c2pa_check.py](file:///d:/workspace/project/find_image_hide/image_forensics/c2pa_check.py)：用 `c2pa-python` 读 manifest，UI 显示"内容凭证：✓ Adobe Photoshop / ⚠ 未签 / ✗ 失效"

**P1.6** UI 增加反向图像搜索按钮：上传图 → 一键打开 Google Images / TinEye / Yandex / Bing 多 tab

### 🎯 P2 — 长尾 / 加分项

- HEIC / AVIF / WebP / RAW 解码兼容
- Deepfake 人脸检测（DeepFake-O-Meter 风格软依赖）
- PRNU 相机指纹
- 报告导出 PDF / 司法级"可重现报告"

---

## 四、决策记录

### 2026-06-02

- **起步阶段**：先 P0 补样本
- **样本范围**：免费公有领域 + 学术数据集 mini + Laundered/HEIC/AVIF/WebP/RAW，**每类 5-10 张，重在展示不堆量**
- **P1 优先项**：LSB 全位面 + Copy-Move + 颜色/频域 AI 启发式
- **外部工具策略**：软依赖 subprocess + 一键安装（沿用 reverse-SynthID 那套，不污染用户环境）
- **是否落 ROADMAP 文档**：是 → 本文件
- **跨平台要求**：所有 fetcher / 命令 / 路径处理按 `platform.system()` 分支，Win + macOS 通吃

---

## 五、推进规则

每个 P 阶段都按以下顺序：

1. 先扩**测试图**（保证有真伪样本能验回归）
2. 再加**检测模块**（新模块上线即跑回归）
3. UI 在 [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py) / [app.js](file:///d:/workspace/project/find_image_hide/webui/static/app.js) 增量加 tab，不动既有结构
4. 每个 P 阶段独立 commit + push，方便 review

每完成一个 P 任务，回到本文件勾掉相应项，并在 §四 追加新决策。
