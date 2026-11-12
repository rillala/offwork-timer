"""下班倒數計時器：系統匣圖示 + 工作列上方浮動小條 + 下班前煙火提醒。"""
import ctypes
import json
import os
import queue
import sys
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, simpledialog

import pystray
from PIL import Image, ImageDraw, ImageFont

from celebrate import Celebration
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
    "remind_before_min": 10,   # 煙火特效
    "warn_before_min": 30,     # 文字變紅
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


def work_area():
    """回傳桌面可用區域 (left, top, right, bottom)，不含工作列。"""
    if sys.platform == "win32":
        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
        r = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
        return r.l, r.t, r.r, r.b
    return None


class App:
    def __init__(self):
        self.config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        if not os.path.exists(CONFIG_PATH):
            save_json(CONFIG_PATH, self.config)
        self.state = load_json(STATE_PATH, {})
        self.q = queue.Queue()
        self.today = date.today()
        self.start = None
        self.source = ""
        self.celebration = None

        self._restore_today_start()
        self._build_bar()
        self._build_tray()
        if not self.start:
            self.root.after(500, self.ask_start)
        self.root.after(200, self._loop)

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

    @property
    def muted(self):
        return self.state.get("muted_date") == self._today_str()

    @property
    def celebrated(self):
        return self.state.get("celebrated_date") == self._today_str()

    def off_time(self):
        if not self.start:
            return None
        c = self.config
        return calc_off_time(self.start, c["work_hours"], parse_hhmm(c["lunch_start"]), parse_hhmm(c["lunch_end"]))

    # ---------- floating bar ----------
    def _build_bar(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.88)
        self.root.configure(bg="#1e1e2e")
        self.label = tk.Label(self.root, text="…", fg="#cdd6f4", bg="#1e1e2e",
                              font=("Microsoft JhengHei UI", 11, "bold"), padx=10, pady=3)
        self.label.pack()
        for w in (self.root, self.label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Button-3>", self._bar_menu)
        self.root.update_idletasks()
        pos = self.state.get("bar_pos")
        if pos:
            self.root.geometry(f"+{pos[0]}+{pos[1]}")
        else:
            wa = work_area()
            if wa:
                self.root.geometry(f"+{wa[2] - 260}+{wa[3] - 36}")
            else:
                self.root.geometry("+100+100")
        if self.state.get("bar_hidden"):
            self.root.withdraw()

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _drag_end(self, _e):
        self.state["bar_pos"] = [self.root.winfo_x(), self.root.winfo_y()]
        save_json(STATE_PATH, self.state)

    def _bar_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        self._mute_var = tk.BooleanVar(value=self.muted)
        m.add_checkbutton(label="今天暫停特效", command=self.toggle_mute, variable=self._mute_var)
        m.add_command(label="設定上班時間…", command=self.ask_start)
        m.add_command(label="測試特效", command=self.celebrate)
        m.add_separator()
        m.add_command(label="隱藏浮動條", command=self.toggle_bar)
        m.add_command(label="結束", command=self.quit)
        m.tk_popup(e.x_root, e.y_root)

    def toggle_bar(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify(); self.root.attributes("-topmost", True)
            self.state["bar_hidden"] = False
        else:
            self.root.withdraw()
            self.state["bar_hidden"] = True
        save_json(STATE_PATH, self.state)

    # ---------- tray ----------
    def _build_tray(self):
        def post(action):
            return lambda *_: self.q.put((action, None, None))
        menu = pystray.Menu(
            pystray.MenuItem("今天暫停特效", post("mute"), checked=lambda _: self.muted),
            pystray.MenuItem("設定上班時間…", post("ask_start")),
            pystray.MenuItem("測試特效", post("celebrate")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("顯示/隱藏浮動條", post("toggle_bar"), default=True),
            pystray.MenuItem("開機自動啟動", post("autostart"), checked=lambda _: self.autostart_enabled()),
            pystray.MenuItem("結束", post("quit")),
        )
        self.tray = pystray.Icon(APP_NAME, self._tray_image("--"), APP_NAME, menu)
        self._tray_text = None
        self.tray.run_detached()

    @staticmethod
    def _tray_image(text, color="#4cc9f0"):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, 63, 63), radius=12, fill="#1e1e2e")
        size = 40                               # 縮到 "00:00" 剛好塞進 64px 寬
        while True:
            try:
                font = ImageFont.truetype("arialbd.ttf", size)
            except OSError:
                font = ImageFont.load_default(); break
            bbox = d.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= 62 or size <= 10:
                break
            size -= 1
        bbox = d.textbbox((0, 0), text, font=font)
        d.text(((64 - (bbox[2] - bbox[0])) / 2 - bbox[0], (64 - (bbox[3] - bbox[1])) / 2 - bbox[1]),
               text, font=font, fill=color)
        return img

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

    def ask_start(self):
        default = self.start.strftime("%H:%M") if self.start else "08:30"
        s = simpledialog.askstring(APP_NAME, "今天上班刷卡時間 (HH:MM)：", initialvalue=default, parent=self.root)
        if not s:
            return
        try:
            t = parse_hhmm(s)
        except ValueError:
            messagebox.showerror(APP_NAME, "格式錯誤，請輸入像 08:42 這樣的時間"); return
        self._set_start(datetime.combine(self.today, t), "手動")

    def celebrate(self):
        if self.celebration and self.celebration.alive:
            return
        mins = self.config["remind_before_min"]
        self.celebration = Celebration(self.root, f"再 {mins} 分鐘下班！")

    def quit(self):
        self.tray.stop()
        self.root.destroy()

    # ---------- main loop ----------
    def _handle_queue(self):
        while True:
            try:
                action, dt, err = self.q.get_nowait()
            except queue.Empty:
                return
            if action == "mute": self.toggle_mute()
            elif action == "ask_start": self.ask_start()
            elif action == "celebrate": self.celebrate()
            elif action == "toggle_bar": self.toggle_bar()
            elif action == "autostart": self.toggle_autostart()
            elif action == "quit": self.quit(); return

    def _loop(self):
        self._handle_queue()
        if not self.root.winfo_exists():
            return
        now = datetime.now()

        if now.date() != self.today:           # 換日 → 重置
            self.today = now.date()
            self.start, self.source = None, ""
            self.root.after(500, self.ask_start)

        end = self.off_time()
        if end is None:
            bar = "尚未設定上班時間（右鍵設定）"
            tray_txt, tip, color = "--:--", f"{APP_NAME}\n尚未設定上班時間", "#888888"
        else:
            left = end - now
            if left.total_seconds() > 0:
                remain = fmt_delta(left)
                bar = f"上班 {self.start:%H:%M} ｜ 下班 {end:%H:%M} ｜ 剩 {remain}"
                tray_txt = remain
                warn = left <= timedelta(minutes=self.config["warn_before_min"])
                color = "#ff4d6d" if warn else "#4cc9f0"
                tip = f"下班 {end:%H:%M}（剩 {remain}）\n上班 {self.start:%H:%M}"
                remind_at = end - timedelta(minutes=self.config["remind_before_min"])
                if now >= remind_at and not self.celebrated and not self.muted:
                    self.state["celebrated_date"] = self._today_str()
                    save_json(STATE_PATH, self.state)
                    self.celebrate()
            else:
                bar = f"可以下班了！已超過 {fmt_delta(left)}"
                tray_txt, color = fmt_delta(left), "#06d6a0"
                tip = f"已過下班時間 {end:%H:%M}"
            if self.muted:
                tip += "\n（今日特效已暫停）"

        self.label.config(text=bar, fg=color if end else "#cdd6f4")
        if (tray_txt, color) != self._tray_text:
            self._tray_text = (tray_txt, color)
            self.tray.icon = self._tray_image(tray_txt, color)
        self.tray.title = tip[:127]
        self.root.after(1000, self._loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
