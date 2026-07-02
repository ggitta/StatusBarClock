#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS 状态栏时钟
================
基于 rumps 的菜单栏时钟小工具(纯文字模式)。

功能:
  - 状态栏实时显示时间(原生文字渲染,自动适应宽度,不会被压缩)
  - 可自定义文字(前景)颜色
  - 可选时区(内置常用时区 + 自定义 IANA 时区名),时间前会带上城市名前缀
  - 可选时间同步服务器(内置常用 NTP 服务器,含苹果官方 time.apple.com)
  - 时间同步仅用于校正"显示"的时间(计算与系统时钟的偏移量),不会修改系统时钟

说明:
  macOS 菜单栏原生不支持自定义"背景色"(系统会强制跟随浅色/深色模式的
  统一背景),因此这里只支持自定义文字颜色,通过 AppKit 的
  NSAttributedString 直接为菜单栏标题上色;文字本身仍由系统原生渲染,
  宽度自动适配,不存在位图图标那种像素/点换算导致挤压的问题。

依赖:
    pip3 install rumps ntplib pyobjc-framework-Cocoa

运行:
    python3 clock_app.py
"""

import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone as dt_timezone

import rumps

try:
    from zoneinfo import ZoneInfo
    HAVE_ZONEINFO = True
except ImportError:  # Python < 3.9 兜底
    HAVE_ZONEINFO = False

try:
    import ntplib
    HAVE_NTPLIB = True
except ImportError:
    HAVE_NTPLIB = False

try:
    from AppKit import (
        NSColor,
        NSFont,
        NSMutableAttributedString,
        NSForegroundColorAttributeName,
        NSFontAttributeName,
    )
    HAVE_APPKIT = True
except ImportError:
    HAVE_APPKIT = False


# --------------------------------------------------------------------------
# 配置存储
# --------------------------------------------------------------------------

APP_SUPPORT_DIR = os.path.expanduser(
    "~/Library/Application Support/StatusBarClock"
)
CONFIG_PATH = os.path.join(APP_SUPPORT_DIR, "config.json")

# 开机自启动通过 LaunchAgent 实现(适用于直接运行 .py 脚本的场景;
# 如果之后打包成 .app,也可以改用 ServiceManagement/SMAppService)
LAUNCH_AGENT_LABEL = "com.statusbarclock.autolaunch"
LAUNCH_AGENT_PATH = os.path.expanduser(
    f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist"
)


def is_autostart_enabled():
    return os.path.exists(LAUNCH_AGENT_PATH)


def enable_autostart():
    """写入 LaunchAgent plist 并通过 launchctl 加载,实现开机自启动。"""
    os.makedirs(os.path.dirname(LAUNCH_AGENT_PATH), exist_ok=True)
    os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
    if getattr(sys, "frozen", False):
        program_arguments = [sys.executable]
    else:
        script_path = os.path.abspath(__file__)
        program_arguments = [sys.executable, script_path]

    plist_data = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": program_arguments,
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": os.path.join(APP_SUPPORT_DIR, "autostart.log"),
        "StandardErrorPath": os.path.join(APP_SUPPORT_DIR, "autostart.err.log"),
    }
    try:
        with open(LAUNCH_AGENT_PATH, "wb") as f:
            plistlib.dump(plist_data, f)
    except Exception as e:
        return False, f"写入 plist 失败: {e}"

    # 先卸载(忽略错误,可能本来就没加载),再加载
    subprocess.run(
        ["launchctl", "unload", "-w", LAUNCH_AGENT_PATH],
        capture_output=True, text=True,
    )
    result = subprocess.run(
        ["launchctl", "load", "-w", LAUNCH_AGENT_PATH],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "launchctl load 失败"
    return True, None


def disable_autostart():
    if not os.path.exists(LAUNCH_AGENT_PATH):
        return True, None
    subprocess.run(
        ["launchctl", "unload", "-w", LAUNCH_AGENT_PATH],
        capture_output=True, text=True,
    )
    try:
        os.remove(LAUNCH_AGENT_PATH)
    except Exception as e:
        return False, f"删除 plist 失败: {e}"
    return True, None


DEFAULT_CONFIG = {
    "fg_color": "#00FF88",      # 文字(前景)颜色
    "timezone": "Asia/Shanghai",
    "ntp_server": "time.apple.com",
    "show_seconds": False,
    "hour_24": True,
    "show_date": False,
    "auto_sync_minutes": 30,    # 自动同步间隔(分钟), 0 表示不自动同步
}

# 内置常用 NTP 服务器(必须包含苹果官方)
BUILTIN_NTP_SERVERS = [
    ("苹果官方 (Apple)", "time.apple.com"),
    ("苹果官方备用", "time.euro.apple.com"),
    ("Google", "time.google.com"),
    ("NIST (美国)", "time.nist.gov"),
    ("微软 (Windows)", "time.windows.com"),
    ("阿里云", "ntp.aliyun.com"),
    ("腾讯云", "ntp.tencent.com"),
    ("NTP Pool (全球)", "pool.ntp.org"),
    ("NTP Pool (中国)", "cn.pool.ntp.org"),
]

# 内置常用时区
BUILTIN_TIMEZONES = [
    ("北京 / 上海", "Asia/Shanghai"),
    ("香港", "Asia/Hong_Kong"),
    ("台北", "Asia/Taipei"),
    ("东京", "Asia/Tokyo"),
    ("首尔", "Asia/Seoul"),
    ("新加坡", "Asia/Singapore"),
    ("伦敦", "Europe/London"),
    ("巴黎/柏林", "Europe/Paris"),
    ("纽约 (美东)", "America/New_York"),
    ("芝加哥 (美中)", "America/Chicago"),
    ("洛杉矶 (美西)", "America/Los_Angeles"),
    ("悉尼", "Australia/Sydney"),
    ("UTC", "UTC"),
]

# 内置时区 -> 城市短名称(用于状态栏前缀显示)
TZ_CITY_LABELS = {
    "Asia/Shanghai": "上海",
    "Asia/Hong_Kong": "香港",
    "Asia/Taipei": "台北",
    "Asia/Tokyo": "东京",
    "Asia/Seoul": "首尔",
    "Asia/Singapore": "新加坡",
    "Europe/London": "伦敦",
    "Europe/Paris": "巴黎",
    "America/New_York": "纽约",
    "America/Chicago": "芝加哥",
    "America/Los_Angeles": "洛杉矶",
    "Australia/Sydney": "悉尼",
    "UTC": "UTC",
}

# 文字颜色预设 (名称, 十六进制)
COLOR_PRESETS = [
    ("黑色", "#000000"),
    ("白色", "#FFFFFF"),
    ("蓝色", "#0A84FF"),
    ("绿色", "#30D158"),
    ("荧光绿", "#00FF88"),
    ("橙色", "#FF9F0A"),
    ("红色", "#FF453A"),
    ("紫色", "#BF5AF2"),
    ("黄色", "#FFD60A"),
    ("灰色", "#8E8E93"),
]

HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def normalize_hex(s):
    s = s.strip()
    if not s.startswith("#"):
        s = "#" + s
    return s.upper()


def hex_to_rgb01(hexcolor):
    hexcolor = hexcolor.lstrip("#")
    r = int(hexcolor[0:2], 16) / 255.0
    g = int(hexcolor[2:4], 16) / 255.0
    b = int(hexcolor[4:6], 16) / 255.0
    return r, g, b


def load_config():
    os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_config(cfg):
    os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# NTP 时间同步 (仅计算偏移量,不修改系统时钟)
# --------------------------------------------------------------------------

class NtpSync:
    """在后台线程里查询 NTP 服务器,计算与本地系统时钟的偏移量(秒)。"""

    def __init__(self):
        self.offset_seconds = 0.0
        self.last_sync_time = None      # 本地 time.time(),记录上次成功同步时刻
        self.last_sync_server = None
        self.last_error = None
        self.syncing = False
        self._lock = threading.Lock()

    def sync_async(self, server, callback=None):
        if self.syncing:
            return
        self.syncing = True

        def worker():
            err = None
            offset = None
            try:
                if not HAVE_NTPLIB:
                    raise RuntimeError("未安装 ntplib,请执行: pip3 install ntplib")
                client = ntplib.NTPClient()
                resp = client.request(server, version=3, timeout=5)
                offset = resp.offset
            except Exception as e:
                err = str(e)
            with self._lock:
                if offset is not None:
                    self.offset_seconds = offset
                    self.last_sync_time = time.time()
                    self.last_sync_server = server
                    self.last_error = None
                else:
                    self.last_error = err
                self.syncing = False
            if callback:
                callback(err)

        threading.Thread(target=worker, daemon=True).start()

    def current_time(self):
        """返回校正后的当前 UTC 时间 (datetime, aware)。"""
        with self._lock:
            offset = self.offset_seconds
        corrected = time.time() + offset
        return datetime.fromtimestamp(corrected, tz=dt_timezone.utc)


# --------------------------------------------------------------------------
# 主应用
# --------------------------------------------------------------------------

class StatusBarClockApp(rumps.App):

    def __init__(self):
        super().__init__("Clock", quit_button=None)
        self.cfg = load_config()
        self.ntp = NtpSync()

        self._build_menu()

        # 每秒刷新一次显示
        self.display_timer = rumps.Timer(self.on_tick, 1)
        self.display_timer.start()

        # 自动同步定时器(按分钟)
        self.sync_timer = None
        self._restart_auto_sync_timer()

        # 启动时先同步一次
        self.ntp.sync_async(self.cfg["ntp_server"], callback=self._after_sync)

        # 立即刷新一次显示,避免启动时空白
        self.on_tick(None)

    # ---------------------------------------------------------------- 菜单
    def _build_menu(self):
        # ------------------ 时区(折叠子菜单) ------------------
        tz_parent = rumps.MenuItem("时区")
        self.tz_items = {}
        for label, tzname in BUILTIN_TIMEZONES:
            item = rumps.MenuItem(
                f"{label} ({tzname})",
                callback=self._make_tz_callback(tzname),
            )
            item.state = (tzname == self.cfg["timezone"])
            self.tz_items[tzname] = item
            tz_parent.add(item)
        tz_parent.add(None)
        tz_parent.add(rumps.MenuItem("自定义时区…", callback=self.on_custom_timezone))

        # ------------------ 时间服务器 NTP(折叠子菜单) ------------------
        ntp_parent = rumps.MenuItem("时间服务器 (NTP)")
        self.ntp_items = {}
        for label, server in BUILTIN_NTP_SERVERS:
            item = rumps.MenuItem(
                f"{label} — {server}",
                callback=self._make_ntp_callback(server),
            )
            item.state = (server == self.cfg["ntp_server"])
            self.ntp_items[server] = item
            ntp_parent.add(item)
        ntp_parent.add(None)
        ntp_parent.add(rumps.MenuItem("自定义服务器…", callback=self.on_custom_ntp))
        ntp_parent.add(None)
        self.sync_status_item = rumps.MenuItem("尚未同步")
        self.sync_status_item.set_callback(None)  # 禁用点击,仅作展示
        ntp_parent.add(self.sync_status_item)
        ntp_parent.add(rumps.MenuItem("立即同步", callback=self.on_sync_now))

        # ------------------ 文字颜色(折叠子菜单) ------------------
        color_parent = rumps.MenuItem("文字颜色")
        self.fg_items = {}
        for label, hexcolor in COLOR_PRESETS:
            item = rumps.MenuItem(
                f"{label} {hexcolor}",
                callback=self._make_fg_callback(hexcolor),
            )
            item.state = (hexcolor.upper() == self.cfg["fg_color"].upper())
            self.fg_items[hexcolor.upper()] = item
            color_parent.add(item)
        color_parent.add(None)
        color_parent.add(rumps.MenuItem("自定义颜色(HEX)…", callback=self.on_custom_fg))

        # ------------------ 显示设置(折叠子菜单) ------------------
        display_parent = rumps.MenuItem("显示设置")
        self.show_seconds_item = rumps.MenuItem(
            "显示秒数", callback=self.on_toggle_seconds
        )
        self.show_seconds_item.state = self.cfg["show_seconds"]

        self.hour24_item = rumps.MenuItem(
            "24 小时制", callback=self.on_toggle_24h
        )
        self.hour24_item.state = self.cfg["hour_24"]

        self.show_date_item = rumps.MenuItem(
            "显示日期", callback=self.on_toggle_date
        )
        self.show_date_item.state = self.cfg["show_date"]

        display_parent.add(self.show_seconds_item)
        display_parent.add(self.hour24_item)
        display_parent.add(self.show_date_item)

        # ------------------ 开机自启动 ------------------
        self.autostart_item = rumps.MenuItem(
            "开机自启动", callback=self.on_toggle_autostart
        )
        self.autostart_item.state = is_autostart_enabled()

        self.menu = [
            tz_parent,
            ntp_parent,
            color_parent,
            display_parent,
            None,
            self.autostart_item,
            None,
            rumps.MenuItem("退出", callback=self.on_quit),
        ]

    # ------------------------------------------------------------- 回调工厂
    def _make_tz_callback(self, tzname):
        def _cb(sender):
            self._set_timezone(tzname)
        return _cb

    def _make_ntp_callback(self, server):
        def _cb(sender):
            self._set_ntp_server(server)
        return _cb

    def _make_fg_callback(self, hexcolor):
        def _cb(sender):
            self._set_fg_color(hexcolor)
        return _cb

    # ------------------------------------------------------------- 设置项
    def _set_timezone(self, tzname):
        try:
            if HAVE_ZONEINFO:
                ZoneInfo(tzname)  # 验证有效性
        except Exception:
            rumps.alert("无效的时区", f"找不到时区: {tzname}")
            return
        for name, item in self.tz_items.items():
            item.state = (name == tzname)
        self.cfg["timezone"] = tzname
        save_config(self.cfg)
        self.on_tick(None)

    def _set_ntp_server(self, server):
        for name, item in self.ntp_items.items():
            item.state = (name == server)
        self.cfg["ntp_server"] = server
        save_config(self.cfg)
        self.ntp.sync_async(server, callback=self._after_sync)

    def _set_fg_color(self, hexcolor):
        hexcolor = normalize_hex(hexcolor)
        for name, item in self.fg_items.items():
            item.state = (name == hexcolor)
        self.cfg["fg_color"] = hexcolor
        save_config(self.cfg)
        self.on_tick(None)

    def _restart_auto_sync_timer(self):
        if self.sync_timer is not None:
            self.sync_timer.stop()
            self.sync_timer = None
        minutes = self.cfg.get("auto_sync_minutes", 30)
        if minutes and minutes > 0:
            self.sync_timer = rumps.Timer(self.on_auto_sync, minutes * 60)
            self.sync_timer.start()

    # ------------------------------------------------------------- 菜单事件
    def on_custom_timezone(self, sender):
        hint = ""
        if HAVE_ZONEINFO:
            hint = "例如 Asia/Chongqing, America/Sao_Paulo"
        resp = rumps.Window(
            title="自定义时区",
            message=f"请输入 IANA 时区名称。{hint}",
            default_text=self.cfg["timezone"],
            ok="确定",
            cancel="取消",
        ).run()
        if resp.clicked and resp.text.strip():
            tzname = resp.text.strip()
            self._set_timezone(tzname)

    def on_custom_ntp(self, sender):
        resp = rumps.Window(
            title="自定义 NTP 服务器",
            message="请输入 NTP 服务器地址,例如 ntp.ntsc.ac.cn",
            default_text=self.cfg["ntp_server"],
            ok="确定",
            cancel="取消",
        ).run()
        if resp.clicked and resp.text.strip():
            server = resp.text.strip()
            self._set_ntp_server(server)

    def on_custom_fg(self, sender):
        resp = rumps.Window(
            title="自定义文字颜色",
            message="请输入十六进制颜色代码,例如 #00FF88",
            default_text=self.cfg["fg_color"],
            ok="确定",
            cancel="取消",
        ).run()
        if resp.clicked and resp.text.strip():
            text = resp.text.strip()
            if HEX_RE.match(text):
                self._set_fg_color(text)
            else:
                rumps.alert("格式错误", "请输入合法的十六进制颜色,例如 #00FF88")

    def on_toggle_seconds(self, sender):
        self.cfg["show_seconds"] = not self.cfg["show_seconds"]
        sender.state = self.cfg["show_seconds"]
        save_config(self.cfg)
        self.on_tick(None)

    def on_toggle_24h(self, sender):
        self.cfg["hour_24"] = not self.cfg["hour_24"]
        sender.state = self.cfg["hour_24"]
        save_config(self.cfg)
        self.on_tick(None)

    def on_toggle_date(self, sender):
        self.cfg["show_date"] = not self.cfg["show_date"]
        sender.state = self.cfg["show_date"]
        save_config(self.cfg)
        self.on_tick(None)

    def on_sync_now(self, sender):
        self.sync_status_item.title = "正在同步…"
        self.ntp.sync_async(self.cfg["ntp_server"], callback=self._after_sync)

    def on_auto_sync(self, sender):
        self.ntp.sync_async(self.cfg["ntp_server"], callback=self._after_sync)

    def _after_sync(self, err):
        if err:
            self.sync_status_item.title = f"同步失败: {err[:40]}"
        else:
            offset_ms = self.ntp.offset_seconds * 1000
            self.sync_status_item.title = (
                f"已同步 {self.ntp.last_sync_server} "
                f"(偏移 {offset_ms:+.1f} ms)"
            )

    def on_toggle_autostart(self, sender):
        if sender.state:
            ok, err = disable_autostart()
            if ok:
                sender.state = False
            else:
                rumps.alert("关闭开机自启动失败", err or "未知错误")
        else:
            ok, err = enable_autostart()
            if ok:
                sender.state = True
            else:
                rumps.alert("设置开机自启动失败", err or "未知错误")

    def on_quit(self, sender):
        rumps.quit_application()

    # ------------------------------------------------------------- 主循环
    def on_tick(self, sender):
        try:
            now_utc = self.ntp.current_time()
            tzname = self.cfg["timezone"]
            if HAVE_ZONEINFO:
                local_dt = now_utc.astimezone(ZoneInfo(tzname))
            else:
                local_dt = now_utc  # 兜底显示 UTC

            fmt = "%H:%M" if self.cfg["hour_24"] else "%I:%M"
            if self.cfg["show_seconds"]:
                fmt = fmt.replace("%M", "%M:%S")
            if not self.cfg["hour_24"]:
                fmt += " %p"
            time_str = local_dt.strftime(fmt)
            if self.cfg["show_date"]:
                time_str = local_dt.strftime("%m-%d ") + time_str

            # 时区城市前缀,例如 "上海 14:32"
            tz_prefix = self._tz_label(tzname)
            display_text = f"{tz_prefix} {time_str}"

            self._apply_title(display_text)
        except Exception:
            # 兜底: 出错时退回纯文字标题,保证状态栏始终可见
            self.title = datetime.now().strftime("%H:%M:%S")

    def _tz_label(self, tzname):
        """内置时区显示中文城市名,自定义时区退回 IANA 名称最后一段。"""
        if tzname in TZ_CITY_LABELS:
            return TZ_CITY_LABELS[tzname]
        return tzname.split("/")[-1].replace("_", " ")

    def _apply_title(self, text):
        """设置菜单栏标题文字,并尽可能应用自定义前景色。
        使用系统原生文字渲染(而非位图图标),宽度由 AppKit 自动计算,
        不会出现被压缩/裁切的问题。"""
        applied = False
        if HAVE_APPKIT:
            try:
                r, g, b = hex_to_rgb01(self.cfg["fg_color"])
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    r, g, b, 1.0
                )
                attr_str = NSMutableAttributedString.alloc().initWithString_(text)
                full_range = (0, attr_str.length())
                attr_str.addAttribute_value_range_(
                    NSForegroundColorAttributeName, color, full_range
                )
                try:
                    font = NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0)
                    attr_str.addAttribute_value_range_(
                        NSFontAttributeName, font, full_range
                    )
                except Exception:
                    pass  # 字体设置失败不影响颜色,继续走下面的 target 逻辑

                status_item = getattr(self._nsapp, "nsstatusitem", None)
                target = None
                if status_item is not None:
                    try:
                        target = status_item.button()
                    except Exception:
                        target = status_item
                if target is not None:
                    target.setAttributedTitle_(attr_str)
                    applied = True
            except Exception:
                applied = False

        if not applied:
            # 兜底:无法上色时,至少保证纯文字正常显示
            self.title = text


def main():
    missing = []
    if not HAVE_NTPLIB:
        missing.append("ntplib")
    if not HAVE_APPKIT:
        missing.append("pyobjc-framework-Cocoa")
    if missing:
        print(
            "缺少依赖,请先运行: pip3 install " + " ".join(missing)
        )

    app = StatusBarClockApp()
    app.run()


if __name__ == "__main__":
    main()
