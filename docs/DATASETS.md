# 数据集与测试样本（Datasets）

> 本文档记录项目目前使用的**所有图像样本来源、license 与下载方式**。  
> 原则：**只引用、不再发**——任何受版权约束或访问受限的数据集都通过脚本"按需懒加载"到本地缓存目录，绝不入库。

---

## 一、样本目录布局

```
find_image_hide/
├── tools/
│   ├── test_images/              # 公有领域 + 合成样本（轻量、可入库前 .gitignore 已排除）
│   │   ├── <legacy flat>         # 早期 9 张 picsum / Wikimedia / NASA
│   │   ├── clean_real/           # 真实负样本：相机原始 EXIF 充足
│   │   ├── ai_generated/         # AI 生成正样本（Wikimedia 公有领域 SDXL/Midjourney/DALL-E/Firefly）
│   │   ├── c2pa_signed/          # Content Credentials 演示图
│   │   ├── format_zoo/           # WebP / TIFF / GIF 格式兼容
│   │   └── social_laundered/     # launder_image.py 生成的平台压缩变体
│   └── datasets/                 # 学术数据集 mini-fetcher
│       ├── _common.py
│       ├── fetch_genimage_mini.py
│       ├── fetch_chameleon_mini.py
│       ├── fetch_casia_v2_mini.py
│       └── fetch_comofod_mini.py
└── .cache/
    └── datasets/                 # 学术 mini-fetcher 输出，已 .gitignore
        ├── genimage_mini/
        ├── chameleon_mini/
        ├── casia_v2_mini/
        └── comofod_mini/
```

`tools/test_images/` 和 `.cache/` 都在 [.gitignore](file:///d:/workspace/project/find_image_hide/.gitignore)，**任何二进制都不会进入仓库**。

---

## 二、获取样本的三条命令

```bash
# 1. 拉公有领域示例图（picsum + Wikimedia + NASA + AI/CC2PA/格式）
python tools/download_test_images.py

# 2. 合成确定性样本（LSB stego / 附加文件 / 水印 / 元数据假阳性等）
python tools/make_test_images.py

# 3. 拉学术数据集 mini 子集（5-10 张/集，演示用）
python tools/datasets/fetch_genimage_mini.py
python tools/datasets/fetch_chameleon_mini.py
python tools/datasets/fetch_casia_v2_mini.py
python tools/datasets/fetch_comofod_mini.py

# 可选：扫描所有目录，生成 dataset_index.json
python tools/build_dataset_index.py

# 可选：把任何一张真图过一遍 Telegram/微信/Twitter 平台压缩
python tools/launder_image.py tools/test_images/clean_real/canon_eos_landscape.jpg
```

---

## 三、来源与 license 一览

### 3.1 公有领域 / 自由使用

| 来源 | 数量 | License | 入口 |
|---|---|---|---|
| picsum.photos | 5 | Free use, no attribution | https://picsum.photos |
| Wikimedia Commons | ~15 | PD / CC0 / CC-BY-SA | https://commons.wikimedia.org |
| NASA Image Library | 1 | Public Domain | https://images.nasa.gov |
| Kodak Lossless True Color Suite | 2 | Research-use, free | https://r0k.us/graphics/kodak/ |

### 3.2 学术数据集（不再发，仅链接 + mini 替身）

| 数据集 | 论文 | 访问 | License / 注意 |
|---|---|---|---|
| **GenImage** | Zhu et al., NeurIPS 2023 | https://github.com/GenImage-Dataset/GenImage | 论文署名引用，非商用 |
| **Chameleon** | Yan et al., 2024 | https://github.com/SCUT-DLVCLab/Chameleon | 仅供研究，需邮件申请 |
| **CASIA-v2** | Dong et al., ChinaSIP 2013 | http://forensics.idealtest.org/ | 需邮件申请 |
| **CoMoFoD** | Tralic et al., ELMAR 2013 | https://www.vcl.fer.hr/comofod/ | 学术使用免费，1.5 GB ZIP |
| **ALASKA2** | Cogranne et al., 2020 | https://alaska.utt.fr/ | Kaggle 免费，2.4 GB |
| **BOSSBase 1.01** | Bas et al., IH 2011 | http://agents.fel.cvut.cz/boss/ | 学术使用免费 |
| **CASIA v1 / Columbia** | (经典基线) | 各原始页面 | 学术使用 |
| **DiffusionDB** | Wang et al., ACL 2023 | https://github.com/poloclub/diffusiondb | CC0 |
| **AI-Face** | (多种) | Hugging Face | 各档 CC-BY |
| **NIST Nimble Challenge / MFC18** | NIST | 需注册 | 政府数据，限制使用 |

### 3.3 Mini-fetcher 当前内容

> 这些 fetcher 拉的是**公有领域代表样本**，不是官方 split。提供它们只是为了"演示该数据集解决的问题"，并让回归脚本有图可吃。

| Fetcher | 文件 | 抓取数 | 真实代表的数据集 |
|---|---|---|---|
| `fetch_genimage_mini.py` | [link](file:///d:/workspace/project/find_image_hide/tools/datasets/fetch_genimage_mini.py) | 6 | GenImage（SD / DALL-E / Midjourney） |
| `fetch_chameleon_mini.py` | [link](file:///d:/workspace/project/find_image_hide/tools/datasets/fetch_chameleon_mini.py) | 6 | Chameleon（高难度 AI 人像 / 风格图） |
| `fetch_casia_v2_mini.py` | [link](file:///d:/workspace/project/find_image_hide/tools/datasets/fetch_casia_v2_mini.py) | ≤8（软指针） | CASIA v2（splicing） |
| `fetch_comofod_mini.py` | [link](file:///d:/workspace/project/find_image_hide/tools/datasets/fetch_comofod_mini.py) | ≤8（软指针） | CoMoFoD（copy-move） |

> **"软指针"含义**：CASIA / CoMoFoD 因 license 不允许 hot-link，脚本默认只打印官方访问 URL；
> 当用户自带 archive 并通过 `CASIA_V2_DIR` / `COMOFOD_DIR` 环境变量指向本地目录时，
> 脚本最多复制 8 张样本到 `.cache/datasets/<name>_mini/` 用于演示。

---

## 四、社交平台压缩仿真（laundered）

[tools/launder_image.py](file:///d:/workspace/project/find_image_hide/tools/launder_image.py) 不下载任何东西，只对**已有真图**做平台风格的 JPEG 重编码：

| 平台 | 长边上限 | JPEG q | 备注 |
|---|---|---|---|
| Telegram | 1280 | 80 | 元数据剥离 |
| 微信 (WeChat) | 960 | 70 | 元数据剥离 + 轻度模糊 |
| Twitter / X | 2048 | 85 | 元数据剥离 |
| 微博 (Weibo) | 1080 | 75 | 元数据剥离 |
| WhatsApp | 800 | 70 | 元数据剥离 |

这些 profile 是**经验近似值**，不是字节级精确仿真，但足以测试 pHash / Copy-Move / C2PA 检测在重新编码后的鲁棒性。

---

## 五、引用要求

如果你在论文 / 报告中**直接使用了某学术数据集的官方 split**（不是这里的 mini 替身），必须按对应论文的 BibTeX 引用：

```bibtex
@inproceedings{zhu2023genimage,
  title  = {GenImage: A Million-Scale Benchmark for Detecting AI-Generated Image},
  author = {Zhu, Mingjian and Chen, Hanting and Yan, Qiangyu and others},
  booktitle = {NeurIPS}, year = {2023}
}

@inproceedings{tralic2013comofod,
  title  = {CoMoFoD - New Database for Copy-Move Forgery Detection},
  author = {Tralic, Dijana and Zupancic, Ivan and Grgic, Sonja and Grgic, Mislav},
  booktitle = {Proc. 55th International Symposium ELMAR-2013}, year = {2013}
}

@inproceedings{dong2013casia,
  title  = {CASIA Image Tampering Detection Evaluation Database},
  author = {Dong, Jing and Wang, Wei and Tan, Tieniu},
  booktitle = {IEEE ChinaSIP}, year = {2013}
}
```

合成 / 公有领域示例图（picsum / Wikimedia / NASA）无需引用。

---

## 六、跨平台说明

所有 fetcher 与 launder 脚本均为**纯 Python + Pillow + urllib**，在 Windows 与 macOS 上行为一致：

* 路径全部走 `pathlib.Path`，无 `\`/`/` 硬编码
* 网络请求统一 `timeout=20s`，失败即跳过，不挂任何调用方
* 输出目录 `mkdir(parents=True, exist_ok=True)`，无需提前创建
