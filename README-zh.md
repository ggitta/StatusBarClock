# StatusBarClock

StatusBarClock 是一个用 Python、rumps 和 AppKit 写的 macOS 菜单栏时钟。它使用系统原生文字渲染菜单栏标题，不走位图图标方案，所以宽度会按文字内容自然适配。

[English README](README.md)

## 功能

- 在 macOS 菜单栏显示带城市前缀的时间，例如 `东京 09:41`。
- 可从内置 IANA 时区中选择，也可以输入自定义时区名。
- 可使用预设颜色或 HEX 值自定义菜单栏文字颜色。
- 可切换秒数、日期和 24 小时制。
- 可通过 NTP 服务器同步应用内显示时间偏移，不修改系统时间。
- 内置常用 NTP 服务器，包括 `time.apple.com`。
- 可在菜单中开启或关闭开机自启动。
- 配置保存到 `~/Library/Application Support/StatusBarClock/config.json`。

## 环境要求

- macOS 10.15 或更新版本
- Python 3.9 或更新版本

项目依赖在 `requirements.txt` 中。运行依赖包括：

- `rumps`
- `pyobjc-framework-Cocoa`
- `ntplib`

`py2app` 也放在同一个文件里，用于本地打包 `.app`。
打包配置会在当前 Python 需要外部 `libffi` 时自动把它带进 `.app`，所以原生 Python 和 Conda Python 都可以使用同一个打包脚本。

## 源码运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python clock_app.py
```

## 打包

```bash
./build_app.sh
```

打包产物位置：

```text
dist/StatusBarClock.app
```

应用图标在 `setup.py` 中配置，实际打包使用：

```text
assets/StatusBarClock.icns
```

可编辑的 SVG 源文件是：

```text
assets/logo.svg
```

## 安装

打包完成后，把 `.app` 复制到 `/Applications`：

```bash
cp -R dist/StatusBarClock.app /Applications/
```

然后打开 `StatusBarClock.app`。本地构建的应用默认未签名，macOS 首次启动时可能拦截。如果遇到拦截，可以右键选择 `打开`，或到系统设置中允许打开。

## 说明

StatusBarClock 不会修改 macOS 系统时间。NTP 同步只计算时间偏移，并把偏移用于菜单栏显示。

当前打包脚本生成的是未签名的本地应用。如果要公开发布二进制版本，需要使用 Apple Developer ID 对应用签名并公证。
