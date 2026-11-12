"""深色主題的「設定上班時間」對話框與「設定」視窗（純 tk 元件）。"""
import ctypes
import sys
import tkinter as tk
from datetime import date, datetime

from theme import BG, BLUE, GREEN, HOVER, RED, SUBTEXT, SURFACE, TEXT, num, zh
from worktime import calc_off_time, parse_hhmm

BAR_STYLES = [("row", "橫向資訊列"), ("capsule", "大字膠囊"), ("card", "雙行卡片"), ("ring", "圓環")]
CELEBRATE_STYLES = [("fireworks", "煙火＋光暈"), ("toast", "右下角通知卡"), ("banner", "頂部橫幅")]


class _Dialog(tk.Toplevel):
    def __init__(self, root, title):
        super().__init__(root)
        self.withdraw()
        self.title(title)
        self.configure(bg=BG, padx=18, pady=14)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.submit())

    def show(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}+{(self.winfo_screenheight() - h) // 3}")
        if sys.platform == "win32":                     # 深色標題列（Win10 20H1+ / Win11）
            try:
                on = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.windll.user32.GetParent(self.winfo_id()), 20, ctypes.byref(on), ctypes.sizeof(on))
            except Exception:
                pass
        self.deiconify()
        self.lift()
        self.focus_force()

    # ---------- 元件工廠 ----------
    @staticmethod
    def label(parent, text="", fg=TEXT, size=10, bold=False):
        return tk.Label(parent, text=text, fg=fg, bg=BG, font=zh(size, bold))

    @staticmethod
    def entry(parent, value, width=7, size=11):
        """輸入框內容都是數字或時間 → 用數字字型。"""
        e = tk.Entry(parent, width=width, bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=num(size), justify="center", highlightthickness=1,
                     highlightbackground=SURFACE, highlightcolor=BLUE)
        e.insert(0, str(value))
        return e

    @staticmethod
    def button(parent, text, cmd, primary=False):
        return tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, cursor="hand2",
                         font=zh(10, primary), padx=14, pady=3,
                         bg=BLUE if primary else SURFACE, fg=BG if primary else TEXT,
                         activebackground="#90e0ef" if primary else HOVER,
                         activeforeground=BG if primary else TEXT)

    @staticmethod
    def check(parent, text, value):
        var = tk.BooleanVar(value=value)
        cb = tk.Checkbutton(parent, text=text, variable=var, fg=TEXT, bg=BG, selectcolor=SURFACE,
                            activebackground=BG, activeforeground=TEXT, disabledforeground=HOVER,
                            font=zh(10), bd=0, highlightthickness=0, cursor="hand2")
        return cb, var

    @staticmethod
    def radios(parent, choices, value):
        var = tk.StringVar(value=value)
        for key, text in choices:
            tk.Radiobutton(parent, text=text, value=key, variable=var, fg=TEXT, bg=BG, selectcolor=SURFACE,
                           activebackground=BG, activeforeground=TEXT, font=zh(10), bd=0,
                           highlightthickness=0, cursor="hand2").pack(side="left", padx=(0, 10))
        return var

    def section(self, text):
        self.label(self, text, bold=True).pack(anchor="w", pady=(12, 4))
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x")
        return row

    def buttons(self, ok_text="確定"):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(14, 0))
        self.button(row, ok_text, self.submit, primary=True).pack(side="right")
        self.button(row, "取消", self.destroy).pack(side="right", padx=(0, 8))

    def submit(self):
        raise NotImplementedError


class StartTimeDialog(_Dialog):
    """輸入上班時間，並即時預覽下班時間。"""

    def __init__(self, root, cfg, initial, on_ok):
        super().__init__(root, "設定上班時間")
        self.cfg, self.on_ok = cfg, on_ok
        self.label(self, "今天上班刷卡時間").pack(anchor="w")
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        self.ent = self.entry(row, initial, width=6, size=18)
        self.ent.pack(side="left", ipady=2)
        self.button(row, "現在", self.fill_now).pack(side="left", padx=(10, 0), fill="y")
        self.preview = tk.Frame(self, bg=BG)
        self.preview.pack(anchor="w", pady=(10, 0))
        self.pv_zh = self.label(self.preview, size=11, bold=True)
        self.pv_num = tk.Label(self.preview, bg=BG, font=num(12, True))
        self.pv_zh.pack(side="left")
        self.pv_num.pack(side="left")
        self.label(self, "可輸入 08:42 或 0842", fg=SUBTEXT, size=9).pack(anchor="w")
        self.buttons()
        self.ent.bind("<KeyRelease>", lambda _e: self.update_preview())
        self.update_preview()
        self.show()
        self.ent.focus_set()
        self.ent.select_range(0, "end")

    def _parse(self):
        t = parse_hhmm(self.ent.get())
        c = self.cfg
        end = calc_off_time(datetime.combine(date.today(), t), c["work_hours"],
                            parse_hhmm(c["lunch_start"]), parse_hhmm(c["lunch_end"]))
        return t, end

    def update_preview(self):
        try:
            _t, end = self._parse()
        except ValueError:
            self.pv_zh.config(text="格式不正確", fg=RED if self.ent.get().strip() else SUBTEXT)
            self.pv_num.config(text="")
            return
        self.pv_zh.config(text="→ 下班 ", fg=GREEN)
        self.pv_num.config(text=f"{end:%H:%M}", fg=GREEN)

    def fill_now(self):
        self.ent.delete(0, "end")
        self.ent.insert(0, datetime.now().strftime("%H:%M"))
        self.update_preview()
        self.ent.focus_set()

    def submit(self):
        try:
            t, _end = self._parse()
        except ValueError:
            self.bell()
            self.update_preview()
            return
        self.destroy()
        self.on_ok(t)


class SettingsDialog(_Dialog):
    """工時、午休、提醒門檻、浮動條樣式與顯示項目、提示畫面樣式。"""

    FIELDS = [  # (key, 標籤, 單位)
        ("work_hours", "每日工時", "小時"),
        ("lunch_start", "午休開始", ""),
        ("lunch_end", "午休結束", ""),
        ("caution_before_min", "下班前轉黃", "分鐘"),
        ("warn_before_min", "下班前轉紅", "分鐘"),
        ("remind_before_min", "下班前提示", "分鐘"),
        ("idle_alpha", "閒置時不透明度", "%"),
    ]
    SHOW = [("show_start", "上班時間"), ("show_end", "下班時間"),
            ("show_remain", "剩餘時間"), ("show_progress", "進度條")]

    def __init__(self, root, cfg, on_ok, on_preview=None, on_bar_preview=None, on_close=None):
        """on_preview(style, minutes)：播放提示畫面預覽。
        on_bar_preview(style)：浮動條暫時換成該樣式（點選即預覽）。
        on_close()：視窗關閉時（儲存或取消）呼叫，用來還原預覽。"""
        super().__init__(root, "設定")
        self.cfg, self.on_ok, self.on_preview = cfg, on_ok, on_preview
        self.on_bar_preview, self.on_close = on_bar_preview, on_close
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="x")
        self.entries = {}
        for r, (key, text, unit) in enumerate(self.FIELDS):
            val = cfg[key]
            if key == "idle_alpha":
                val = round(val * 100)
            elif key == "work_hours" and float(val).is_integer():
                val = int(val)
            self.label(grid, text).grid(row=r, column=0, sticky="w", pady=3)
            e = self.entry(grid, val)
            e.grid(row=r, column=1, padx=8, pady=3)
            self.label(grid, unit, fg=SUBTEXT).grid(row=r, column=2, sticky="w")
            self.entries[key] = e

        self.bar_style = self.radios(self.section("浮動條樣式"), BAR_STYLES, cfg["bar_style"])

        row = self.section("浮動條顯示（僅「橫向資訊列」）")
        self.show_vars, self.show_cbs = {}, []
        for key, text in self.SHOW:
            cb, var = self.check(row, text, cfg[key])
            cb.pack(side="left", padx=(0, 10))
            self.show_vars[key] = var
            self.show_cbs.append(cb)
        self.bar_style.trace_add("write", lambda *_a: self._on_bar_style())
        self._sync_show_state()

        self.celebrate_style = self.radios(self.section("下班前提示畫面"), CELEBRATE_STYLES, cfg["celebrate_style"])
        if on_preview:
            self.button(self, "▶ 預覽提示畫面", self.preview).pack(anchor="w", pady=(8, 0))

        self.err = self.label(self, fg=RED, size=9)
        self.err.pack(anchor="w", pady=(8, 0))
        self.buttons("儲存")
        self.show()

    def _sync_show_state(self):
        state = "normal" if self.bar_style.get() == "row" else "disabled"
        for cb in self.show_cbs:
            cb.config(state=state)

    def _on_bar_style(self):
        self._sync_show_state()
        if self.on_bar_preview:
            self.on_bar_preview(self.bar_style.get())

    def destroy(self):
        cb, self.on_close = self.on_close, None          # 只呼叫一次
        if cb:
            cb()
        super().destroy()

    def preview(self):
        try:
            minutes = int(self.entries["remind_before_min"].get())
        except ValueError:
            minutes = self.cfg["remind_before_min"]
        self.on_preview(self.celebrate_style.get(), minutes)

    def _collect(self):
        g = {k: e.get().strip() for k, e in self.entries.items()}
        new = dict(self.cfg)
        try:
            new["work_hours"] = float(g["work_hours"])
        except ValueError:
            raise ValueError("每日工時請輸入數字")
        if not 0 < new["work_hours"] <= 24:
            raise ValueError("每日工時需介於 0～24 小時")
        try:
            ls, le = parse_hhmm(g["lunch_start"]), parse_hhmm(g["lunch_end"])
        except ValueError:
            raise ValueError("午休時間格式請用 HH:MM")
        if le <= ls:
            raise ValueError("午休結束需晚於午休開始")
        new["lunch_start"], new["lunch_end"] = ls.strftime("%H:%M"), le.strftime("%H:%M")
        for key in ("caution_before_min", "warn_before_min", "remind_before_min"):
            try:
                new[key] = int(g[key])
            except ValueError:
                raise ValueError("分鐘數請輸入整數")
            if new[key] < 0:
                raise ValueError("分鐘數不可為負")
        try:
            alpha = int(g["idle_alpha"])
        except ValueError:
            raise ValueError("不透明度請輸入 20～100 的整數")
        if not 20 <= alpha <= 100:
            raise ValueError("不透明度請輸入 20～100 的整數")
        new["idle_alpha"] = alpha / 100
        new["bar_style"] = self.bar_style.get()
        new["celebrate_style"] = self.celebrate_style.get()
        for key, var in self.show_vars.items():
            new[key] = var.get()
        if new["bar_style"] == "row" and not (new["show_start"] or new["show_end"] or new["show_remain"]):
            raise ValueError("上班／下班／剩餘時間至少要勾選一項")
        return new

    def submit(self):
        try:
            new = self._collect()
        except ValueError as e:
            self.err.config(text=str(e))
            self.bell()
            return
        self.destroy()
        self.on_ok(new)
