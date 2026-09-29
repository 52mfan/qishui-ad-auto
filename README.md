# 汽水音乐自动看广告脚本

基于 **ADB + OCR** 的汽水音乐「看广告领时长」自动化工具。  
识别屏幕上的 **领取奖励 / 继续观看 / 领取成功** 等按钮并自动点击，支持广告倒计时等待、直播间秒退、防卡死、点击抖动防检测。

> 仅供个人学习与自动化测试使用。请遵守目标应用的用户协议与当地法律法规，风险自负。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| OCR 识别按钮 | RapidOCR 识别「领取奖励 / 领取 / 继续观看 / 领取成功 / 我知道了」 |
| 倒计时等待 | 识别「N秒后可领奖励」后按秒休眠，结束立刻探查领取 |
| 直播间秒退 | 顶部出现「关注 / 更多直播」立即返回 |
| 防卡死 | 连续未命中自动返回 |
| 坐标换算 | 影像分辨率 ≠ 真机分辨率时自动换算点击坐标 |
| 点击抖动 | 坐标随机偏移、间隔随机浮动，降低脚本特征 |
| GUI 版 | 实时预览、OCR 信息表、手机状态（电量/网络）、WiFi ADB、熄屏运行 |
| 命令行版 | 轻量挂机 |
| 可选 scrcpy | 高帧率实时预览（约 30 FPS），无 scrcpy 时自动回退截图 |

---

## 目录结构

```
qishui-ad-auto/
├── README.md
├── LICENSE
├── requirements.txt
├── 启动.bat                 # Windows 一键启动（可选）
├── qishui_ad_gui.py         # GUI 版（推荐）
├── qishui_ad_bot.py         # 命令行版
├── live_screen.py           # 实时影像（scrcpy / 截图回退）
└── docs/
    ├── 01-手机设置.md
    ├── 02-电脑环境.md
    ├── 03-使用教程.md
    └── 04-打包EXE.md
```

---

## 快速开始

### 1. 手机设置（只需一次）

详见 [docs/01-手机设置.md](docs/01-手机设置.md)

- 打开 **开发者选项**
- 开启 **USB 调试**
- 小米 / vivo 等请再开 **USB 调试（安全设置）** 或 **允许模拟点击**
- 数据线连接电脑，手机弹窗点「允许」

### 2. 安装电脑环境

详见 [docs/02-电脑环境.md](docs/02-电脑环境.md)

```bash
# 需要 Python 3.9+
pip install -r requirements.txt
```

还需 **adb**（platform-tools）。可把 `platform-tools` 目录放到本项目下，或加入系统 PATH。

### 3. 运行

```bash
# GUI 版（推荐）
python qishui_ad_gui.py

# 命令行版
python qishui_ad_bot.py
```

或 Windows 下双击 `启动.bat`。

### 4. 开始挂机

1. 手机打开 **汽水音乐** → 进入 **看广告领时长** 页面
2. 保持屏幕常亮（GUI 可勾选「熄屏运行」）
3. 点击 GUI「启动」或等待 CLI 开始识别
4. 停止：GUI 点「停止」；CLI 按 `Ctrl+C`

---

## 详细教程

| 文档 | 内容 |
|------|------|
| [docs/01-手机设置.md](docs/01-手机设置.md) | 开发者选项、USB 调试、厂商特殊设置 |
| [docs/02-电脑环境.md](docs/02-电脑环境.md) | Python、依赖、adb 安装 |
| [docs/03-使用教程.md](docs/03-使用教程.md) | GUI 各区域说明、常见问题 |
| [docs/04-打包EXE.md](docs/04-打包EXE.md) | 用 PyInstaller 打包单文件 exe |

---

## 可选：scrcpy 高帧率预览

GUI 内预览优先使用 **scrcpy H.264 流**（约 30 FPS）。若没有 scrcpy，会自动回退为截图模式（约 1.5 FPS，不影响点击）。

安装方式：

1. 下载 [scrcpy](https://github.com/Genymobile/scrcpy/releases) Windows 包
2. 解压后把整个 `scrcpy` 文件夹放到 **与 exe / 源码同级** 目录：

```
qishui-ad-auto/
├── qishui_ad_gui.py   (或 QishuiAdGUI.exe)
└── scrcpy/
    ├── scrcpy.exe
    ├── scrcpy-server
    └── ...
```

---

## 工作原理

```
ADB 截屏 / scrcpy 推流
        ↓
   OCR 识别文字 (RapidOCR)
        ↓
 命中「领取奖励」等目标？ ──否──→ 等待 / 防卡死返回
        ↓ 是
 坐标换算 + 随机抖动
        ↓
   ADB tap 点击
```

- 广告倒计时文案（如「14秒后可领奖励」）**不会**被误点，只用于计算等待时间
- 「继续观看」优先点**底部**按钮，避免点到顶部同名关闭按钮

---

## 常见问题

**Q: 提示「截图失败」/ 未检测到设备？**  
A: 执行 `adb devices`，应显示 `device`。若为 `unauthorized`，请在手机上点允许。

**Q: 识别到了但不点击？**  
A: 看日志「拒绝: xxx 出界」——按钮可能在 ROI 外，可放宽 `qishui_ad_gui.py` 里 `TARGET_ROI`。

**Q: 一直显示「未命中」？**  
A: 确认手机停在「看广告领时长」相关页面，且文案含目标按钮。

**Q: CMD 黑框一闪？**  
A: GUI 版已隐藏 adb 子进程窗口；若仍出现，请使用 `--windowed` 打包的 exe。

---

## 免责声明

本项目仅供学习、研究与个人效率工具用途。使用本软件产生的一切后果由使用者自行承担。请勿用于破坏服务公平性、批量薅羊毛或其他可能违反用户协议的行为。

---

## License

[MIT](LICENSE)
