# 打包为 EXE（可选）

给没有 Python 环境的用户使用时，可打包成单文件 exe。

## 1. 安装 PyInstaller

```bash
pip install pyinstaller
```

## 2. 打包 GUI 版

```bash
python -m PyInstaller --noconfirm --onefile --windowed --name QishuiAdGUI ^
  --collect-all rapidocr_onnxruntime ^
  --collect-all onnxruntime ^
  --collect-all cv2 ^
  --hidden-import numpy ^
  --hidden-import PIL ^
  --hidden-import PIL.ImageTk ^
  --hidden-import tkinter ^
  --hidden-import live_screen ^
  --hidden-import win32file ^
  --hidden-import win32pipe ^
  --hidden-import av ^
  qishui_ad_gui.py
```

PowerShell 用反引号 `` ` `` 换行，或写成一行。

产物：`dist\QishuiAdGUI.exe`

## 3. 打包命令行版

```bash
python -m PyInstaller --noconfirm --onefile --console --name QishuiAdBot ^
  --collect-all rapidocr_onnxruntime ^
  --collect-all onnxruntime ^
  --collect-all cv2 ^
  --hidden-import numpy ^
  --hidden-import live_screen ^
  qishui_ad_bot.py
```

## 4. 发布目录结构

```
发布包/
├── QishuiAdGUI.exe
└── scrcpy/          # 可选，高帧率预览
    ├── scrcpy.exe
    └── ...
```

**不要只拷贝 exe**，若使用 scrcpy 预览，需连同 `scrcpy\` 文件夹一起分发。

## 5. 说明

- OCR 模型会打进 exe，体积约 100MB+ 属正常
- 首次启动会解压临时文件并加载 OCR，约几秒
- `--windowed` 用于 GUI 无黑框；命令行版用 `--console`
