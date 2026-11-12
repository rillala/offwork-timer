"""下班倒數計時器：系統匣圖示 + 浮動小條 + 下班前煙火提醒。"""
import ctypes
import json
import os
import queue
import sys
import tkinter as tk
from datetime import date, datetime, timedelta

import pystray
from PIL import Image, ImageDraw, ImageFont

import celebrate
from bar_styles import STYLES, UnsetStyle
from dialogs import SettingsDialog, StartTimeDialog
from theme import BG, BLUE, GRAY, GREEN, KEY, RED, SURFACE, YELLOW, resolve_fonts
from worktime import calc_off_time, fmt_delta, parse_hhmm

APP_NAME = "OffworkTimer"
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), APP_NAME)
STATE_PATH = os.path.join(DATA_DIR, "state.json")

DEFAULT_CONFIG = {
    "work_hours": 8,
    "lunch_start": "12:00",
    "lunch_end": "13:30",
    "remind_before_min": 10,    # 下班前提示畫面
    "warn_before_min": 30,      # 轉紅
    "caution_before_min": 60,   # 轉黃
    "idle_alpha": 0.7,          # 滑鼠不在浮動條上時的不透明度
    "bar_style": "row",         # row / capsule / card / ring
    "celebrate_style": "fireworks",  # fireworks / toast / banner
    "show_start": True,         # show_*：只對 row 樣式有效
    "show_end": True,
    "show_remain": True,
    "show_progress": True,
}

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return {**default, **json.load(f)}
    except (OSError, ValueError):
        return dict(default)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Win32 小工具 ----------
if sys.platform == "win32":
    from ctypes import wintypes

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    _user32 = ctypes.windll.user32
    _user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _user32.MonitorFromPoint.restype = wintypes.HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]


def monitor_rect(x, y, work=False):
    """回傳離 (x, y) 最近的螢幕範圍 (l, t, r, b)；work=True 時不含工作列。"""
    if sys.platform != "win32":
        return None
    hmon = _user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
    mi = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
    if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    r = mi.rcWork if work else mi.rcMonitor
    return r.left, r.top, r.right, r.bottom


def hwnd_of(win):
    return ctypes.windll.user32.GetParent(win.winfo_id())


def force_topmost(win):
    """重新把視窗推到最上層（點工作列後工作列會蓋過其他 topmost 視窗）。不搶焦點。"""
    if sys.platform != "win32":
        return
    HWND_TOPMOST = wintypes.HWND(-1)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
    _user32.SetWindowPos(hwnd_of(win), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


def redraw_now(win):
    """強制整個視窗立即重繪。半透明（layered）視窗同時移動＋改大小時，Windows 常沒重繪，
    會殘留舊畫面（例如大字膠囊 hover 展開／收合時）。"""
    if sys.platform != "win32":
        return
    RDW_INVALIDATE, RDW_ERASE, RDW_ALLCHILDREN, RDW_UPDATENOW, RDW_FRAME = 0x1, 0x4, 0x80, 0x100, 0x400
    ctypes.windll.user32.RedrawWindow(hwnd_of(win), None, None,
                                      RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME)


def round_corners(win, on=True):
    """Windows 11 圓角（on=False 取消，給圓環樣式用）；舊版 Windows 會靜默失敗。"""
    if sys.platform != "win32":
        return
    try:
        pref = ctypes.c_int(2 if on else 1)  # DWMWCP_ROUND / DWMWCP_DONOTROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd_of(win), 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


class App:
    def __init__(self):
        self.config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        save_json(CONFIG_PATH, self.config)          # 補上新版本的設定欄位
        self.state = load_json(STATE_PATH, {})
        self.q = queue.Queue()
        self.today = date.today()
        self.start = None
        self.source = ""
        self.celebration = None
        self._dialogs = {}
        self.style = None
        self._style_preview = None      # 設定頁點選中的浮動條樣式（尚未儲存）
        self._bar_size = None
        self._hover = False
        self._menu_open = False
        self._tray_key = None

        self._restore_today_start()
        self._build_bar()
        self._build_tray()
        if not self.start:
            self.root.after(500, self.ask_start)
        self.root.after(200, self._loop)
        self.root.after(300, self._keep_on_top)

    # ---------- state ----------
    def _today_str(self):
        return self.today.isoformat()

    def _restore_today_start(self):
        if self.state.get("date") == self._today_str() and self.state.get("start"):
            self.start = datetime.fromisoformat(self.state["start"])
            self.source = self.state.get("source", "")

    def _set_start(self, dt, source):
        self.start, self.source = dt, source
        self.state.update(date=self._today_str(), start=dt.isoformat(), source=source)
        save_json(STATE_PATH, self.state)
        self._refresh()

    @property
    def muted(self):
        return self.state.get("muted_date") == self._today_str()

    @property
    def celebrated(self):
        return self.state.get("celebrated_date") == self._today_str()

    @property
    def bar_hidden(self):
        return bool(self.state.get("bar_hidden"))

    def off_time(self):
        if not self.start:
            return None
        c = self.config
        return calc_off_time(self.start, c["work_hours"], parse_hhmm(c["lunch_start"]), parse_hhmm(c["lunch_end"]))

    def stage_color(self, left):
        mins = left.total_seconds() / 60
        if mins <= 0:
            return GREEN
        if mins <= self.config["warn_before_min"]:
            return RED
        if mins <= self.config["caution_before_min"]:
            return YELLOW
        return BLUE

    # ---------- floating bar ----------
    def _build_bar(self):
        root = self.root = tk.Tk()
        root.title(APP_NAME)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.config["idle_alpha"])
        root.configure(bg=BG)
        resolve_fonts(root)

        # 綁在 toplevel 上 → 所有子元件（含之後換樣式重建的）都會觸發
        root.bind("<ButtonPress-1>", self._drag_start)
        root.bind("<B1-Motion>", self._drag_move)
        root.bind("<ButtonRelease-1>", self._drag_end)
        root.bind("<Double-Button-1>", lambda _e: self.ask_start())
        root.bind("<Button-3>", self._bar_menu)
        root.bind("<Enter>", lambda _e: self._set_hover(True))
        root.bind("<Leave>", lambda _e: root.after(80, self._check_hover))

        root.update_idletasks()
        round_corners(root)
        if self.bar_hidden:
            root.withdraw()

    def _set_hover(self, on):
        if on != self._hover:
            self._hover = on
            self.root.attributes("-alpha", 1.0 if on else self.config["idle_alpha"])

    def _check_hover(self):
        px, py = self.root.winfo_pointerxy()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        self._set_hover(x <= px < x + self.root.winfo_width() and y <= py < y + self.root.winfo_height())

    def _anchor_from_rect(self, x, y, w, h):
        """浮動條靠螢幕右半邊 → 以右下角為錨點（文字變長時往左長），否則以左下角為錨點。"""
        mon = monitor_rect(x + w // 2, y + h // 2)
        right = mon is not None and x + w / 2 > (mon[0] + mon[2]) / 2
        return {"x": x + w if right else x, "y": y + h, "side": "right" if right else "left"}

    def _place_bar(self):
        root = self.root
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        a = self.state.get("bar_anchor")
        if not a:
            old = self.state.pop("bar_pos", None)       # 舊版存的是左上角
            if old:
                a = self._anchor_from_rect(old[0], old[1], w, h)
            else:
                wa = monitor_rect(0, 0, work=True) or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
                a = {"x": wa[2] - 12, "y": wa[3] - 8, "side": "right"}
            self.state["bar_anchor"] = a
            save_json(STATE_PATH, self.state)
        x = a["x"] - w if a["side"] == "right" else a["x"]
        y = a["y"] - h
        mon = monitor_rect(x + w // 2, y + h // 2)      # 螢幕拔掉或解析度改變時拉回畫面內
        if mon:
            x = min(max(x, mon[0]), mon[2] - w)
            y = min(max(y, mon[1]), mon[3] - h)
        root.geometry(f"+{x}+{y}")
        self._bar_size = (w, h)
        root.update_idletasks()
        redraw_now(root)

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _drag_end(self, _e):
        r = self.root
        self.state["bar_anchor"] = self._anchor_from_rect(r.winfo_x(), r.winfo_y(), r.winfo_width(), r.winfo_height())
        save_json(STATE_PATH, self.state)

    def _keep_on_top(self):
        if not self.bar_hidden and not self._menu_open:
            force_topmost(self.root)
        self.root.after(300, self._keep_on_top)

    def _apply_bar_style(self, cls):
        """換浮動條樣式：銷毀舊內容、切換透明／圓角模式、建立新內容。"""
        if self.style:
            self.style.destroy()
        root = self.root
        if cls.transparent:
            root.configure(bg=KEY)
            root.attributes("-transparentcolor", KEY)
        else:
            root.attributes("-transparentcolor", "")
            root.configure(bg=BG)
        root.update_idletasks()
        round_corners(root, not cls.transparent)
        self.style = cls(root, self.config)

    def _render_bar(self, view):
        """view：見 bar_styles 模組說明；未設定上班時間時為 None。"""
        key = self._style_preview or self.config["bar_style"]
        cls = UnsetStyle if view is None else STYLES.get(key, STYLES["row"])
        if type(self.style) is not cls:
            self._apply_bar_style(cls)
        if view is not None:
            self.style.update(view)
        self.root.update_idletasks()
        if (self.root.winfo_reqwidth(), self.root.winfo_reqheight()) != self._bar_size:
            self._place_bar()

    def toggle_bar(self):
        if self.bar_hidden:
            self.state["bar_hidden"] = False
            self.root.deiconify()
            force_topmost(self.root)
        else:
            self.state["bar_hidden"] = True
            self.root.withdraw()
        save_json(STATE_PATH, self.state)
        self.tray.update_menu()

    # ---------- menus（浮動條右鍵與系統匣共用） ----------
    def _menu_items(self):
        return [
            ("今天暫停特效", "mute", lambda: self.muted),
            ("設定上班時間…", "ask_start", None),
            ("設定…", "settings", None),
            ("測試特效", "celebrate", None),
            None,
            (lambda: "顯示浮動條" if self.bar_hidden else "隱藏浮動條", "toggle_bar", None),
            ("開機自動啟動", "autostart", self.autostart_enabled),
            ("結束", "quit", None),
        ]

    def _do(self, action):
        {"mute": self.toggle_mute, "ask_start": self.ask_start, "settings": self.open_settings,
         "celebrate": self.celebrate, "toggle_bar": self.toggle_bar,
         "autostart": self.toggle_autostart, "quit": self.quit}[action]()

    def _bar_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        for item in self._menu_items():
            if item is None:
                m.add_separator(); continue
            label, action, checked = item
            label = label() if callable(label) else label
            if checked:
                m.add_checkbutton(label=label, command=lambda a=action: self._do(a),
                                  variable=tk.BooleanVar(m, value=checked()))
            else:
                m.add_command(label=label, command=lambda a=action: self._do(a))
        self._menu_open = True                       # 選單開著時別把浮動條推到選單上面
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
            self._menu_open = False

    def _build_tray(self):
        items = []
        for item in self._menu_items():
            if item is None:
                items.append(pystray.Menu.SEPARATOR); continue
            label, action, checked = item
            text = (lambda _i, f=label: f()) if callable(label) else label
            items.append(pystray.MenuItem(
                text, lambda *_a, a=action: self.q.put(a),
                checked=(lambda _i, f=checked: f()) if checked else None,
                default=(action == "toggle_bar")))
        self.tray = pystray.Icon(APP_NAME, self._tray_image("--", GRAY, None), APP_NAME, pystray.Menu(*items))
        self.tray.run_detached()

    @staticmethod
    def _tray_image(text, color, ratio):
        """64px 圖示：外圈為當日進度環，中間是精簡文字（3h / 42m / OK）。"""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, 63, 63), radius=12, fill=BG)
        if ratio is not None:
            box = (4, 4, 59, 59)
            d.ellipse(box, outline=SURFACE, width=7)
            if ratio > 0:
                d.arc(box, -90, -90 + 360 * min(ratio, 1), fill=color, width=7)
        max_w = 40 if ratio is not None else 60
        size = 34
        while True:
            font = App._tray_font(size)
            if font is None:
                font = ImageFont.load_default(); break
            bbox = d.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_w or size <= 10:
                break
            size -= 1
        bbox = d.textbbox((0, 0), text, font=font)
        d.text(((64 - (bbox[2] - bbox[0])) / 2 - bbox[0], (64 - (bbox[3] - bbox[1])) / 2 - bbox[1]),
               text, font=font, fill=color)
        return img

    @staticmethod
    def _tray_font(size):
        """匣圖示字型：Segoe UI Variable Bold（Win11）→ Segoe UI Bold → Arial Bold。"""
        try:
            f = ImageFont.truetype("SegUIVar.ttf", size)
            f.set_variation_by_name("Bold")
            return f
        except (OSError, ValueError, AttributeError):
            pass
        for name in ("segoeuib.ttf", "arialbd.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return None

    @staticmethod
    def _compact(left):
        mins = -(-int(left.total_seconds()) // 60)
        return f"{mins // 60}h" if mins >= 60 else f"{mins}m"

    # ---------- autostart（HKCU Run） ----------
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _launch_cmd(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        return f'"{pyw}" "{os.path.abspath(__file__)}"'

    def autostart_enabled(self):
        if sys.platform != "win32":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            return False

    def toggle_autostart(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if self.autostart_enabled():
                winreg.DeleteValue(k, APP_NAME)
            else:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, self._launch_cmd())
        self.tray.update_menu()

    # ---------- actions ----------
    def toggle_mute(self):
        if self.muted:
            self.state.pop("muted_date", None)
        else:
            self.state["muted_date"] = self._today_str()
            if self.celebration:
                self.celebration.close()
        save_json(STATE_PATH, self.state)
        self.tray.update_menu()

    def _open_dialog(self, name, factory):
        dlg = self._dialogs.get(name)
        if dlg is not None and dlg.winfo_exists():
            dlg.deiconify(); dlg.lift(); dlg.focus_force()
            return
        self._dialogs[name] = factory()

    def ask_start(self):
        default = self.start.strftime("%H:%M") if self.start else "08:30"
        self._open_dialog("start", lambda: StartTimeDialog(
            self.root, self.config, default,
            on_ok=lambda t: self._set_start(datetime.combine(self.today, t), "手動")))

    def open_settings(self):
        self._open_dialog("settings", lambda: SettingsDialog(
            self.root, self.config, on_ok=self._apply_settings,
            on_preview=lambda style, minutes: self.celebrate(style, minutes, replay=True),
            on_bar_preview=self._preview_bar_style,
            on_close=lambda: self._preview_bar_style(None)))

    def _preview_bar_style(self, style):
        """設定頁點選浮動條樣式時即時預覽；style=None 還原成已儲存的樣式。"""
        if style == self._style_preview:
            return
        self._style_preview = style
        try:
            if self.style:
                self.style.destroy()
                self.style = None
            self._refresh()
        except tk.TclError:          # 程式結束時設定頁跟著被銷毀，浮動條已不存在
            pass

    def _apply_settings(self, new):
        self.config = new
        save_json(CONFIG_PATH, new)
        self.root.attributes("-alpha", 1.0 if self._hover else new["idle_alpha"])
        if self.style:                       # 樣式或顯示項目可能變了 → 重建
            self.style.destroy()
            self.style = None
        self._refresh()

    def celebrate(self, style=None, minutes=None, replay=False):
        """播放下班前提示。replay=True（設定頁預覽）會中斷正在播的那個重新播。"""
        if self.celebration and self.celebration.alive:
            if not replay:
                return
            self.celebration.close()
        r = self.root
        if self.bar_hidden:
            bar_rect, cx, cy = None, 0, 0
        else:
            x, y, w, h = r.winfo_x(), r.winfo_y(), r.winfo_width(), r.winfo_height()
            bar_rect, cx, cy = (x, y, x + w, y + h), x + w // 2, y + h // 2
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        mon = monitor_rect(cx, cy) or (0, 0, sw, sh)
        work = monitor_rect(cx, cy, work=True) or mon
        end = self.off_time()
        self.celebration = celebrate.play(
            r, style or self.config["celebrate_style"],
            self.config["remind_before_min"] if minutes is None else minutes,
            f"{end:%H:%M}" if end else "--:--", mon, work, bar_rect)

    def quit(self):
        self.tray.stop()
        self.root.destroy()

    # ---------- main loop ----------
    def _handle_queue(self):
        while True:
            try:
                action = self.q.get_nowait()
            except queue.Empty:
                return
            self._do(action)
            if action == "quit":
                return

    def _refresh(self):
        now = datetime.now()
        end = self.off_time()
        if end is None:
            view = None
            tray_txt, color, ratio, tip = "--", GRAY, None, f"{APP_NAME}\n尚未設定上班時間"
        else:
            left = end - now
            color = self.stage_color(left)
            span = (end - self.start).total_seconds()
            ratio = min(max((now - self.start).total_seconds() / span, 0), 1) if span > 0 else 1
            remain = fmt_delta(left)
            if left.total_seconds() > 0:
                tray_txt = self._compact(left)
                tip = f"下班 {end:%H:%M}（剩 {remain}）\n上班 {self.start:%H:%M}"
                remind_at = end - timedelta(minutes=self.config["remind_before_min"])
                if now >= remind_at and not self.celebrated and not self.muted:
                    self.state["celebrated_date"] = self._today_str()
                    save_json(STATE_PATH, self.state)
                    self.celebrate()
            else:
                tray_txt = "OK"
                tip = f"已過下班時間 {end:%H:%M}（+{remain}）"
            if self.muted:
                tip += "\n（今日特效已暫停）"
            day = self.start.date()
            ls = datetime.combine(day, parse_hhmm(self.config["lunch_start"]))
            le = datetime.combine(day, parse_hhmm(self.config["lunch_end"]))
            pos = (lambda t: min(max((t - self.start).total_seconds() / span, 0), 1)) if span > 0 else (lambda t: 0)
            view = {"start": f"{self.start:%H:%M}", "end": f"{end:%H:%M}", "remain": remain,
                    "over": left.total_seconds() <= 0, "color": color, "ratio": ratio,
                    "lunch": (pos(ls), pos(le)), "in_lunch": ls <= now < le}

        self._render_bar(view)
        key = (tray_txt, color, None if ratio is None else round(ratio * 50))
        if key != self._tray_key:
            self._tray_key = key
            self.tray.icon = self._tray_image(tray_txt, color, ratio)
        self.tray.title = tip[:127]

    def _loop(self):
        self._handle_queue()
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if date.today() != self.today:           # 換日 → 重置
            self.today = date.today()
            self.start, self.source = None, ""
            self.root.after(500, self.ask_start)
        self._refresh()
        self.root.after(1000, self._loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
