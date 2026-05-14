# Easy-Wav2Lip（中文使用指南）

基于 Wav2Lip 的 AI 唇形同步工具，支持表情控制和数据分析功能，大幅优化了原版 Wav2Lip 的速度和画质。

## 核心优势

### 更快

| 版本 | 9秒 720p 60fps 测试耗时 |
|------|----------------------|
| 原版 Wav2Lip | 6 分 53 秒 |
| Easy-Wav2Lip | **56 秒** |
| 重复运行同一视频（复用缓存） | **25 秒** |

### 更好看

- 修复了原版 Wav2Lip 的唇部视觉瑕疵
- 三档质量可选：Fast / Improved / Enhanced
- Enhanced 模式使用 GFPGAN 进行人脸增强和超分辨率

## 目录结构

```
Easy-Wav2Lip/
├── inference.py              # 核心推理脚本
├── pipeline.py               # 处理流水线
├── run.py                    # 主运行脚本
├── app.py                    # Web 应用入口
├── analytics.py              # 分析统计
├── expression_control.py     # 表情控制
├── config.ini                # 配置文件
├── requirements.txt          # Python 依赖
├── checkpoints/              # 模型权重（需下载）
├── gfpgan/                   # GFPGAN 人脸增强
├── models/                   # 其他模型文件
├── static/                   # 静态资源
└── templates/                # Web 模板
```

## 环境要求

- **GPU**: NVIDIA GPU（推荐 RTX 3060 以上）
- **系统**: Windows 10/11 64位 / Linux
- **依赖**: Python 3.10.11（推荐）、Git、FFmpeg、CUDA 12+

## 安装方式

### 方式一：Windows 一键安装（推荐）

1. 下载 [Easy-Wav2Lip.bat](https://github.com/anothermartz/Easy-Wav2Lip/releases/download/v8.1_release/Easy-Wav2Lip_v8.1.bat)
2. 将 `.bat` 文件放入一个独立文件夹
3. 双击运行，按提示完成环境配置
4. 自动检查更新并运行

> 注意：确保 NVIDIA 驱动为最新版本，以支持 CUDA 12。

### 方式二：Google Colab（最快）

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/anothermartz/Easy-Wav2Lip/blob/v8.1/Easy_Wav2Lip_v8.1.ipynb)

访问 [Easy_Wav2Lip_v8.1.ipynb](https://colab.research.google.com/github/anothermartz/Easy-Wav2Lip/blob/v8.1/Easy_Wav2Lip_v8.1.ipynb)，只需运行 2 个代码单元格即可。

### 方式三：手动安装

```bash
# 1. 克隆代码
git clone https://github.com/anothermartz/Easy-Wav2Lip.git
cd Easy-Wav2Lip

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装模型
python install.py

# 4. 运行
python run.py
# 或循环运行模式
./run_loop.sh     # Linux
call run_loop.bat  # Windows
```

## 模型文件下载

模型文件需单独下载，放到 `checkpoints/` 目录：

| 文件 | 说明 | 大小 | 下载地址 |
|------|------|------|---------|
| `Wav2Lip_GAN.pth` | GAN 版本（推荐） | ~200MB | [GitHub Releases](https://github.com/anothermartz/Easy-Wav2Lip/releases) |
| `Wav2Lip.pth` | 原始版本 | ~200MB | 同上 |
| `mobilenet.pth` | 人脸检测器 | ~14MB | 同上 |
| `shape_predictor_68_face_landmarks.dat` | 68点人脸关键点 | ~100MB | [dlib-models](https://github.com/AKSHAYUBHAT/dlib-models) |

GFPGAN 增强模型（用于 Enhanced 质量模式）：

| 文件 | 说明 | 下载地址 |
|------|------|---------|
| `GFPGANv1.4.pth` | 人脸修复权重 | [TencentARC/GFPGAN](https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth) |

放入 `gfpgan/` 目录。

## 快速开始

### 方式一：配置文件

1. 首次运行后会自动生成 `config.ini`
2. 填写视频路径和音频路径：

```ini
[INPUT]
video_file = C:\Videos\my_face.mp4
vocal_file = C:\Audio\voice.wav

[OUTPUT]
output_height = 720

[QUALITY]
quality = Enhanced   ; Fast / Improved / Enhanced
wav2lip_version = Wav2Lip_GAN  ; Wav2Lip / Wav2Lip_GAN
```

3. 保存并关闭 `config.ini`，自动开始处理

### 方式二：命令行参数

```bash
python run.py --video input.mp4 --audio voice.wav --quality Enhanced --output_height 720
```

### 方式三：Python API

```python
from inference import Wav2LipInference

inference = Wav2LipInference()

# 单个文件处理
result = inference.process(
    video_path="input.mp4",
    audio_path="voice.wav",
    quality="Enhanced",
    output_height=720
)

# 批量处理
from pipeline import BatchProcessor
processor = BatchProcessor()
processor.process_batch(
    video_dir="videos/",
    audio_dir="audios/",
    output_dir="output/"
)
```

## 配置参数详解

### 质量模式

| 模式 | 说明 | 速度 | 画质 |
|------|------|------|------|
| Fast | 仅 Wav2Lip | 最快 | 一般 |
| Improved | Wav2Lip + 羽化蒙版 |较快 | 较好 |
| Enhanced | + GFPGAN 人脸增强 | 较慢 | **最佳** |

### Wav2Lip 版本

| 版本 | 优点 | 缺点 |
|------|------|------|
| Wav2Lip | 唇形同步更准确，能保持闭嘴状态 | 偶尔出现牙齿缺失 |
| Wav2Lip_GAN | 视觉效果更好，保持原始表情 | 闭嘴遮罩效果略差 |

### Padding（人脸边距）

控制人脸裁剪区域的大小：

| 参数 | 说明 | 示例 |
|------|------|------|
| U（上） | 负值减少，正值增加 | U = -10 → 裁剪顶部 5px |
| D（下） | 增加底部边距 | D = 10 → 增加底部 10px |
| L（左）/ R（右） | 控制左右边距 | 建议底部加 10px |

### Mask（蒙版）

| 参数 | 说明 |
|------|------|
| size | 蒙版覆盖区域大小 |
| feathering | 蒙版边缘羽化程度 |
| mouth_tracking | 实时跟踪嘴巴位置（更慢但更准） |
| debug_mask | 显示蒙版调试视图 |

### 其他选项

| 参数 | 说明 |
|------|------|
| `nosmooth` | 禁用帧间平滑（适合快速运动画面） |
| `batch_processing` | 批量处理多个文件 |
| `output_suffix` | 输出文件后缀 |
| `preview_input` | 处理前预览输入文件 |
| `preview_settings` | 仅渲染 1 帧用于参数调试 |

## 最佳实践

### 视频要求

- **必须**：画面中所有帧都包含人脸（否则会失败）
- **建议**：720p 以下、30 秒以内、30fps
- **避免**：侧脸、面部遮挡、多人画面（会随机选择一张脸）
- **格式**：推荐 h264 编码的 MP4 文件

### 音频要求

- 推荐保存为 WAV 格式，时长与输入视频相同
- 支持 MP3、WAV 等常见格式
- **注意**：处理后视频会比原视频短约 80ms，建议音频稍长

### 获取最佳效果

- **预处理**：在唇形同步前，将语音与口型和表情对齐
- **先小后大**：先用小片段测试参数，熟悉后再处理大文件
- **素材选择**：选择正面、光线充足、表情自然的视频

## 批量处理

将文件按数字编号命名，放入同一文件夹：

```
videos/
├── Video1.mp4
├── Video2.mp4
├── Video3.mp4
└── ...
```

在 `config.ini` 中选择 `Video1.mp4`，程序会自动按顺序处理 Video1、Video2、Video3......

也支持：一个视频 + 多个音频（同一视频说不同话），或多个视频 + 一个音频（不同人说同一句话）。

## 与 DigitalHumanMVP 集成

本项目作为 DigitalHumanMVP 的唇形同步引擎使用。在 DigitalHumanMVP 的 `config.yaml` 中配置：

```yaml
WAV2LIP_ROOT: "D:/hecheng/Easy-Wav2Lip"
```

## 常见问题

### Q: 报错 "No face detected"

确保视频中每帧都有清晰的人脸，避免侧脸、遮挡或多人。

### Q: 显存不足（OOM）

- 降低 `output_height`（如设为 480）
- 使用 Fast 质量模式
- 缩短视频时长

### Q: 处理后嘴唇位置偏移

调整 `Padding` 参数的 U/D/L/R 值，覆盖正确的人脸区域。

### Q: 模型下载失败

手动从 GitHub Releases 页面下载所有 `.pth` 文件，放入 `checkpoints/` 目录。

## Credits

- [The Original Wav2Lip](https://github.com/Rudrabha/Wav2Lip)
- [cog-Wav2Lip](https://github.com/devxpy/cog-Wav2Lip)（速度优化）
- [GFPGAN](https://github.com/TencentARC/GFPGAN)（人脸增强）
- [wav2lip-hq-updated-ESRGAN](https://github.com/GucciFlipFlops1917/wav2lip-hq-updated-ESRGAN)

## License

MIT License
