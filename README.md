<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:FF4D4F,50:FF7A45,100:FFD666&height=220&section=header&text=&animation=tw" />

<br/>

# <img src="https://img.shields.io/badge/%F0%9F%A5%A4-QISHUI__AD__AUTO-FF4D4F?style=for-the-badge&labelColor=0A0A0A" />

## **汽水音乐 · 自动看广告**

### `识别 · 等待 · 点击 · 挂机`

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=22&duration=2800&pause=800&color=FF7A45&center=true&vCenter=true&width=560&lines=ADB+%2B+OCR+Automation;Just+Run+%26+Walk+Away;Stars+Welcome+%E2%AD%90" />

<br/>

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![ONNX](https://img.shields.io/badge/RapidOCR-ONNX-FF6B00?style=for-the-badge&logo=paddlepaddle&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-00C853?style=for-the-badge&logo=opensourceinitiative&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)

<br/>

[![GitHub release](https://img.shields.io/github/v/release/52mfan/qishui-ad-auto?style=for-the-badge&color=FF4D4F&label=RELEASE)](https://github.com/52mfan/qishui-ad-auto/releases)
[![Stars](https://img.shields.io/github/stars/52mfan/qishui-ad-auto?style=for-the-badge&color=FFD700&logo=github)](https://github.com/52mfan/qishui-ad-auto/stargazers)
[![Forks](https://img.shields.io/github/forks/52mfan/qishui-ad-auto?style=for-the-badge&color=00B894&logo=github)](https://github.com/52mfan/qishui-ad-auto/network)
[![Issues](https://img.shields.io/github/issues/52mfan/qishui-ad-auto?style=for-the-badge&color=6C5CE7)](https://github.com/52mfan/qishui-ad-auto/issues)

<br/>

**[`🔥 一键下载`](https://github.com/52mfan/qishui-ad-auto/releases)** ─── **[`⚡ 快速开始`](#-光速上手)** ─── **[`🧠 原理`](#-工作原理)** ─── **[`📚 文档`](#-文档)** ─── **[`❓ FAQ`](#-faq)**

</div>

---

## <img src="https://img.shields.io/badge/%E2%9C%A8-WHY-FF4D4F?style=for-the-badge" />

每天手动点广告，枯燥、费眼、还容易漏。

> 广告倒计时…… 3 2 1 → **领取奖励** → 再来一轮 → 卧槽进直播间了 → 返回 → ……

把重复劳动交给脚本，**你负责挂机，它负责点击**。

---

## <img src="https://img.shields.io/badge/%F0%9F%9A%80-FEATURES-FF7A45?style=for-the-badge" />

<br/>

<table>
<tr>
<td align="center" width="50%" bgcolor="#111111">
<br/>
<img src="https://img.shields.io/badge/%20-01-FF4D4F?style=for-the-badge" /><br/><br/>

### 🧠 **看得懂**

本地 OCR 秒识按钮<br/>
`领取奖励` `继续观看` `领取成功`<br/>
错字缺字也能匹配

<br/>
</td>
<td align="center" width="50%" bgcolor="#111111">
<br/>
<img src="https://img.shields.io/badge/%20-02-FF7A45?style=for-the-badge" /><br/><br/>

### ⏱ **等得准**

解析「14秒后可领奖励」<br/>
倒计时结束 **立刻** 点<br/>
不误点、不空转

<br/>
</td>
</tr>
<tr>
<td align="center" width="50%" bgcolor="#111111">
<br/>
<img src="https://img.shields.io/badge/%20-03-FFD666?style=for-the-badge" /><br/><br/>

### 🎯 **点得像人**

坐标 ±6px 抖动<br/>
点击间隔随机浮动<br/>
降低脚本特征

<br/>
</td>
<td align="center" width="50%" bgcolor="#111111">
<br/>
<img src="https://img.shields.io/badge/%20-04-00B894?style=for-the-badge" /><br/><br/>

### 🖥 **挂得省心**

GUI 实时预览 · 手机状态<br/>
直播间秒退 · 防卡死<br/>
熄屏也能跑

<br/>
</td>
</tr>
</table>

---

## <img src="https://img.shields.io/badge/%E2%9A%99%EF%B8%8F-ARCHITECTURE-00B894?style=for-the-badge" />

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor': '#FF4D4F', 'primaryTextColor':'#fff', 'primaryBorderColor':'#FF7A45', 'lineColor':'#FFD666', 'secondaryColor':'#1A1A2E', 'tertiaryColor':'#0A0A0A'}}}%
flowchart TB
    A[📱 汽水音乐<br/>看广告页面] --> B[📡 scrcpy H.264 流<br/>/ screencap]
    B --> C[🧠 RapidOCR<br/>本地文字识别]
    C --> D{决策引擎}
    D -->|🎯 领取奖励| E[抖动点击]
    D -->|⏱ N秒后可领| F[精准休眠]
    D -->|🚪 直播间| G[秒退返回]
    D -->|💤 连续未命中| H[防卡死]
    E --> A
    F --> C
    G --> A
    H --> A

    style A fill:#FF4D4F,color:#fff
    style C fill:#6C5CE7,color:#fff
    style E fill:#00B894,color:#fff
    style F fill:#FF7A45,color:#fff
    style G fill:#0984E3,color:#fff
    style H fill:#636E72,color:#fff
```

---

## <img src="https://img.shields.io/badge/%F0%9F%92%BB-TECH-6C5CE7?style=for-the-badge" />

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" />
  <img src="https://img.shields.io/badge/ONNX-000000?style=for-the-badge&logo=onnxruntime&logoColor=white" />
  <img src="https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&logo=android&logoColor=white" />
  <img src="https://img.shields.io/badge/ADB-0A0A0A?style=for-the-badge&logo=androidstudio&logoColor=white" />
  <img src="https://img.shields.io/badge/scrcpy-111111?style=for-the-badge&logo=obsstudio&logoColor=white" />
</p>

---

## <img src="https://img.shields.io/badge/%E2%9A%A1-光速上手-FFD666?style=for-the-badge" />

### 0️⃣ 环境

| 🖥 电脑 | 📱 手机 |
|:--:|:--:|
| Python 3.9+ | Android 8+ |
| platform-tools (adb) | USB 调试已开 |
| Windows 推荐 | 模拟点击已开（小米/vivo） |

### 1️⃣ 安装

```bash
git clone https://github.com/52mfan/qishui-ad-auto.git
cd qishui-ad-auto
pip install -r requirements.txt
```

<details>
<summary>📦 <b>不想装 Python？直接下 EXE</b></summary>
<br/>

👉 [Releases 页面](https://github.com/52mfan/qishui-ad-auto/releases) → 下载 `QishuiAdGUI.exe` → 双击运行

</details>

### 2️⃣ 运行

```bash
python qishui_ad_gui.py
```

### 3️⃣ 挂机

```bash
# 手机打开：汽水音乐 → 看广告领时长
# 电脑点击：▶ 启动
```

<details>
<summary>📱 <b>手机端详细设置</b></summary>
<br/>

1. 设置 → 关于手机 → 连点版本号 7 次  
2. 开发者选项 → USB 调试  
3. 小米 / vivo → 允许模拟点击  
4. 连接电脑 → 弹窗点允许  
5. `adb devices` 看到 `device` ✅  

完整教程：[docs/01-手机设置.md](docs/01-手机设置.md)

</details>

---

## <img src="https://img.shields.io/badge/%F0%9F%93%BA-PREVIEW-E84393?style=for-the-badge" />

```
  ╔═══════════════════════╦══════════════════════════╗
  ║      实 时 影 像      ║       手 机 信 息        ║
  ║                       ║  Xiaomi M2007J1SC        ║
  ║    ┌─────────────┐    ║  Android 13 · 1080×2340  ║
  ║    │  📺 广告中  │    ║  🔋 97%  ⚡ 充电中        ║
  ║    │  14秒后可领 │    ║  📶 WiFi · 192.168.x.x   ║
  ║    └─────────────┘    ║                          ║
  ║      scrcpy · 30fps   ╠══════════════════════════╣
  ║                       ║       重 点 识 别        ║
  ║                       ║  领取奖励    1.00  ✔     ║
  ║                       ║  继续观看    0.99        ║
  ║                       ╠══════════════════════════╣
  ║                       ║       运 行 日 志        ║
  ║                       ║  🎯 点击「领取奖励」     ║
  ║                       ║  ⏱ 倒计时 14s 等待中     ║
  ╚═══════════════════════╩══════════════════════════╝
```

---

## <img src="https://img.shields.io/badge/%E2%9B%84%EF%B8%8F-TERMINAL-0984E3?style=for-the-badge" />

```console
$ python qishui_ad_bot.py

🚀 汽水音乐 · 自动看广告脚本
   ADB     : platform-tools\adb.exe
   设备    : d7458733 (M2007J1SC)
   目标    : ['领取奖励', '领取', '继续观看', ...]
   真机分辨率 1080x2340 · 影像流 540x1170
📡 实时影像已启动
✅ OCR 就绪

⏱ 广告倒计时 14s，等待 13.8s 后探查领取奖励
🎯 点击「领取奖励」 score=1.00 帧(270,618)→机(540,1236)
⚡ 「领取奖励」已点，立即继续识别
🎯 点击「继续观看」 score=1.00 帧(270,1162)→机(540,2324)
🎯 点击「领取成功」 score=1.00 @ (980,120)
```

---

## <img src="https://img.shields.io/badge/%E2%9A%99%EF%B8%8F-CONFIG-636E72?style=for-the-badge" />

```python
TARGETS        = ["领取奖励", "领取", "继续观看", "领取成功", "我知道了"]
OCR_SCORE      = 0.55    # 识别置信度
CLICK_JITTER   = 6       # 点击抖动像素
POLL_INTERVAL  = 1.2     # 轮询秒数
```

<details>
<summary>更多配置项</summary>

| 配置 | 说明 |
|------|------|
| `TARGET_ROI` | 按钮允许出现的屏幕区域 |
| `CLICK_COOLDOWN` | 点击后冷却 |
| `MISS_BACK_THRESHOLD` | 防卡死阈值 |
| `NO_COOLDOWN_TARGETS` | 点击后不冷却的目标 |
| `SAVE_DEBUG` | 保存点击调试图 |

</details>

---

## <img src="https://img.shields.io/badge/%E2%9D%93-FAQ-FDCB6E?style=for-the-badge" />

| ❓ 问题 | 💡 答案 |
|--------|---------|
| 会误点倒计时吗？ | 不会，只等待不点击 |
| 识别到却不点？ | 放宽 `TARGET_ROI` |
| 预览很卡？ | 装 scrcpy 提升到 30fps |
| 会封号吗？ | 请控制频率、遵守协议、自负风险 |
| 支持 Mac 吗？ | 理论可以，需自备 adb |

---

## <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F-COMMUNITY-FF6B81?style=for-the-badge" />

<div align="center">

欢迎 **Issue** / **PR** / **Star**

<br/>

[![GitHub stars](https://img.shields.io/github/stars/52mfan/qishui-ad-auto?style=social)](https://github.com/52mfan/qishui-ad-auto/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/52mfan/qishui-ad-auto?style=social)](https://github.com/52mfan/qishui-ad-auto/network)

</div>

---

## <img src="https://img.shields.io/badge/%F0%9F%93%96-LICENSE-2ECC71?style=for-the-badge" />

> ⚠️ **免责声明**  
> 本项目仅供学习、研究与个人效率用途。  
> 请遵守目标应用用户协议与法律法规，勿用于批量滥用。  
> 使用本软件的一切后果由使用者自行承担。

📄 [MIT License](LICENSE)

---

<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:FFD666,50:FF7A45,100:FF4D4F&height=180&section=footer" />

<br/>

**⭐ 如果觉得不错，点个 Star 再走呀 ⭐**

<br/>

![Visitors](https://komarev.com/ghpvc/?username=52mfan&label=visitors&color=FF4D4F&style=for-the-badge)

</div>
