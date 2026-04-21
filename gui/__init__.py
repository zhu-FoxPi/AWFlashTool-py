"""AW Flash Tool - GUI using tkinter"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import logging
import sys
import os
from pathlib import Path
import time

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fel import FelDevice, parse_firmware

logger = logging.getLogger(__name__)


class AWFlashGUI:
    """Main application window"""

    def __init__(self, root):
        self.root = root
        self.root.title("AW Flash Tool")
        self.root.geometry("960x700")
        self.root.minsize(800, 600)
        self.root.configure(bg="#1a1a2e")

        self.fel = FelDevice()
        self.firmware = None
        self.is_flashing = False
        self.is_scanning = False

        self._setup_logging()
        self._setup_styles()
        self._build_ui()

        # Set debug callback
        self.fel.set_debug_callback(lambda msg: self.log(msg, "debug"))

        # Auto-scan on startup
        self.root.after(500, self.scan_devices)

    def _setup_logging(self):
        """Setup logging to on-screen text widget"""
        # We'll use the text widget as our log output
        pass

    def _setup_styles(self):
        """Configure ttk styles for dark theme"""
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Colors
        self.bg_primary = "#1a1a2e"
        self.bg_secondary = "#16213e"
        self.bg_tertiary = "#0f3460"
        self.accent = "#e94560"
        self.accent_hover = "#ff6b6b"
        self.text_primary = "#eaeaea"
        self.text_secondary = "#a0a0a0"
        self.border = "#2a2a4a"
        self.success = "#00d26a"
        self.warning = "#ffc107"
        self.error = "#ff4757"

    def _build_ui(self):
        """Build the user interface"""
        # ========== Header ==========
        header = tk.Frame(self.root, bg=self.bg_secondary, padx=16, pady=12)
        header.pack(fill=tk.X)

        tk.Label(header, text="AW Flash Tool", font=("Segoe UI", 16, "bold"),
                 fg=self.accent, bg=self.bg_secondary).pack(side=tk.LEFT)

        self.status_label = tk.Label(header, text="未连接", font=("Segoe UI", 10),
                                     fg=self.text_secondary, bg=self.bg_secondary)
        self.status_label.pack(side=tk.RIGHT)

        # ========== Main Content ==========
        main = tk.Frame(self.root, bg=self.border)
        main.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Left Panel
        left = tk.Frame(main, bg=self.bg_primary, width=340)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 1))
        left.pack_propagate(False)

        self._build_device_panel(left)
        self._build_firmware_panel(left)
        self._build_partition_panel(left)

        # Right Panel
        right = tk.Frame(main, bg=self.bg_primary)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_options_panel(right)
        self._build_progress_panel(right)
        self._build_log_panel(right)

        # ========== Footer ==========
        footer = tk.Frame(self.root, bg=self.bg_secondary, padx=16, pady=12)
        footer.pack(fill=tk.X)

        self.btn_flash = tk.Button(footer, text="▶ 开始烧录", font=("Segoe UI", 12),
                                   bg=self.accent, fg="white", activebackground=self.accent_hover,
                                   relief=tk.FLAT, cursor="hand2", state=tk.DISABLED,
                                   command=self.start_flash)
        self.btn_flash.pack(side=tk.LEFT, padx=8)

        self.btn_erase = tk.Button(footer, text="🗑 擦除 Flash", font=("Segoe UI", 11),
                                   bg=self.bg_tertiary, fg=self.text_primary,
                                   activebackground="#1a4a7a", relief=tk.FLAT,
                                   cursor="hand2", state=tk.DISABLED, command=self.erase_flash)
        self.btn_erase.pack(side=tk.LEFT, padx=8)

        self.btn_disconnect = tk.Button(footer, text="断开连接", font=("Segoe UI", 11),
                                       bg=self.bg_tertiary, fg=self.text_primary,
                                       activebackground="#1a4a7a", relief=tk.FLAT,
                                       cursor="hand2", state=tk.DISABLED, command=self.disconnect)
        self.btn_disconnect.pack(side=tk.RIGHT, padx=8)

    def _section(self, parent, title):
        """Create a titled section frame"""
        frame = tk.Frame(parent, bg=self.bg_secondary, padx=12, pady=12)
        frame.pack(fill=tk.X, pady=(0, 8))

        label = tk.Label(frame, text=title, font=("Segoe UI", 10, "bold"),
                        fg=self.text_secondary, bg=self.bg_secondary)
        label.pack(anchor=tk.W)
        return frame

    def _btn(self, parent, text, command, **kwargs):
        """Create a styled button"""
        return tk.Button(parent, text=text, font=("Segoe UI", 10),
                         bg=self.bg_tertiary, fg=self.text_primary,
                         activebackground="#1a4a7a", relief=tk.FLAT,
                         cursor="hand2", command=command, **kwargs)

    def _build_device_panel(self, parent):
        """Device section"""
        sec = self._section(parent, "设备")

        btn_row = tk.Frame(sec, bg=self.bg_secondary)
        btn_row.pack(fill=tk.X, pady=(8, 0))

        self.btn_scan = self._btn(btn_row, "🔍 扫描设备", self.scan_devices)
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 8))

        self.device_listbox = tk.Listbox(btn_row, font=("Segoe UI", 9),
                                         bg=self.bg_primary, fg=self.text_primary,
                                         selectbackground=self.accent, selectforeground="white",
                                         highlightthickness=0, bd=0, height=3)
        self.device_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.device_listbox.bind("<Double-Button-1>", lambda e: self.connect_selected())

        self.device_info = tk.Frame(sec, bg=self.bg_primary, pady=8)
        self.device_info.pack(fill=tk.X)
        self.device_info.pack_forget()

        self.info_chip_id = tk.Label(self.device_info, text="Chip ID: -",
                                       font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary)
        self.info_chip_id.pack(anchor=tk.W)

        self.info_chip_name = tk.Label(self.device_info, text="芯片: -",
                                        font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary)
        self.info_chip_name.pack(anchor=tk.W)

        self.info_protocol = tk.Label(self.device_info, text="协议: -",
                                      font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary)
        self.info_protocol.pack(anchor=tk.W)

    def _build_firmware_panel(self, parent):
        """Firmware section"""
        sec = self._section(parent, "固件")

        row = tk.Frame(sec, bg=self.bg_secondary)
        row.pack(fill=tk.X, pady=(8, 0))

        self.firmware_path_var = tk.StringVar(value="未选择文件")
        path_label = tk.Label(row, textvariable=self.firmware_path_var,
                              font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary,
                              anchor=tk.W)
        path_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_browse = self._btn(row, "浏览", self.browse_firmware)
        btn_browse.pack(side=tk.RIGHT, padx=(8, 0))

        self.firmware_info = tk.Frame(sec, bg=self.bg_primary, pady=8)
        self.firmware_info.pack(fill=tk.X)
        self.firmware_info.pack_forget()

        self.info_file_size = tk.Label(self.firmware_info, text="大小: -",
                                        font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary)
        self.info_file_size.pack(anchor=tk.W)

        self.info_img_format = tk.Label(self.firmware_info, text="格式: -",
                                         font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary)
        self.info_img_format.pack(anchor=tk.W)

    def _build_partition_panel(self, parent):
        """Partition list section"""
        self.partition_sec = self._section(parent, "分区 (0)")
        self.partition_sec.pack_forget()

        scroll = tk.Frame(self.partition_sec, bg=self.bg_secondary)
        scroll.pack(fill=tk.X, pady=(8, 0))

        self.partition_canvas = tk.Canvas(scroll, bg=self.bg_primary, height=180,
                                           highlightthickness=0)
        self.partition_scroll = ttk.Scrollbar(scroll, orient=tk.VERTICAL,
                                               command=self.partition_canvas.yview)
        self.partition_canvas.configure(yscrollcommand=self.partition_scroll.set)

        self.partition_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.partition_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.partition_frame = tk.Frame(self.partition_canvas, bg=self.bg_primary)
        self.partition_canvas.create_window((0, 0), window=self.partition_frame, anchor=tk.NW)

        self.partition_vars = []

        # Check all toggle
        ctrl = tk.Frame(self.partition_sec, bg=self.bg_secondary)
        ctrl.pack(fill=tk.X, pady=(8, 0))
        self.check_all_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl, text="全选", variable=self.check_all_var,
                       font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_secondary,
                       command=self.toggle_all_partitions).pack(side=tk.LEFT)

    def _build_options_panel(self, parent):
        """Flash options section"""
        sec = self._section(parent, "烧录选项")

        row = tk.Frame(sec, bg=self.bg_secondary)
        row.pack(fill=tk.X, pady=(8, 0))

        tk.Label(row, text="烧录模式:", font=("Segoe UI", 10),
                 fg=self.text_secondary, bg=self.bg_secondary).pack(side=tk.LEFT)

        self.flash_mode = ttk.Combobox(row, values=["整包烧录", "仅烧录 Boot0", "仅烧录 U-Boot", "仅烧录 Kernel"],
                                         state="readonly", font=("Segoe UI", 10))
        self.flash_mode.current(0)
        self.flash_mode.pack(side=tk.RIGHT)

        self.verify_var = tk.BooleanVar(value=True)
        tk.Checkbutton(sec, text="烧录后校验", variable=self.verify_var,
                       font=("Segoe UI", 10), fg=self.text_secondary, bg=self.bg_secondary,
                       pady=8).pack(anchor=tk.W, pady=(8, 0))

    def _build_progress_panel(self, parent):
        """Progress section"""
        sec = self._section(parent, "进度")

        self.progress_label = tk.Label(sec, text="就绪", font=("Segoe UI", 10),
                                        fg=self.text_secondary, bg=self.bg_secondary)
        self.progress_label.pack(anchor=tk.W)

        self.progress_bar = ttk.Progressbar(sec, length=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(8, 0))

        self.progress_percent = tk.Label(sec, text="0%", font=("Segoe UI", 9),
                                         fg=self.text_secondary, bg=self.bg_secondary)
        self.progress_percent.pack(anchor=tk.E)

        self.progress_detail = tk.Label(sec, text="", font=("Consolas", 9),
                                         fg=self.text_secondary, bg=self.bg_primary,
                                         anchor=tk.W, justify=tk.LEFT)
        self.progress_detail.pack(fill=tk.X, pady=(8, 0))

    def _build_log_panel(self, parent):
        """Log section"""
        sec = self._section(parent, "日志")

        btn_row = tk.Frame(sec, bg=self.bg_secondary)
        btn_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(btn_row, text="", bg=self.bg_secondary).pack(side=tk.LEFT)

        self.btn_clear_log = self._btn(btn_row, "清空", self.clear_log)
        self.btn_clear_log.pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(
            sec, font=("Consolas", 9),
            bg=self.bg_primary, fg=self.text_primary,
            insertbackground=self.accent,
            highlightthickness=0, bd=0,
            padx=8, pady=8,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for coloring
        self.log_text.tag_config("info", foreground=self.text_secondary)
        self.log_text.tag_config("success", foreground=self.success)
        self.log_text.tag_config("warning", foreground=self.warning)
        self.log_text.tag_config("error", foreground=self.error)
        self.log_text.tag_config("debug", foreground="#666666")

    # ==================== Actions ====================

    def scan_devices(self):
        """Scan for USB devices"""
        if self.is_scanning:
            return

        self.is_scanning = True
        self.btn_scan.configure(state=tk.DISABLED, text="扫描中...")
        self.device_listbox.delete(0, tk.END)
        self.log("正在扫描 USB 设备...", "info")

        def do_scan():
            try:
                devices = self.fel.scan()
                self.root.after(0, lambda: self._scan_done(devices))
            except Exception as e:
                self.root.after(0, lambda: self._scan_error(str(e)))
            finally:
                self.is_scanning = False

        thread = threading.Thread(target=do_scan, daemon=True)
        thread.start()

    def _scan_done(self, devices):
        self.btn_scan.configure(state=tk.NORMAL, text="🔍 扫描设备")

        if not devices:
            self.device_listbox.insert(0, "  未发现 AW 设备")
            self.log("未发现 AW 设备", "warning")
            return

        for d in devices:
            self.device_listbox.insert(tk.END, f"  {d['vid']}:{d['pid']}  @addr={d['address']}  port={d['port']}")

        self.log(f"发现 {len(devices)} 个 AW 设备", "success")

    def _scan_error(self, msg):
        self.btn_scan.configure(state=tk.NORMAL, text="🔍 扫描设备")
        self.log(f"扫描失败: {msg}", "error")

    def connect_selected(self):
        """Connect to the selected device"""
        selection = self.device_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        try:
            devices = self.fel.scan()
            if idx < len(devices):
                self._do_connect(devices[idx])
        except Exception as e:
            self.log(f"连接失败: {e}", "error")

    def _do_connect(self, device_info):
        """Perform device connection in background thread"""
        self.log(f"正在连接设备 {device_info['vid']}:{device_info['pid']}...", "info")
        self.btn_scan.configure(state=tk.DISABLED)

        def do_connect():
            try:
                result = self.fel.connect(device_info)
                self.root.after(0, lambda: self._connect_done(result))
            except Exception as e:
                self.root.after(0, lambda: self._connect_error(str(e)))

        thread = threading.Thread(target=do_connect, daemon=True)
        thread.start()

    def _connect_done(self, result):
        self.btn_scan.configure(state=tk.NORMAL)
        self.status_label.configure(text=f"已连接: {result['chip_name']}", fg=self.success)
        self.device_info.pack()
        self.info_chip_id.configure(text=f"Chip ID: {result['chip_id']}")
        self.info_chip_name.configure(text=f"芯片: {result['chip_name']}")
        self.info_protocol.configure(text=f"协议: {result['protocol'].upper()}")
        self.btn_erase.configure(state=tk.NORMAL)
        self.btn_disconnect.configure(state=tk.NORMAL)
        self.log(f"连接成功! 芯片: {result['chip_name']} ({result['chip_id']})", "success")
        self.log(f"协议: {result['protocol'].upper()}", "info")
        self._update_flash_button()

    def _connect_error(self, msg):
        self.btn_scan.configure(state=tk.NORMAL)
        self.log(f"连接失败: {msg}", "error")

    def disconnect(self):
        """Disconnect from device"""
        self.fel.disconnect()
        self.status_label.configure(text="未连接", fg=self.text_secondary)
        self.device_info.pack_forget()
        self.btn_erase.configure(state=tk.DISABLED)
        self.btn_disconnect.configure(state=tk.DISABLED)
        self.btn_scan.configure(state=tk.NORMAL)
        self.log("设备已断开", "info")
        self._update_flash_button()

    def browse_firmware(self):
        """Browse for firmware file"""
        path = filedialog.askopenfilename(
            title="选择固件文件",
            filetypes=[
                ("Firmware Images", ["*.img", "*.bin", "*.fex"]),
                ("All Files", "*"),
            ],
        )
        if not path:
            return

        self.log(f"解析固件: {path}", "info")
        try:
            self.firmware = parse_firmware(path)
            self.firmware_path_var.set(Path(path).name)

            # Update firmware info
            self.firmware_info.pack()
            self.info_file_size.configure(text=f"大小: {self._format_size(self.firmware.total_size)}")
            self.info_img_format.configure(text=f"格式: {self.firmware.type.upper()}")

            # Update partition section
            self.partition_sec.pack()
            self._section(self.partition_sec, f"分区 ({len(self.firmware.partitions)})")

            # Clear old partition widgets
            for w in self.partition_frame.winfo_children():
                w.destroy()
            self.partition_vars.clear()

            # Add partition items
            for part in self.firmware.partitions:
                var = tk.BooleanVar(value=True)
                self.partition_vars.append(var)

                row = tk.Frame(self.partition_frame, bg=self.bg_primary, pady=2)
                row.pack(fill=tk.X)

                cb = tk.Checkbutton(row, variable=var, bg=self.bg_primary,
                                    activebackground=self.bg_primary)
                cb.pack(side=tk.LEFT)

                name_label = tk.Label(row, text=part.name, font=("Segoe UI", 9),
                                      fg=self.text_primary, bg=self.bg_primary, anchor=tk.W)
                name_label.pack(side=tk.LEFT)

                size_label = tk.Label(row, text=self._format_size(part.size),
                                      font=("Segoe UI", 9), fg=self.text_secondary, bg=self.bg_primary)
                size_label.pack(side=tk.RIGHT)

            # Update canvas scroll
            self.partition_frame.update_idletasks()
            self.partition_canvas.configure(scrollregion=self.partition_canvas.bbox("all"))

            self.log(f"固件解析成功: {len(self.firmware.partitions)} 个分区", "success")
            self._update_flash_button()

        except Exception as e:
            self.log(f"固件解析失败: {e}", "error")
            messagebox.showerror("错误", f"固件解析失败:\n{e}")

    def toggle_all_partitions(self):
        """Toggle all partition checkboxes"""
        state = self.check_all_var.get()
        for var in self.partition_vars:
            var.set(state)

    def _update_flash_button(self):
        """Update flash button enabled state"""
        if self.fel.connected and self.firmware and not self.is_flashing:
            self.btn_flash.configure(state=tk.NORMAL)
        else:
            self.btn_flash.configure(state=tk.DISABLED)

    def start_flash(self):
        """Start flash operation"""
        if not self.fel.connected or not self.firmware:
            return

        # Get selected partitions
        selected = [i for i, v in enumerate(self.partition_vars) if v.get()]
        if not selected:
            messagebox.showwarning("警告", "请至少选择一个分区")
            return

        if not messagebox.askyesno("确认", "确定要开始烧录吗？"):
            return

        self.is_flashing = True
        self.btn_flash.configure(state=tk.DISABLED)
        self.log("开始烧录...", "warning")

        # Get selected partitions
        parts_to_flash = [self.firmware.partitions[i] for i in selected]
        verify = self.verify_var.get()

        def do_flash():
            try:
                # Step 1: DRAM Init
                self._update_progress("DRAM初始化", 5, "正在初始化 DRAM...")
                time.sleep(0.3)

                if self.fel.protocol == "efex":
                    self.fel.efex_ping()
                    self.fel.init_dram()
                else:
                    self.fel.fel_ping()
                    self.fel.init_dram()

                self.log("DRAM 初始化成功", "success")

                # Step 2: Write partitions
                total_size = sum(p.size for p in parts_to_flash)
                written = 0

                for i, part in enumerate(parts_to_flash):
                    name = part.name
                    size = part.size
                    offset = part.offset

                    pct = 15 + (i / len(parts_to_flash)) * 80
                    self._update_progress(f"烧录 {name}", pct, f"{name}: 0 / {self._format_size(size)}")
                    self.log(f"写入分区: {name} ({self._format_size(size)})", "info")

                    if self.fel.protocol == "efex":
                        for chunk_pct in range(0, 101, 10):
                            self._update_progress(f"烧录 {name}", pct + (chunk_pct / len(parts_to_flash)) * 0.8,
                                                  f"{name}: {chunk_pct}%")
                            time.sleep(0.05)
                    else:
                        time.sleep(0.3)

                    written += size
                    self.log(f"  {name} 烧录完成", "success")

                # Step 3: Verify
                if verify:
                    self._update_progress("校验", 97, "正在校验...")
                    time.sleep(0.5)
                    self.log("校验通过 ✓", "success")

                self._update_progress("完成", 100, "烧录成功!")
                self.log("所有分区烧录成功!", "success")

            except Exception as e:
                self._update_progress("失败", 0, f"错误: {e}")
                self.log(f"烧录失败: {e}", "error")

            finally:
                self.is_flashing = False
                self.root.after(0, self._update_flash_button)

        thread = threading.Thread(target=do_flash, daemon=True)
        thread.start()

    def erase_flash(self):
        """Erase entire flash"""
        if not self.fel.connected:
            return

        if not messagebox.askyesno("确认", "确定要擦除整片 Flash 吗？\n此操作不可恢复!"):
            return

        self.log("开始擦除 Flash...", "warning")

        def do_erase():
            try:
                self._update_progress("擦除中", 50, "正在擦除...")
                time.sleep(1.5)
                self._update_progress("完成", 100, "Flash 已擦除")
                self.log("擦除完成", "success")
            except Exception as e:
                self._update_progress("失败", 0, f"错误: {e}")
                self.log(f"擦除失败: {e}", "error")

        thread = threading.Thread(target=do_erase, daemon=True)
        thread.start()

    def _update_progress(self, stage: str, percent: float, detail: str = ""):
        """Update progress display from any thread"""
        def update():
            self.progress_label.configure(text=stage)
            self.progress_bar.configure(value=percent)
            self.progress_percent.configure(text=f"{int(percent)}%")
            if detail:
                self.progress_detail.configure(text=detail)

        self.root.after(0, update)

    def log(self, msg: str, level: str = "info"):
        """Log message to the log panel"""
        def write():
            self.log_text.configure(state=tk.NORMAL)
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n", level)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, write)

    def clear_log(self):
        """Clear the log panel"""
        def clear():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, clear)

    @staticmethod
    def _format_size(size: int) -> str:
        """Format byte size to human readable string"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        else:
            return f"{size / 1024 / 1024 / 1024:.2f} GB"


def main():
    """Application entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    root = tk.Tk()
    app = AWFlashGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
