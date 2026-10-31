# Z8 Full-Pool Shutter Sound — 1360ms 实验扩展

**基于 [South-Bridge/z8-custom-shutter-sound](https://github.com/South-Bridge/z8-custom-shutter-sound) 的机制分析与工具修改。原作者及贡献者的工作是本项目的基础；本项目的整池扩展由 PIPA12344 提供，未经原作者审阅或背书。**

> **实验工具，可能造成相机故障、无法启动、存储卡损坏或数据丢失，并可能影响保修。没有实机安全保证，没有保证可回刷或恢复。模拟器运行、CRC 和字节检查通过均不等于实机安全。请阅读 [风险与验证边界](docs/RISKS.md)。**
>
> 仓库只发布源码与分析文档。请自行提供合法取得的固件与有权使用的音频。这里不包含 Nikon 固件、固件模块、刷机成品、存储卡镜像或语音素材。工具不操作相机或存储卡。

## 做了什么

把 Nikon Z8 **C3.11** 中 B/C/D/E 的连续音频资源池合并使用，令 **B 的主段及前段请求播放完整 1360ms**，不绑定某一条语音或 1237ms 的示例时长。

| 项目 | 本项目行为 |
|---|---|
| PCM 池 | 261,120 字节 = 65,280 个立体声帧 = **1360ms** |
| 输入 | 48kHz、16-bit PCM、双声道 WAV，1..65,280 帧 |
| 小于 1360ms | 按原作者转换器补静音至整池大小，不变速 |
| 恰好 1360ms | 使用全部输入帧，保留原转换器的尾部渐隐与归一化 |
| 大于 1360ms | 明确报错；不偷偷裁切、压缩或改变速度 |
| B | 主段和前段都指向池首，长度返回 261,120 字节 |
| C/D/E | 原始声音被覆盖，仍按原来的短段读取池内片段或静音 |
| A 与高速连拍独立声音 | 本补丁不修改它们的资源和分派；不代表已实机验证 |

**这是一个共享长声音，不是四个独立的长音色。**

**1360ms 是资源容量和这两条路径的请求长度，不是任何快门速度下都能听到完整声音的保证。** 原厂 cap、慢门阶段切换、打断/重复行为没有被绕过。完整相机仿真和真实扬声器验证尚未完成。支持范围是一个已固定布局的 C3.11，不宣称跨固件、跨机型通用。

## 来源与改动

- 原作者：[South-Bridge](https://github.com/South-Bridge)，原项目采用 MIT 许可。
- 固定参考 commit：[6bfbb01](https://github.com/South-Bridge/z8-custom-shutter-sound/tree/6bfbb01c95859d490e1135e7d2927a2fbc619642)。
- 原项目的资源映射、kind 分派、初始化复制和 cap 分析，以及 S3 / [s3lemming](https://github.com/s3lemming) 的相关线索，是本扩展的重要基础。
- third_party/ 中的原脚本和 MIT 许可完整保留。音频转换直接调用其未改动的 load_wav，校验固定 SHA256；没有声称本项目仍使用原来的 340ms 补丁逻辑。
- 新增：B/C/D/E 整池复用、B 私有 32 位长度 getter、B 地址/长度表重定向、严格输入与修改范围检查、实际 ARM 指令的有界验证。
- 本项目没有复制 NikonFirmwarePatch 的 GPL 源码，也不打包其功能补丁。已有功能可以通过用户自行生成的干净 EG 作为基底保留；相关工具请遵守各自许可。

详细来源：[NOTICE.md](NOTICE.md)、[third_party/south_bridge/SOURCE.md](third_party/south_bridge/SOURCE.md)。技术说明：[docs/MECHANISM.md](docs/MECHANISM.md)。

## 安装

Python 3.10+，Windows / Linux / macOS。建议使用虚拟环境。

~~~sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: . .venv/bin/activate
python -m pip install -r requirements.txt
~~~

## 使用

### 1. 准备输入

从你自行取得的**官方 C3.11 完整更新包**中，使用你已核验的解包工具提取原始 EG：

- **81,807,711 字节，保留末尾两个 CRC 字节**。
- SHA256：f85e0138e2f5e660ece8560de62e0d12cb795e0e14983e50f20b61dce906c46c
- 完整约 99MB 更新包和去掉 CRC 的 QEMU MAIN 都不能代替这个输入。

若使用 [NikonFirmwarePatch](https://github.com/XinmiaoZhao/NikonFirmwarePatch)，请在你自己的该工具环境中查阅 z8prores/package.py 的 Package(...).eg 接口；这里不包含解包器或完整固件打包器。

准备不超过 1360ms 的标准 WAV。需要转换格式时，请显式处理；例如使用你已安装的 FFmpeg：

~~~sh
ffmpeg -i input.wav -ar 48000 -ac 2 -c:a pcm_s16le clip.wav
~~~

此命令只转换格式，不缩短音频；如果超时长，请自行编辑后再输入。

### 2. 构建并执行检查

~~~sh
python full_pool.py --stock-eg /private/original-eg.bi --wav /private/clip.wav --out local/test-1360
~~~

本项目与 [NikonFirmwarePatch 四项功能修改工程](https://github.com/XinmiaoZhao/NikonFirmwarePatch)兼容，可搭配使用。**请使用未修改过快门声的干净 C3.11 基底。**

### 3. 输出

| 文件 | 用途 |
|---|---|
| patched-eg.bi | 含 CRC 的实验 EG，供你自己的经过核验的封装流程使用 |
| modified-main.bi | 去掉 EG 末尾 CRC，供 QEMU 实验；启动器需要显式接受其新哈希 |
| preview.wav | 转换后的完整 1360ms 音源；这是素材试听，不是相机录音 |
| manifest.json | 实际输入/输出哈希、补静音帧数、字节及 ARM 检查记录、验证边界 |
| SHA256SUMS.txt | 三个输出文件的 SHA256 |

**工具不生成完整更新包，不修改版本号，也不会自动刷写。不要把 patched-eg.bi 改名成更新包直接放进相机。** 外层封装、版本身份、其他功能配方和完整更新包校验应由你的整合工具负责。

没有输出目录覆盖；输入文件保持只读。未知固件、已修改的声音子系统、空 WAV、格式不符、超长或截断文件都会拒绝。

## 检查范围

- 原始 EG 精确 SHA256、长度和 CRC。
- 输出只改动声明的五个窗口及 EG CRC；基底其他字节不变。
- 在 Unicorn 中执行用户固件里的原始 ARM64 初始化与地址/长度分发，确认完整 PCM 在 RAM 中重建，所有 16 个资源留在原池内。
- 执行三段原始 cap 处理代码。cap=0 时测试片段保留整池，非零 cap 仍可能截短。
- 引用检查只覆盖直接 B/BL 和 64 位指针字面量，不是任意计算调用不存在的证明。
- 不模拟完整 RTOS、音频 DMA、扬声器、真实镜头与拍摄时序，不承诺实机完整播放或恢复。

测试方法和已知结论：[docs/VALIDATION.md](docs/VALIDATION.md)。

## 许可与贡献

本项目原创代码采用 [MIT](LICENSE)。原作者 MIT 许可保留在 [third_party/south_bridge/LICENSE](third_party/south_bridge/LICENSE)。软件许可不授予 Nikon 固件或第三方音频的权利。

欢迎提交不含固件、音频素材或密钥的代码与问题报告。报告请附工具版本、固件版本、哈希、复现步骤和经过检查的日志；不要上传完整固件或相机卡镜像。项目与 Nikon Corporation 无隶属、认可或支持关系。
