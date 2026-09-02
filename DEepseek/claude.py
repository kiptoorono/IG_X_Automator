import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import csv
import os
import time
import random
import threading
import sys
import re
import subprocess
import socket
import json
from datetime import datetime
import pyfiglet

# ---- Banner ----
def print_banner():
    G = "\033[92m"
    DG = "\033[32m"
    W = "\033[97m"
    Y = "\033[93m"
    C = "\033[96m"
    R = "\033[91m"
    X = "\033[0m"
    lines = pyfiglet.figlet_format("IG Reels", font="slant").splitlines()
    print(DG + "#" * 74 + X)
    print("\n".join([G + line + X for line in lines]))
    print(DG + "#" * 74 + X)
    print(f"  {R}!! SYS{X}  {W}IG REELS SCOUTER PRO{X:<40}{Y}v2.0.2{X}")
    print(f"  {C}>> MODE{X}  {W}AUTO COLLECTION | VETTING{X}")
    print(f"  {C}>> TGTS{X}  {W}instagram.com/reels{X}")
    print(f"  {C}>> STAT{X}  {W}READY{X}")

print_banner()

# ---- Selenium imports ----
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import SessionNotCreatedException

# ---- uiautomator2 for auto collection ----
try:
    import uiautomator2 as u2
except ImportError:
    u2 = None

# ---- Config ----
from config import (
    DATA_DIR,
    CLEAN_LEADS_FILE,
    SUBMITTED_FILE,
    BLACKLIST_FILE,
    DUPLICATE_CACHE_FILE,
    COLLECTED_PAIRS_FILE,
    SCREENSHOT_DIR,
    CHROME_PATH,
    USER_CHROME_DATA_DIR,
    BOT_PROFILE_NAME,
    send_to_discord,
    log_stats
)

# =========================================================================
# ---- UI Theme (Instagram-inspired dark palette + small helper utils) ----
# =========================================================================
THEME = {
    "bg":          "#0b0b0d",
    "bg_alt":      "#111114",
    "card":        "#17171b",
    "card_border": "#2a2a30",
    "text":        "#f5f5f7",
    "muted":       "#8a8a93",
    "purple":      "#5f27cd",
    "magenta":     "#c13584",
    "pink":        "#e1306c",
    "red":         "#ed4956",
    "orange":      "#f77737",
    "yellow":      "#fcaf45",
    "success":     "#3ddc84",
    "warning":     "#fcaf45",
    "error":       "#ed4956",
    "info":        "#e6e6e8",
}

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def _rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb

def _lerp_color(c1, c2, t):
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex((int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)))

def draw_gradient(canvas, width, height, colors):
    """Paints a smooth left-to-right gradient across the given colors onto a Canvas."""
    canvas.delete("gradient")
    segments = len(colors) - 1
    if segments <= 0 or width <= 0:
        return
    seg_width = max(width / segments, 1)
    for i in range(segments):
        c1, c2 = colors[i], colors[i + 1]
        steps = max(int(seg_width), 1)
        for s in range(steps):
            t = s / max(steps - 1, 1)
            color = _lerp_color(c1, c2, t)
            x = int(i * seg_width + s)
            canvas.create_line(x, 0, x, height, fill=color, tags="gradient")
    canvas.tag_lower("gradient")

def style_button(btn, base, hover, fg="white"):
    """Applies a flat, modern look to a tk.Button and wires up a hover effect."""
    btn.configure(
        bg=base, fg=fg, activebackground=hover, activeforeground=fg,
        bd=0, relief="flat", font=("Segoe UI", 10, "bold"),
        cursor="hand2", padx=10, pady=10, highlightthickness=0,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover) if btn["state"] != "disabled" else None)
    btn.bind("<Leave>", lambda e: btn.configure(bg=base) if btn["state"] != "disabled" else None)

# ---- Regex helpers (only profile extraction now) ----
_PROFILE_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)(?:[/?].*)?$",
    re.IGNORECASE,
)
_IG_RESERVED = {
    "reel", "reels", "p", "tv", "explore", "stories", "accounts",
    "about", "legal", "policies", "developer", "help", "privacy",
    "safety", "blog", "press", "api", "oauth", "challenge",
    "login", "signup", "direct", "location", "tags", "search",
}

def extract_handle_from_url(profile_url: str) -> str:
    """Extract @handle from Instagram profile URL, or return None if invalid."""
    m = _PROFILE_RE.search(profile_url)
    if m:
        username = m.group(1).lower()
        if username not in _IG_RESERVED:
            return f"@{username}"
    return None

# ---- Chrome driver helpers (unchanged) ----
def get_chrome_profiles() -> list[dict]:
    import json
    profiles = []
    if not os.path.isdir(USER_CHROME_DATA_DIR):
        return profiles
    for entry in os.listdir(USER_CHROME_DATA_DIR):
        prefs_path = os.path.join(USER_CHROME_DATA_DIR, entry, "Preferences")
        if not os.path.isfile(prefs_path):
            continue
        try:
            with open(prefs_path, "r", encoding="utf-8", errors="ignore") as f:
                prefs = json.load(f)
            profile_info = prefs.get("profile", {})
            name = profile_info.get("name", entry)
            email = ""
            account_info = prefs.get("account_info", [])
            if account_info and isinstance(account_info, list):
                email = account_info[0].get("email", "")
            if not email:
                signin = prefs.get("signin", {})
                last_email = signin.get("last_signed_in_email", "")
                if last_email:
                    email = last_email
            profiles.append({"folder": entry, "name": name, "email": email})
        except Exception:
            continue
    return profiles

def pick_chrome_profile() -> str:
    profiles = get_chrome_profiles()
    if not profiles:
        return "Default"

    chosen = {"folder": "Default"}
    # NOTE: this used to be tk.Tk(), which spins up a second Tcl root/interpreter
    # while the main app's mainloop is already running. That can hang or silently
    # fail to return, which is why the browser step sometimes never kicked off.
    # Toplevel() attaches to the existing root instead, and wait_window() blocks
    # this call until the picker closes — the correct pattern here.
    picker = tk.Toplevel()
    picker.title("Choose Chrome Profile")
    picker.configure(bg=THEME["bg"])
    picker.resizable(False, False)
    picker.attributes("-topmost", True)
    picker.grab_set()

    tk.Label(
        picker,
        text="Select the Chrome profile logged into ViralTasks:",
        font=("Segoe UI", 9, "bold"), fg=THEME["pink"], bg=THEME["bg"],
        padx=14, pady=10,
    ).pack()

    listbox = tk.Listbox(
        picker,
        font=("Consolas", 9), bg=THEME["card"], fg=THEME["text"],
        selectbackground=THEME["magenta"], selectforeground="#ffffff",
        activestyle="none", bd=0, highlightthickness=1,
        highlightbackground=THEME["card_border"],
        width=52, height=min(len(profiles), 10),
    )
    listbox.pack(padx=14, pady=(0, 8))

    for p in profiles:
        email_str = f"  {p['email']}" if p["email"] else ""
        listbox.insert(tk.END, f"  {p['name']}{email_str}  [{p['folder']}]")

    listbox.selection_set(0)
    listbox.activate(0)

    def on_select():
        idx = listbox.curselection()
        if idx:
            chosen["folder"] = profiles[idx[0]]["folder"]
        picker.destroy()

    btn = tk.Button(picker, text="Use This Profile", command=on_select)
    style_button(btn, THEME["magenta"], THEME["pink"])
    btn.pack(pady=(0, 14), padx=14, fill="x")

    picker.eval("tk::PlaceWindow . center")
    picker.wait_window()
    return chosen["folder"]

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except Exception:
            return False


def get_chrome_major_version(chrome_path: str) -> int | None:
    try:
        output = subprocess.check_output([chrome_path, '--version'], stderr=subprocess.STDOUT, text=True)
        match = re.search(r"(\d+)\.\d+\.\d+\.\d+", output)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return None


def get_chromedriver_with_version_check():
    """Return a chromedriver path that matches the installed Chrome major version when possible."""
    chrome_major = get_chrome_major_version(CHROME_PATH) if CHROME_PATH else None
    try:
        if chrome_major:
            return ChromeDriverManager(driver_version=str(chrome_major)).install()
    except Exception:
        pass
    return ChromeDriverManager().install()


def kill_chrome_and_release_locks():
    """Kill chrome/chromedriver and remove potential lock files in the user data dir."""
    try:
        subprocess.run("taskkill /F /IM chrome.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run("taskkill /F /IM chromedriver.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(1.0)
    try:
        lock_paths = [
            os.path.join(USER_CHROME_DATA_DIR, "SingletonLock"),
            os.path.join(USER_CHROME_DATA_DIR, "lock"),
            os.path.join(USER_CHROME_DATA_DIR, BOT_PROFILE_NAME, "SingletonLock"),
            os.path.join(USER_CHROME_DATA_DIR, BOT_PROFILE_NAME, "lock")
        ]
        for lp in lock_paths:
            try:
                if os.path.exists(lp):
                    os.remove(lp)
            except Exception:
                pass
    except Exception:
        pass


def safe_init_webdriver(service, options):
    """Initialize webdriver safely, retrying once after killing chrome if common profile/lock errors occur."""
    try:
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in ("session not created", "devtoolsactiveport", "failed to start", "webdriver")):
            kill_chrome_and_release_locks()
            try:
                return webdriver.Chrome(service=service, options=options)
            except Exception:
                raise
        raise


def build_chrome_driver(profile_folder: str = "Default", initial_url: str | None = None):
    if not CHROME_PATH:
        raise Exception("Google Chrome not found.")

    opts = ChromeOptions()
    opts.binary_location = CHROME_PATH
    opts.add_argument(f"--user-data-dir={USER_CHROME_DATA_DIR}")
    opts.add_argument(f"--profile-directory={profile_folder}")
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-popup-blocking")

    service = ChromeService(get_chromedriver_with_version_check())
    drv = safe_init_webdriver(service, opts)

    if initial_url:
        try:
            drv.get(initial_url)
        except Exception:
            pass
    return drv

# ---- Robust platform selection (unchanged) ----
def select_instagram_platform(driver, timeout=10):
    """
    Selects 'Instagram' from the platform dropdown on ViralTasks.
    Handles both native <select> and custom dropdowns (React/Vue).
    Returns True on success, False otherwise.
    """
    try:
        wait = WebDriverWait(driver, timeout)
        # First, try to find a native <select> element
        select_elements = driver.find_elements(By.XPATH, "//select")
        if select_elements:
            select_obj = Select(select_elements[0])
            # Check if any option contains "instagram"
            for opt in select_obj.options:
                if "instagram" in opt.text.lower():
                    select_obj.select_by_visible_text(opt.text.strip())
                    # Trigger change event
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", select_elements[0])
                    return True
            # Fallback: select by exact text
            select_obj.select_by_visible_text("Instagram")
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", select_elements[0])
            return True
        else:
            # Custom dropdown: find a label with "Social Media" or "Platform"
            label = driver.find_element(By.XPATH, "//*[contains(text(),'Social Media') or contains(text(),'Platform')]")
            # Find the closest container that has a dropdown toggle
            container = label.find_element(By.XPATH, "./ancestor::div[1]")
            # Look for a clickable element that opens the dropdown (div with role='button' or class containing 'dropdown', 'select')
            toggle = container.find_element(By.XPATH, ".//div[@role='button' or contains(@class, 'dropdown') or contains(@class, 'select')]")
            toggle.click()
            time.sleep(0.5)
            # Now find the option with text containing "Instagram"
            option = driver.find_element(By.XPATH, "//*[contains(text(),'Instagram')]")
            option.click()
            return True
    except Exception as e:
        print(f"[!] Platform selection error: {e}")
        return False

# ---- ViralTasks duplicate check (unchanged) ----
def vt_check_handle(driver, handle: str, timeout: int = 14):
    """
    Returns True (fresh), False (dupe), or None (timeout/error).
    """
    VT_URL = "https://viraltasks.com/platform/leads/project/67de0467-441a-4846-bc0d-0b303fc1ed1b"
    try:
        if driver.current_url != VT_URL:
            driver.get(VT_URL)
            time.sleep(3)
        wait = WebDriverWait(driver, timeout)

        # Reset form – click "Back" if present
        backs = driver.find_elements(By.XPATH, "//button[contains(.,'Back')]")
        if backs:
            try:
                backs[0].click()
                time.sleep(0.8)
            except Exception:
                pass

        # Select platform using robust function
        if not select_instagram_platform(driver, timeout=10):
            # If selection fails, try fallback: use Select with visible text
            try:
                select_el = driver.find_element(By.XPATH, "//select")
                Select(select_el).select_by_visible_text("Instagram")
            except:
                pass  # give up

        # Enter handle (with @)
        inp = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='text']")))
        inp.clear()
        inp.send_keys(handle)
        time.sleep(0.4)

        # Click Check button
        check_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(.,'Check') or contains(.,'Verify')]")
        ))
        check_btn.click()

        # Poll for outcome
        deadline = time.time() + timeout
        while time.time() < deadline:
            if driver.find_elements(By.XPATH, "//button[contains(.,'Back to Duplicate Check')]"):
                return True   # FRESH
            src = driver.page_source.lower()
            # Look for explicit duplicate messages only (avoid matching generic 'duplicate' text)
            if "already exists" in src or "duplicate values" in src:
                return False  # DUPE
            time.sleep(0.4)
        return None  # Timed out
    except Exception as e:
        print(f"[VT CHECK ERROR] {e}")
        return None

# ---- Main application ----
class MainLauncherPro:
    def __init__(self, root):
        self.root = root
        self.root.title("IG Reels Scouter Pro")
        self.root.geometry("480x680")
        self.root.configure(bg=THEME["bg"])
        self.root.resizable(False, False)

        self.is_running = False
        self.auto_collect_active = False

        self.ensure_files()
        self.setup_ui()
        self.update_stats()

        if u2 is None:
            self.log("uiautomator2 not installed — auto-collection disabled. Run: pip install uiautomator2", "warning")

    def ensure_files(self):
        # Ensure all necessary files exist with headers
        for f, header in [
            (CLEAN_LEADS_FILE, ["Handle", "Followers", "Email", "Account URL", "Video URL", "Status"]),
            (SUBMITTED_FILE, ["Handle", "Status", "Timestamp"]),
            (COLLECTED_PAIRS_FILE, ["Handle", "Account URL", "Video URL", "Email"])
        ]:
            if not os.path.exists(f):
                with open(f, 'w', encoding='utf-8', newline='') as fp:
                    csv.writer(fp).writerow(header)
        for f in [BLACKLIST_FILE, DUPLICATE_CACHE_FILE]:
            if not os.path.exists(f):
                open(f, 'w', encoding='utf-8').close()

    # ---------------------------------------------------------------
    # UI
    # ---------------------------------------------------------------
    def setup_ui(self):
        # --- Gradient header banner (IG-style), compact ---
        header = tk.Canvas(self.root, width=480, height=40, highlightthickness=0, bg=THEME["bg"])
        header.pack(fill="x")
        draw_gradient(header, 480, 40, [THEME["purple"], THEME["magenta"], THEME["pink"], THEME["orange"]])
        header.create_text(240, 15, text="ALGOMINER TOOLS", font=("Segoe UI", 13, "bold"), fill="white")
        header.create_text(240, 30, text="IG Scouter", font=("Segoe UI", 8), fill="#fbe9ff")

        # --- Stats card ---
        stats_frame = tk.Frame(self.root, bg=THEME["card"], highlightbackground=THEME["card_border"], highlightthickness=1)
        stats_frame.pack(fill="x", padx=14, pady=(10, 6))

        def stat_block(row, col, color, title):
            cell = tk.Frame(stats_frame, bg=THEME["card"])
            cell.grid(row=row, column=col, sticky="w", padx=12, pady=6)
            dot = tk.Canvas(cell, width=7, height=7, bg=THEME["card"], highlightthickness=0)
            dot.create_oval(0, 0, 7, 7, fill=color, outline="")
            dot.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 6))
            tk.Label(cell, text=title, font=("Segoe UI", 7, "bold"), fg=color, bg=THEME["card"]).grid(row=0, column=1, sticky="w")
            value_lbl = tk.Label(cell, text="0", font=("Segoe UI", 11, "bold"), fg=color, bg=THEME["card"])
            value_lbl.grid(row=1, column=1, sticky="w")
            return value_lbl

        self.lbl_pairs = stat_block(0, 0, THEME["pink"], "COLLECTED PAIRS")
        self.lbl_clean = stat_block(0, 1, THEME["yellow"], "CLEAN LEADS")
        self.lbl_submitted = stat_block(1, 0, THEME["success"], "TOTAL SUBMITTED")
        self.lbl_dupe = stat_block(1, 1, THEME["muted"], "DUPLICATES CACHED")

        # --- Action buttons ---
        btn_frame = tk.Frame(self.root, bg=THEME["bg"])
        btn_frame.pack(fill="x", padx=14, pady=(4, 4))

        self.btn_collect = tk.Button(btn_frame, text="📱  START AUTO COLLECTION", command=self.toggle_auto_collect)
        style_button(self.btn_collect, THEME["magenta"], THEME["pink"])
        self.btn_collect.pack(fill="x", pady=(0, 8))

        self.btn_check = tk.Button(btn_frame, text="🔍  CHECK DUPLICATES  ·  PHASE 2", command=self.start_duplicate_check)
        style_button(self.btn_check, THEME["purple"], "#7a4fe0")
        self.btn_check.pack(fill="x", pady=(0, 8))

        self.btn_vet = tk.Button(btn_frame, text="👁  OPEN VETTING CONSOLE", command=self.open_vetting_console)
        style_button(self.btn_vet, THEME["orange"], THEME["yellow"], fg="#1a1a1a")
        self.btn_vet.pack(fill="x", pady=(0, 8))

        self.btn_stop = tk.Button(self.root, text="⏹  STOP CURRENT TASK", state='disabled', command=self.stop_current_task)
        style_button(self.btn_stop, THEME["red"], "#ff6b78")
        self.btn_stop.pack(fill="x", padx=14, pady=(4, 10))

        # --- Activity log ---
        tk.Label(self.root, text="ACTIVITY LOG", font=("Segoe UI", 8, "bold"), fg=THEME["muted"], bg=THEME["bg"]).pack(anchor="w", padx=16, pady=(0, 4))
        log_card = tk.Frame(self.root, bg=THEME["card"], highlightbackground=THEME["card_border"], highlightthickness=1)
        log_card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.log_area = scrolledtext.ScrolledText(
            log_card, height=10, font=("Consolas", 9),
            state='disabled', bg=THEME["card"], fg=THEME["text"],
            insertbackground=THEME["text"], bd=0, highlightthickness=0,
            padx=10, pady=8,
        )
        self.log_area.pack(fill="both", expand=True)
        self.log_area.tag_config("timestamp", foreground=THEME["muted"])
        self.log_area.tag_config("info", foreground=THEME["info"])
        self.log_area.tag_config("success", foreground=THEME["success"])
        self.log_area.tag_config("warning", foreground=THEME["warning"])
        self.log_area.tag_config("error", foreground=THEME["error"])

    def log(self, message, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, f"{ts}  ", "timestamp")
        self.log_area.insert(tk.END, f"{message}\n", level)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def update_stats(self):
        try:
            self.lbl_pairs.config(text=str(self.get_pairs_count()))
            self.lbl_clean.config(text=str(self.get_clean_count()))
            self.lbl_submitted.config(text=str(self.get_total_lifetime_submissions()))
            self.lbl_dupe.config(text=str(self.get_dupe_cache_count()))
        except Exception as e:
            print(f"Stats Error: {e}")
        self.root.after(5000, self.update_stats)

    def get_pairs_count(self):
        if not os.path.exists(COLLECTED_PAIRS_FILE):
            return 0
        with open(COLLECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
            return max(0, len([l for l in f if l.strip()]) - 1)

    def get_clean_count(self):
        if not os.path.exists(CLEAN_LEADS_FILE):
            return 0
        with open(CLEAN_LEADS_FILE, 'r', encoding='utf-8') as f:
            return max(0, len([l for l in f if l.strip()]) - 1)

    def get_total_lifetime_submissions(self):
        if os.path.exists(SUBMITTED_FILE):
            with open(SUBMITTED_FILE, 'r', encoding='utf-8') as f:
                return max(0, len([l for l in f if l.strip()]) - 1)
        return 0

    def get_dupe_cache_count(self):
        if os.path.exists(DUPLICATE_CACHE_FILE):
            with open(DUPLICATE_CACHE_FILE, 'r', encoding='utf-8') as f:
                return len([l for l in f if l.strip()])
        return 0

    def stop_current_task(self):
        self.is_running = False
        self.auto_collect_active = False
        self.log("Stop requested.", "warning")
        self.btn_stop.config(state='disabled')
        self.btn_collect.config(text="📱  START AUTO COLLECTION", bg=THEME["magenta"])

    def set_ui_state(self, active):
        state = 'disabled' if active else 'normal'
        self.btn_collect.config(state='normal' if not self.auto_collect_active else 'disabled')
        self.btn_check.config(state=state)
        self.btn_vet.config(state='normal')
        self.is_running = active
        self.btn_stop.config(state='normal' if active else 'disabled')

    # ---------- Phase 1: Auto Collection (uiautomator2) ----------
    def toggle_auto_collect(self):
        if self.auto_collect_active:
            self.auto_collect_active = False
            self.btn_collect.config(text="📱  START AUTO COLLECTION", bg=THEME["magenta"])
            self.log("Auto-collection stopped.", "warning")
        else:
            if u2 is None:
                messagebox.showerror("Missing dependency", "uiautomator2 not installed.\nInstall with: pip install uiautomator2")
                return
            self.auto_collect_active = True
            self.btn_collect.config(text="⏹  STOP AUTO COLLECTION", bg=THEME["red"])
            self.is_running = True
            self.btn_stop.config(state='normal')
            self.log("Auto-collection started — connecting to device...", "info")
            threading.Thread(target=self._auto_collect_loop, daemon=True).start()

    def _auto_collect_loop(self):
        """Runs the uiautomator2 script to collect profile+reel pairs."""
        MAX_REELS = 20  # configurable
        PACKAGE_NAME = "com.instagold.android"  # IG Gold

        try:
            d = u2.connect()
            self.log(f"Connected to device: {d.info['productName']}", "success")

            # Enable IME for clipboard access
            d.set_fastinput_ime()

            # Start Instagram
            d.shell('monkey -p {} -c android.intent.category.LAUNCHER 1'.format(PACKAGE_NAME))
            time.sleep(5)

            # Confirm the app actually made it to the foreground before we
            # start hunting for UI elements — "monkey" returns immediately
            # even if the launch failed or got interrupted (e.g. an update
            # dialog, permission prompt, or the launcher animation still
            # running), which used to cause false "tab not found" aborts.
            app_ready = False
            for _ in range(6):
                try:
                    current = d.app_current()
                except Exception:
                    current = {}
                if current.get("package") == PACKAGE_NAME:
                    app_ready = True
                    break
                time.sleep(1)
            if not app_ready:
                self.log(f"{PACKAGE_NAME} never reached the foreground — aborting.", "error")
                return

            # Navigate to Reels — retry a few times with short waits, since
            # the tab can take a moment to render right after a cold launch.
            reels_selectors = [
                lambda: d(resourceId="com.instagold.android:id/clips_tab"),
                lambda: d(description="Reels"),
                lambda: d(text="Reels"),
                lambda: d(textContains="Reel"),
            ]
            reels_opened = False
            for attempt in range(5):
                for selector in reels_selectors:
                    el = selector()
                    if el.exists:
                        el.click()
                        reels_opened = True
                        break
                if reels_opened:
                    break
                time.sleep(1.5)

            if not reels_opened:
                self._dump_ui_for_debugging("reels_tab_not_found")
                self.log("Could not find the Reels tab — aborting. UI dump saved for debugging (see below).", "error")
                return
            time.sleep(3)

            collected = 0
            for i in range(MAX_REELS):
                if not self.is_running:
                    self.log("Auto-collection interrupted by user.", "warning")
                    break

                # --- Get Profile URL ---
                username_btn = d(resourceId="com.instagold.android:id/clips_author_username")
                if not username_btn.exists:
                    username_btn = d(className="android.widget.Button", descriptionContains="and")
                if not username_btn.exists:
                    width, height = d.window_size()
                    d.click(int(width * 0.12), int(height * 0.12))
                    time.sleep(2)
                else:
                    username_btn.click()
                    time.sleep(2)

                # Wait for profile
                d(resourceId="com.instagold.android:id/action_bar_title").wait(timeout=5)

                # Open Options menu
                if d(description="Options").exists:
                    d(description="Options").click()
                else:
                    width, height = d.window_size()
                    d.click(int(width * 0.9), int(height * 0.08))
                time.sleep(1.5)

                # Click Copy
                if not d(description="Copy").wait(timeout=3):
                    if not d(text="Copy").wait(timeout=2):
                        self.log(f"Reel {i+1}: copy button not found — skipped.", "warning")
                        d.press("back")
                        if i < MAX_REELS - 1:
                            d.swipe(500, 800, 500, 300, duration=0.3)
                            time.sleep(3)
                        continue
                copy_btn = d(description="Copy") if d(description="Copy").exists else d(text="Copy")
                if copy_btn.exists:
                    copy_btn.click()
                    time.sleep(1.5)
                else:
                    self.log(f"Reel {i+1}: copy button not found — skipped.", "warning")
                    d.press("back")
                    if i < MAX_REELS - 1:
                        d.swipe(500, 800, 500, 300, duration=0.3)
                        time.sleep(3)
                    continue

                profile_url = d.clipboard
                if not (profile_url and ("instagram.com" in profile_url or "instagr.am" in profile_url)):
                    profile_url = None

                # Return to Reel – Back press
                d.press("back")
                time.sleep(3)
                if d(resourceId="com.instagold.android:id/action_bar_title").exists(timeout=2):
                    d.press("back")
                    time.sleep(3)

                # Safety net: if we're not actually back on the Reels feed
                # (can happen after 2+ profiles), recover instead of pressing
                # on blind and fumbling around inside a profile/settings page.
                if not self._recover_to_reels(
                    d, PACKAGE_NAME,
                    reel_resource_id="com.instagold.android:id/like_button",
                    clips_tab_resource_id="com.instagold.android:id/clips_tab",
                ):
                    self.log(f"Reel {i+1}: could not recover to Reels feed — stopping.", "error")
                    break

                if not profile_url:
                    self.log(f"Reel {i+1}: no profile URL captured — skipped.", "warning")
                    if i < MAX_REELS - 1:
                        d.swipe(500, 800, 500, 300, duration=0.3)
                        time.sleep(3)
                    continue

                # --- Get Reel URL ---
                # Wait for the Reel to load (like_button)
                d(resourceId="com.instagold.android:id/like_button").wait(timeout=5)

                share_btn = None
                # Find Share/More button
                if d(resourceId="com.instagold.android:id/direct_share_button").exists:
                    share_btn = d(resourceId="com.instagold.android:id/direct_share_button")
                elif d(resourceId="com.instagram.android:id/row_feed_action_share").exists:
                    share_btn = d(resourceId="com.instagram.android:id/row_feed_action_share")
                elif d(description="Share").exists:
                    share_btn = d(description="Share")
                elif d(descriptionContains="Share").exists:
                    share_btn = d(descriptionContains="Share")
                elif d(description="More options").exists:
                    share_btn = d(description="More options")
                elif d(resourceId="com.instagold.android:id/clips_ufi_more_button_component").exists:
                    share_btn = d(resourceId="com.instagold.android:id/clips_ufi_more_button_component")
                elif d(description="More").exists:
                    share_btn = d(description="More")

                if share_btn is None:
                    width, height = d.window_size()
                    d.click(int(width * 0.9), int(height * 0.2))
                    time.sleep(1.5)
                else:
                    share_btn.click()
                    time.sleep(1.5)

                # Find "Copy link" with retries
                copy_link_btn = None
                for attempt in range(8):
                    if d(description="Copy link").exists:
                        copy_link_btn = d(description="Copy link")
                        break
                    if d(text="Copy link").exists:
                        copy_link_btn = d(text="Copy link")
                        break
                    if d(text="Copy URL").exists:
                        copy_link_btn = d(text="Copy URL")
                        break
                    if d(text="Salin tautan").exists:
                        copy_link_btn = d(text="Salin tautan")
                        break
                    if d(textContains="Copy").exists:
                        copy_link_btn = d(textContains="Copy")
                        break
                    time.sleep(0.5)

                if copy_link_btn is None:
                    self.log(f"Reel {i+1}: copy-link button not found — skipped.", "warning")
                    d.press("back")
                    if i < MAX_REELS - 1:
                        d.swipe(500, 800, 500, 300, duration=0.3)
                        time.sleep(3)
                    continue

                copy_link_btn.click()
                time.sleep(1.5)

                reel_url = d.clipboard
                if not (reel_url and ("instagram.com" in reel_url or "instagr.am" in reel_url)):
                    reel_url = None

                # Close share menu
                d.press("back")
                time.sleep(0.5)

                if not reel_url:
                    self.log(f"Reel {i+1}: no reel URL captured — skipped.", "warning")
                    if i < MAX_REELS - 1:
                        d.swipe(500, 800, 500, 300, duration=0.3)
                        time.sleep(3)
                    continue

                # --- Save the pair ---
                handle = extract_handle_from_url(profile_url)
                if not handle:
                    self.log(f"Reel {i+1}: invalid handle — skipped.", "warning")
                    if i < MAX_REELS - 1:
                        d.swipe(500, 800, 500, 300, duration=0.3)
                        time.sleep(3)
                    continue

                self._save_collected_pair(handle, profile_url, reel_url, "")
                collected += 1
                self.root.after(0, self.update_stats)

                # Scroll to next reel
                if i < MAX_REELS - 1:
                    d.swipe(500, 800, 500, 300, duration=0.3)
                    time.sleep(3)

            self.log(f"Auto-collection finished — {collected} pairs collected.", "success")
            self.auto_collect_active = False
            self.root.after(0, lambda: self.btn_collect.config(text="📱  START AUTO COLLECTION", bg=THEME["magenta"]))
            self.root.after(0, lambda: self.btn_stop.config(state='disabled'))

        except Exception as e:
            self.log(f"Auto-collection error: {e}", "error")
            self.auto_collect_active = False
            self.root.after(0, lambda: self.btn_collect.config(text="📱  START AUTO COLLECTION", bg=THEME["magenta"]))
            self.root.after(0, lambda: self.btn_stop.config(state='disabled'))

    def _recover_to_reels(self, d, package_name, reel_resource_id, clips_tab_resource_id):
        """Best-effort recovery: get back to the Reels feed if the app looks lost
        (e.g. stuck a couple of screens deep inside a profile). Presses back a
        few times first; if that doesn't work, force-restarts the app and
        re-opens the Reels tab."""
        def on_reels():
            return d(resourceId=reel_resource_id).exists or d(resourceId=clips_tab_resource_id).exists

        if on_reels():
            return True

        for _ in range(4):
            d.press("back")
            time.sleep(1.3)
            if on_reels():
                return True

        self.log("Navigation lost — restarting the app.", "warning")
        try:
            d.app_stop(package_name)
        except Exception:
            pass
        time.sleep(1.5)
        d.shell('monkey -p {} -c android.intent.category.LAUNCHER 1'.format(package_name))
        time.sleep(5)

        if d(resourceId=clips_tab_resource_id).exists:
            d(resourceId=clips_tab_resource_id).click()
        elif d(description="Reels").exists:
            d(description="Reels").click()
        elif d(text="Reels").exists:
            d(text="Reels").click()
        elif d(textContains="Reel").exists:
            d(textContains="Reel").click()
        time.sleep(3)
        return d(resourceId=reel_resource_id).exists

    def _dump_ui_for_debugging(self, tag):
        """Saves the current on-screen UI hierarchy (and a screenshot, if
        possible) so a broken selector can be diagnosed after the app's UI
        changes. Purely diagnostic — does not affect collection logic."""
        try:
            import uiautomator2 as _u2  # already imported at module scope; local ref for clarity
            d = _u2.connect()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.getcwd()
            dump_path = os.path.join(out_dir, f"ui_dump_{tag}_{ts}.xml")
            xml = d.dump_hierarchy()
            with open(dump_path, "w", encoding="utf-8") as f:
                f.write(xml)
            self.log(f"UI hierarchy saved: {dump_path}", "warning")
            try:
                shot_path = os.path.join(out_dir, f"ui_dump_{tag}_{ts}.png")
                d.screenshot(shot_path)
                self.log(f"Screenshot saved: {shot_path}", "warning")
            except Exception as shot_err:
                self.log(f"Could not save screenshot: {shot_err}", "warning")
        except Exception as e:
            self.log(f"Could not save UI dump: {e}", "warning")

    def _save_collected_pair(self, handle, account_url, video_url, email=""):
        """Save a collected pair to COLLECTED_PAIRS_FILE, avoiding duplicates."""
        existing = set()
        if os.path.exists(COLLECTED_PAIRS_FILE):
            with open(COLLECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row.get('Handle'), row.get('Account URL'), row.get('Video URL'))
                    existing.add(key)
        new_key = (handle, account_url, video_url)
        if new_key in existing:
            self.log(f"Already collected: {handle}", "warning")
            return
        with open(COLLECTED_PAIRS_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([handle, account_url, video_url, email])
        self.log(f"Collected: {handle}", "success")

    # ---------- Phase 2: Duplicate Check (unchanged) ----------
    def start_duplicate_check(self):
        if not os.path.exists(COLLECTED_PAIRS_FILE) or self.get_pairs_count() == 0:
            messagebox.showinfo("No pairs", "No collected pairs to check. Run auto‑collection first.")
            return
        self.set_ui_state(True)
        threading.Thread(target=self._run_duplicate_check_task, daemon=True).start()

    def _run_duplicate_check_task(self):
        self.log("Duplicate check started.", "info")
        # Load existing clean leads, blacklist, dupes cache
        existing_handles = set()
        for filepath in [CLEAN_LEADS_FILE, BLACKLIST_FILE, DUPLICATE_CACHE_FILE]:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    if filepath.endswith('.csv'):
                        reader = csv.DictReader(f)
                        for row in reader:
                            h = row.get('Handle')
                            if h:
                                existing_handles.add(h.strip().lower())
                    else:
                        for line in f:
                            h = line.strip()
                            if h:
                                existing_handles.add(h.lower() if h.startswith('@') else f"@{h}".lower())

        # Read collected pairs
        pairs = []
        with open(COLLECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pairs.append(row)

        if not pairs:
            self.log("No pairs to process.", "warning")
            self.root.after(0, lambda: self.set_ui_state(False))
            return

        # Pick Chrome profile
        try:
            profile = pick_chrome_profile()
            self.log(f"Using Chrome profile: {profile}", "info")
        except Exception as e:
            self.log(f"Profile selection error: {e}", "error")
            self.root.after(0, lambda: self.set_ui_state(False))
            return

        driver = None
        try:
            vt_url = "https://viraltasks.com/platform/leads/project/67de0467-441a-4846-bc0d-0b303fc1ed1b"
            driver = build_chrome_driver(profile, initial_url=vt_url)
            time.sleep(4)
            if "login" in driver.current_url.lower():
                self.log("Login required on ViralTasks — please log in and retry.", "error")
                return

            for row in pairs:
                if not self.is_running:
                    break
                handle = row.get('Handle', '').strip()
                account_url = row.get('Account URL', '').strip()
                video_url = row.get('Video URL', '').strip()
                email = row.get('Email', '').strip()

                if not handle or not account_url or not video_url:
                    self.log(f"Incomplete row skipped: {handle}", "warning")
                    self._remove_collected_pair(handle, account_url, video_url)
                    continue

                handle_lower = handle.lower()
                if handle_lower in existing_handles:
                    self.log(f"Already known: {handle}", "warning")
                    self._remove_collected_pair(handle, account_url, video_url)
                    continue

                self.log(f"Checking: {handle}", "info")
                fresh = vt_check_handle(driver, handle, timeout=14)
                if fresh is True:
                    self._save_clean_lead(handle, account_url, video_url, email)
                    existing_handles.add(handle_lower)
                    self.log(f"Fresh lead: {handle}", "success")
                    self._remove_collected_pair(handle, account_url, video_url)
                elif fresh is False:
                    with open(DUPLICATE_CACHE_FILE, 'a', encoding='utf-8') as f:
                        f.write(handle + "\n")
                    existing_handles.add(handle_lower)
                    self.log(f"Duplicate: {handle}", "warning")
                    self._remove_collected_pair(handle, account_url, video_url)
                else:
                    # Timeout/error – keep the pair for retry
                    self.log(f"Timed out checking {handle} — will retry later.", "warning")
                    # DO NOT remove the pair

                self.root.after(0, self.update_stats)
                time.sleep(random.uniform(2, 4))

            self.log("Duplicate check finished.", "success")
        except Exception as e:
            self.log(f"Duplicate check error: {e}", "error")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            self.root.after(0, lambda: self.set_ui_state(False))

    def _save_clean_lead(self, handle, account_url, video_url, email=""):
        existing = set()
        if os.path.exists(CLEAN_LEADS_FILE):
            with open(CLEAN_LEADS_FILE, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    h = row.get('Handle')
                    if h:
                        existing.add(h.strip().lower())
        if handle.lower() in existing:
            return
        with open(CLEAN_LEADS_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([handle, "", email, account_url, video_url, "pending"])

    def _remove_collected_pair(self, handle, account_url, video_url):
        if not os.path.exists(COLLECTED_PAIRS_FILE):
            return
        rows = []
        with open(COLLECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not (row.get('Handle') == handle and row.get('Account URL') == account_url and row.get('Video URL') == video_url):
                    rows.append(row)
        with open(COLLECTED_PAIRS_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["Handle", "Account URL", "Video URL", "Email"])
            writer.writeheader()
            writer.writerows(rows)

    # ---------- Vetting Console (unchanged) ----------
    def open_vetting_console(self):
        VettingWindow(self.root, self.log)


# ---- VettingWindow (unchanged) ----
class VettingWindow(tk.Toplevel):
    def __init__(self, parent, log_func):
        super().__init__(parent)
        self.title("AlgoMiner IG Vetting")
        self.geometry("300x560")
        self.configure(bg=THEME["bg"])
        self.attributes("-topmost", True)
        self.log_func = log_func
        self.leads = []
        self.driver = None
        self.success_count = 0
        self.is_processing = False
        self.load_leads()
        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        log_stats("START_VETTING", session_success=0, total_submitted=0)
        send_to_discord(f"🚀 **Vetting Session Started**\nQueue: `{len(self.leads)}`")

    def load_leads(self):
        if not os.path.exists(CLEAN_LEADS_FILE):
            return
        try:
            with open(CLEAN_LEADS_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('Handle') and row['Handle'] != 'Handle':
                        self.leads.append(row)
            self.log_func(f"Loaded {len(self.leads)} leads into the vetting queue.", "info")
        except Exception as e:
            self.log_func(f"Queue load error: {e}", "error")

    def save_leads(self):
        fieldnames = ['Handle', 'Followers', 'Email', 'Account URL', 'Video URL', 'Status']
        with open(CLEAN_LEADS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.leads)

    def setup_ui(self):
        header = tk.Canvas(self, width=320, height=46, highlightthickness=0, bg=THEME["bg"])
        header.pack(fill="x")
        draw_gradient(header, 320, 46, [THEME["purple"], THEME["magenta"], THEME["pink"], THEME["orange"]])
        header.create_text(160, 23, text="VETTING CONSOLE", font=("Segoe UI", 12, "bold"), fill="white")

        header_frame = tk.Frame(self, bg=THEME["card"], highlightbackground=THEME["card_border"], highlightthickness=1)
        header_frame.pack(fill="x", padx=8, pady=8)
        self.lbl_stats = tk.Label(header_frame, text=f"QUEUE: {len(self.leads)}", font=("Segoe UI", 11, "bold"), fg=THEME["success"], bg=THEME["card"])
        self.lbl_stats.pack(pady=8)

        info_frame = tk.LabelFrame(self, text=" CURRENT LEAD ", bg=THEME["card"], fg=THEME["pink"], font=("Segoe UI", 8, "bold"), bd=1)
        info_frame.pack(fill="x", padx=8, pady=5)
        self.lbl_current = tk.Label(info_frame, text="Press [S] to load", font=("Consolas", 8), wraplength=280, fg=THEME["text"], bg=THEME["card"], justify="left")
        self.lbl_current.pack(pady=8, padx=5)

        self.lbl_action = tk.Label(self, text="", fg=THEME["success"], font=("Segoe UI", 8, "bold"), bg=THEME["bg"])
        self.lbl_action.pack(pady=3)

        follower_frame = tk.Frame(self, bg=THEME["bg"])
        follower_frame.pack(fill="x", padx=8, pady=5)
        tk.Label(follower_frame, text="Followers:", fg=THEME["muted"], bg=THEME["bg"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.entry_followers = tk.Entry(follower_frame, font=("Consolas", 10), bg=THEME["card"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", highlightthickness=1, highlightbackground=THEME["card_border"])
        self.entry_followers.pack(fill="x", pady=4, ipady=4)

        email_frame = tk.Frame(self, bg=THEME["bg"])
        email_frame.pack(fill="x", padx=8, pady=5)
        tk.Label(email_frame, text="Email:", fg=THEME["muted"], bg=THEME["bg"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.entry_email = tk.Entry(email_frame, font=("Consolas", 10), bg=THEME["card"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", highlightthickness=1, highlightbackground=THEME["card_border"])
        self.entry_email.pack(fill="x", pady=4, ipady=4)

        btn_frame = tk.Frame(self, bg=THEME["bg"])
        btn_frame.pack(pady=8, fill="x", padx=8)

        b_start = tk.Button(btn_frame, text="[S] START", command=self.next_lead)
        style_button(b_start, THEME["purple"], "#7a4fe0")
        b_start.pack(pady=3, fill="x")

        b_submit = tk.Button(btn_frame, text="[Y] SUBMIT", command=self.submit_lead)
        style_button(b_submit, THEME["success"], "#57e79e", fg="#0a0a0a")
        b_submit.pack(pady=3, fill="x")

        b_next = tk.Button(btn_frame, text="[N] NEXT", command=self.skip_lead)
        style_button(b_next, THEME["orange"], THEME["yellow"], fg="#1a1a1a")
        b_next.pack(pady=3, fill="x")

        b_ban = tk.Button(btn_frame, text="[B] BANNED", command=self.ban_lead)
        style_button(b_ban, THEME["red"], "#ff6b78")
        b_ban.pack(pady=3, fill="x")

        b_close = tk.Button(btn_frame, text="CLOSE", command=self.close_window)
        style_button(b_close, "#2a1010", "#3a1616", fg=THEME["red"])
        b_close.pack(pady=3, fill="x")

        self.bind('y', lambda e: self.handle_hotkey('y'))
        self.bind('n', lambda e: self.handle_hotkey('n'))
        self.bind('b', lambda e: self.handle_hotkey('b'))
        self.bind('s', lambda e: self.handle_hotkey('s'))

    def handle_hotkey(self, key_type):
        focused = self.focus_get()
        if isinstance(focused, tk.Entry):
            return
        if key_type == 'y':
            self.submit_lead()
        elif key_type == 'n':
            self.skip_lead()
        elif key_type == 'b':
            self.ban_lead()
        elif key_type == 's':
            self.next_lead()

    def init_driver(self):
        if not CHROME_PATH:
            messagebox.showerror("Error", "Google Chrome not found.\nCheck CHROME_PATH in config.py")
            return False

        if self.driver is not None:
            try:
                self.driver.current_url
                return True
            except:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None

        try:
            profile = pick_chrome_profile()
            self.lbl_action.config(text=f"Launching Chrome profile '{profile}'...", fg=THEME["success"])
            kill_chrome_and_release_locks()
            time.sleep(0.5)
            vt_url = "https://viraltasks.com/platform/leads/project/67de0467-441a-4846-bc0d-0b303fc1ed1b"
            self.driver = build_chrome_driver(profile, initial_url=vt_url)
            time.sleep(4)
            current_url = self.driver.current_url
            if "login" in current_url.lower():
                messagebox.showwarning("Login Required", 
                    "Please log in to ViralTasks in the Chrome window.\n"
                    "After logging in, press START again to continue vetting.")
                self.lbl_action.config(text="Login required – please log in", fg=THEME["warning"])
                return False
            self.lbl_action.config(text="Browser ready — logged in", fg=THEME["success"])
            return True
        except Exception as e:
            error_msg = f"Driver initialisation failed:\n{str(e)}"
            self.lbl_action.config(text=f"Error: {str(e)[:60]}", fg=THEME["error"])
            messagebox.showerror("Vetting Console Error", error_msg)
            return False

    def take_screenshot(self, label="Manual"):
        if self.driver:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ss_{label}_{timestamp}.png"
                path = os.path.join(SCREENSHOT_DIR, filename)
                self.driver.save_screenshot(path)
                send_to_discord(f"📸 **Screenshot: {label}**", path)
            except Exception as e:
                print(f"[!] Screenshot failed: {e}")

    def next_lead(self):
        if not self.leads:
            self.lbl_current.config(text="ALL DONE!", fg=THEME["success"])
            return
        lead = self.leads[0]
        email_text = f"\nEmail: {lead.get('Email', '')}" if lead.get('Email', '').strip() else ""
        self.lbl_current.config(text=f"Handle: {lead.get('Handle', 'Unknown')}\nAccount: {lead.get('Account URL', '')}\nVideo: {lead.get('Video URL', '')}{email_text}", fg=THEME["text"])
        self.lbl_action.config(text="Ready for vetting", fg=THEME["success"])
        self.lbl_stats.config(text=f"QUEUE: {len(self.leads)}")
        self.entry_followers.delete(0, tk.END)
        self.entry_email.delete(0, tk.END)
        self.entry_email.insert(0, lead.get('Email', ''))
        if self.init_driver():
            try:
                account_url = lead.get('Account URL', '')
                if account_url:
                    self.driver.get(account_url)
                    time.sleep(4)
            except Exception as e:
                self.lbl_action.config(text=f"Preview error: {e}", fg=THEME["error"])

    def submit_lead(self):
        if not self.leads or self.is_processing:
            return
        followers_text = self.entry_followers.get().strip()
        if not followers_text.isdigit():
            messagebox.showwarning("Followers", "Enter a numeric follower count before submitting.")
            return
        email_text = self.entry_email.get().strip()
        self.is_processing = True
        lead = self.leads[0]
        lead['Followers'] = followers_text
        lead['Email'] = email_text
        try:
            if not self.init_driver():
                return
            success = self.perform_viral_submission(lead)
            if success:
                self.success_count += 1
                with open(SUBMITTED_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([lead['Handle'], "Success", datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                self.leads.pop(0)
                self.save_leads()
                self.lbl_stats.config(text=f"QUEUE: {len(self.leads)}")
                self.lbl_action.config(text="Submitted!", fg=THEME["success"])
                self.entry_followers.delete(0, tk.END)
                self.entry_email.delete(0, tk.END)
                self.next_lead()
            else:
                self.lbl_action.config(text="Submission failed", fg=THEME["error"])
        except Exception as e:
            self.log_func(f"Submit error: {e}", "error")
        finally:
            self.is_processing = False

    def skip_lead(self):
        if not self.leads:
            return
        self.leads.pop(0)
        self.save_leads()
        self.lbl_stats.config(text=f"QUEUE: {len(self.leads)}")
        self.lbl_action.config(text="Skipped", fg=THEME["warning"])
        self.entry_followers.delete(0, tk.END)
        self.entry_email.delete(0, tk.END)
        self.next_lead()

    def ban_lead(self):
        if not self.leads:
            return
        lead = self.leads.pop(0)
        try:
            with open(BLACKLIST_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{lead['Handle']}\n")
            with open(DUPLICATE_CACHE_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{lead['Handle']}\n")
        except Exception as e:
            self.log_func(f"Blacklist error: {e}", "error")
        self.save_leads()
        self.lbl_stats.config(text=f"QUEUE: {len(self.leads)}")
        self.lbl_action.config(text="Banned", fg=THEME["error"])
        self.entry_followers.delete(0, tk.END)
        self.entry_email.delete(0, tk.END)
        self.next_lead()

    def wait_for_element(self, xpath, timeout=10):
        wait = WebDriverWait(self.driver, timeout)
        return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))

    def perform_viral_submission(self, lead):
        try:
            self.driver.execute_script("window.open('https://viraltasks.com/platform/leads/project/67de0467-441a-4846-bc0d-0b303fc1ed1b', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            time.sleep(3)
            if "login" in self.driver.current_url.lower():
                self.lbl_action.config(text="Login required on ViralTasks", fg=THEME["error"])
                return False

            if not select_instagram_platform(self.driver, timeout=10):
                try:
                    select_el = self.driver.find_element(By.XPATH, "//select")
                    Select(select_el).select_by_visible_text("Instagram")
                except:
                    pass

            handle_box = self.wait_for_element("//input[@type='text']", timeout=12)
            handle_box.clear()
            handle_box.send_keys(lead['Handle'])
            time.sleep(0.5)
            try:
                check_btn = self.wait_for_element("//button[contains(., 'Check') or contains(., 'Verify')]")
                check_btn.click()
            except Exception:
                pass
            time.sleep(2)
            fields = [
                {"val": lead['Account URL'], "xp": "//input[contains(@placeholder, 'Account')] | //label[contains(., 'Account')]/..//input"},
                {"val": lead['Video URL'], "xp": "//input[contains(@placeholder, 'Video')] | //label[contains(., 'Video')]/..//input"},
                {"val": str(lead['Followers']), "xp": "//input[contains(@placeholder, 'Follower')] | //label[contains(., 'Follower')]/..//input | //input[contains(@placeholder, 'Subscribers')]"},
                {"val": lead.get('Email', ''), "xp": "//input[contains(@placeholder, 'Email')] | //label[contains(., 'Email')]/..//input | //input[@type='email']"}
            ]
            for field in fields:
                try:
                    el = self.wait_for_element(field['xp'], timeout=10)
                    el.clear()
                    el.send_keys(field['val'])
                    time.sleep(0.5)
                except Exception as fe:
                    self.log_func(f"Field fill error: {fe}", "warning")
            submit_btn = self.wait_for_element("//button[contains(., 'Submit')]")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            time.sleep(0.5)
            for attempt in range(3):
                try:
                    submit_btn.click()
                    break
                except Exception:
                    time.sleep(1)
                    submit_btn = self.wait_for_element("//button[contains(., 'Submit')]")
            time.sleep(3)
            self.driver.close()
            if self.driver.window_handles:
                self.driver.switch_to.window(self.driver.window_handles[0])
            return True
        except Exception as e:
            self.log_func(f"Submission error: {e}", "error")
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except:
                pass
            return False

    def close_window(self):
        try:
            if self.driver:
                self.driver.get("https://www.viraltasks.com/platform/leads")
                time.sleep(3)
        except:
            pass
        self.take_screenshot("SessionStop")
        log_stats("STOP_VETTING", session_success=self.success_count, total_submitted=self.success_count)
        send_to_discord(f"🛑 **Vetting Session Stopped**\nSuccessful Submissions: `{self.success_count}`\nRemaining Queue: `{len(self.leads)}`")
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.destroy()


# ---- Main ----
def main():
    root = tk.Tk()
    app = MainLauncherPro(root)
    root.mainloop()

if __name__ == "__main__":
    main()