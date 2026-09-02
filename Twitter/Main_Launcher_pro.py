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

try:
    import pyfiglet
except ImportError:
    pyfiglet = None

from adb_bundle import ensure_adb_available

ensure_adb_available()

# ---- Banner ----
def print_banner():
    G = "\033[92m"
    DG = "\033[32m"
    W = "\033[97m"
    Y = "\033[93m"
    C = "\033[96m"
    R = "\033[91m"
    X = "\033[0m"

    if pyfiglet is not None:
        try:
            lines = pyfiglet.figlet_format("Twitter", font="slant").splitlines()
        except Exception:
            lines = ["TWITTER"]
    else:
        lines = ["TWITTER"]

    print(DG + "#" * 74 + X)
    print("\n".join([G + line + X for line in lines]))
    print(DG + "#" * 74 + X)
    print(f"  {R}!! SYS{X}  {W}TWITTER LEAD SCOUTER PRO{X:<40}{Y}v1.0.0{X}")
    print(f"  {C}>> MODE{X}  {W}AUTO COLLECTION | VETTING{X}")
    print(f"  {C}>> TGTS{X}  {W}x.com (Twitter video leads){X}")
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
# ---- UI Theme (Twitter/X-inspired dark palette) ----
# =========================================================================
THEME = {
    "bg":          "#000000",
    "bg_alt":      "#0a0a0a",
    "card":        "#16181c",
    "card_border": "#2f3336",
    "text":        "#e7e9ea",
    "muted":       "#71767b",
    "purple":      "#1d9bf0",
    "blue":        "#1d9bf0",
    "light_blue":  "#8ecdf8",
    "pink":        "#f91880",
    "red":         "#f4212e",
    "orange":      "#ff7a00",
    "yellow":      "#ffd400",
    "success":     "#00ba7c",
    "warning":     "#ffd400",
    "error":       "#f4212e",
    "info":        "#e7e9ea",
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

# ---- Regex helpers ----
_TWITTER_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)(?:[/?].*)?$",
    re.IGNORECASE,
)
_TWITTER_RESERVED = {
    "home", "search", "explore", "notifications", "messages", "compose",
    "settings", "privacy", "tos", "about", "help", "support", "jobs",
    "privacy", "terms", "downloads", "share", "hashtag", "i",
    "login", "signup", "account", "media", "topics", "lists",
}

def extract_handle_from_url(profile_url: str) -> str:
    """Extract @handle from Twitter/X profile URL, or return None if invalid."""
    m = _TWITTER_URL_RE.search(profile_url)
    if m:
        username = m.group(1).lower()
        if username not in _TWITTER_RESERVED and not username.startswith("i/"):
            return f"@{username}"
    return None

# ---- Chrome driver helpers ----
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
    picker = tk.Tk()
    picker.title("Choose Chrome Profile")
    picker.configure(bg=THEME["bg"])
    picker.resizable(False, False)
    picker.attributes("-topmost", True)

    tk.Label(
        picker,
        text="Select the Chrome profile logged into ViralTasks:",
        font=("Segoe UI", 9, "bold"), fg=THEME["blue"], bg=THEME["bg"],
        padx=14, pady=10,
    ).pack()

    listbox = tk.Listbox(
        picker,
        font=("Consolas", 9), bg=THEME["card"], fg=THEME["text"],
        selectbackground=THEME["blue"], selectforeground="#ffffff",
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
    style_button(btn, THEME["blue"], THEME["light_blue"])
    btn.pack(pady=(0, 14), padx=14, fill="x")

    picker.eval("tk::PlaceWindow . center")
    picker.mainloop()
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

# ---- ViralTasks platform selection for Twitter ----
def select_twitter_platform(driver, timeout=10):
    """
    Selects 'Twitter' from the platform dropdown on ViralTasks.
    """
    try:
        wait = WebDriverWait(driver, timeout)
        select_elements = driver.find_elements(By.XPATH, "//select")
        if select_elements:
            select_obj = Select(select_elements[0])
            for opt in select_obj.options:
                if "twitter" in opt.text.lower() or "x.com" in opt.text.lower():
                    select_obj.select_by_visible_text(opt.text.strip())
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", select_elements[0])
                    return True
            select_obj.select_by_visible_text("Twitter")
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", select_elements[0])
            return True
        else:
            label = driver.find_element(By.XPATH, "//*[contains(text(),'Social Media') or contains(text(),'Platform')]")
            container = label.find_element(By.XPATH, "./ancestor::div[1]")
            toggle = container.find_element(By.XPATH, ".//div[@role='button' or contains(@class, 'dropdown') or contains(@class, 'select')]")
            toggle.click()
            time.sleep(0.5)
            option = driver.find_element(By.XPATH, "//*[contains(text(),'Twitter') or contains(text(),'X')]")
            option.click()
            return True
    except Exception as e:
        print(f"[!] Platform selection error: {e}")
        return False

# ---- Twitter ID Lookup via ilo.so ----
def lookup_twitter_id(driver, handle: str, timeout: int = 20) -> str | None:
    """
    Look up the permanent Twitter user ID for a given handle using ilo.so/twitter-id.
    Returns the ID string or None on failure.
    """
    try:
        clean_handle = handle.lstrip("@").strip()
        url = f"https://ilo.so/twitter-id?handle={clean_handle}"
        driver.get(url)
        time.sleep(4)

        # Look for the ID field — ilo.so displays it in a copy-ready field
        wait = WebDriverWait(driver, timeout)

        # Try to find the numerical ID on the page
        # ilo.so shows the ID in a prominent field
        id_elements = driver.find_elements(By.XPATH, "//input[@readonly or @value]")
        for el in id_elements:
            val = el.get_attribute("value") or ""
            if val.strip().isdigit() and len(val.strip()) > 3:
                return val.strip()

        # Fallback: search the page source for the ID pattern
        page_text = driver.page_source
        # Look for "User ID" label followed by a number
        id_match = re.search(r'(?:User\s*ID|user_id)["\s:]+(\d{5,})', page_text, re.IGNORECASE)
        if id_match:
            return id_match.group(1)

        # Another fallback: look for large numbers that could be Snowflake IDs
        num_match = re.search(r'\b(\d{10,})\b', page_text)
        if num_match:
            return num_match.group(1)

        return None
    except Exception as e:
        print(f"[!] Twitter ID lookup error: {e}")
        return None

# ---- ViralTasks duplicate check ----
def vt_check_twitter_id(driver, twitter_id: str, timeout: int = 14):
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

        # Select Twitter platform
        select_twitter_platform(driver, timeout=10)

        # Enter Twitter ID
        inp = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='text']")))
        inp.clear()
        inp.send_keys(twitter_id)
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
            if "already exists" in src or "duplicate values" in src:
                return False  # DUPE
            time.sleep(0.4)
        return None  # Timed out
    except Exception as e:
        print(f"[VT CHECK ERROR] {e}")
        return None

# =========================================================================
# ---- Main Application ----
# =========================================================================
class MainLauncherPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitter Lead Scouter Pro")
        self.root.geometry("480x720")
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
        for f, header in [
            (CLEAN_LEADS_FILE, ["Handle", "Twitter ID", "Followers", "Email", "Account URL", "Video URL", "Status"]),
            (SUBMITTED_FILE, ["Handle", "Twitter ID", "Status", "Timestamp"]),
            (COLLECTED_PAIRS_FILE, ["Handle", "Twitter ID", "Account URL", "Video URL", "Email"])
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
        # --- Gradient header banner (X/Twitter style) ---
        header = tk.Canvas(self.root, width=480, height=64, highlightthickness=0, bg=THEME["bg"])
        header.pack(fill="x")
        draw_gradient(header, 480, 64, [THEME["blue"], "#1a8cd8", THEME["light_blue"], THEME["blue"]])
        header.create_text(240, 23, text="TWITTER LEAD SCOUTER", font=("Segoe UI", 16, "bold"), fill="white")
        header.create_text(240, 45, text="PRO  ·  AUTOMATED LEAD PIPELINE", font=("Segoe UI", 8, "bold"), fill="#cce8ff")

        # --- Stats card ---
        stats_frame = tk.Frame(self.root, bg=THEME["card"], highlightbackground=THEME["card_border"], highlightthickness=1)
        stats_frame.pack(fill="x", padx=14, pady=(14, 8))

        def stat_block(row, col, color, title):
            cell = tk.Frame(stats_frame, bg=THEME["card"])
            cell.grid(row=row, column=col, sticky="w", padx=16, pady=10)
            dot = tk.Canvas(cell, width=9, height=9, bg=THEME["card"], highlightthickness=0)
            dot.create_oval(0, 0, 9, 9, fill=color, outline="")
            dot.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8))
            tk.Label(cell, text=title, font=("Segoe UI", 8), fg=THEME["muted"], bg=THEME["card"]).grid(row=0, column=1, sticky="w")
            value_lbl = tk.Label(cell, text="0", font=("Segoe UI", 13, "bold"), fg=THEME["text"], bg=THEME["card"])
            value_lbl.grid(row=1, column=1, sticky="w")
            return value_lbl

        self.lbl_pairs = stat_block(0, 0, THEME["blue"], "COLLECTED PAIRS")
        self.lbl_clean = stat_block(0, 1, THEME["yellow"], "CLEAN LEADS")
        self.lbl_submitted = stat_block(1, 0, THEME["success"], "TOTAL SUBMITTED")
        self.lbl_dupe = stat_block(1, 1, THEME["muted"], "DUPLICATES CACHED")

        # --- Action buttons ---
        btn_frame = tk.Frame(self.root, bg=THEME["bg"])
        btn_frame.pack(fill="x", padx=14, pady=(4, 4))

        self.btn_collect = tk.Button(btn_frame, text="🐦  START AUTO COLLECTION", command=self.toggle_auto_collect)
        style_button(self.btn_collect, THEME["blue"], THEME["light_blue"])
        self.btn_collect.pack(fill="x", pady=(0, 8))

        self.btn_twitter_id = tk.Button(btn_frame, text="🔗  LOOKUP TWITTER IDs  ·  PHASE 1.5", command=self.start_twitter_id_lookup)
        style_button(self.btn_twitter_id, "#536471", "#6e7b85")
        self.btn_twitter_id.pack(fill="x", pady=(0, 8))

        self.btn_check = tk.Button(btn_frame, text="🔍  CHECK DUPLICATES  ·  PHASE 2", command=self.start_duplicate_check)
        style_button(self.btn_check, "#1d9bf0", "#1a8cd8")
        self.btn_check.pack(fill="x", pady=(0, 8))

        self.btn_vet = tk.Button(btn_frame, text="👁  OPEN VETTING CONSOLE", command=self.open_vetting_console)
        style_button(self.btn_vet, THEME["orange"], "#ff9e44", fg="#1a1a1a")
        self.btn_vet.pack(fill="x", pady=(0, 8))

        self.btn_stop = tk.Button(self.root, text="⏹  STOP CURRENT TASK", state='disabled', command=self.stop_current_task)
        style_button(self.btn_stop, THEME["red"], "#ff5c5c")
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
        self.btn_collect.config(text="🐦  START AUTO COLLECTION", bg=THEME["blue"])

    def set_ui_state(self, active):
        state = 'disabled' if active else 'normal'
        self.btn_collect.config(state='normal' if not self.auto_collect_active else 'disabled')
        self.btn_check.config(state=state)
        self.btn_twitter_id.config(state=state)
        self.btn_vet.config(state='normal')
        self.is_running = active
        self.btn_stop.config(state='normal' if active else 'disabled')

    # ===============================================================
    # Phase 1: Auto Collection (uiautomator2 — Twitter/X Android)
    # ===============================================================
    def toggle_auto_collect(self):
        if self.auto_collect_active:
            self.auto_collect_active = False
            self.btn_collect.config(text="🐦  START AUTO COLLECTION", bg=THEME["blue"])
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
        """
        Twitter auto-collection flow (selectors from UI dumps):
        1. User must already have a video tweet open in the Twitter video player.
        2. Tool extracts the author's @handle from the video player overlay.
        3. Tool clicks Share → Copy link to get the video/tweet URL.
        4. Constructs profile URL from the handle.
        5. Scrolls to the next video and repeats.

        EXACT SELECTORS FROM DUMPS:
        - Video player container: resource-id="VideoTab"
        - Share button: content-desc="Share" (bounds [604,1231][694,1352])
        - Author avatar: content-desc="{AuthorName}" (clickable, goes to profile)
        - Author handle: text="@handle" (e.g. text="@MarioNawfal")
        - Copy link in share sheet: text="Copy link" (bounds [151,1320][286,1451])
        - Back button: content-desc="Back" (bounds [31,74][121,164])
        - Profile page: resource-id="UserProfileScreen"
        """
        MAX_VIDEOS = 20
        TWITTER_PACKAGE = "com.twitter.android"

        try:
            d = u2.connect()
            self.log(f"Connected to device: {d.info['productName']}", "success")

            try:
                if hasattr(d, 'app_current'):
                    d.app_current()
                self.log("Device automation session initialized.", "info")
            except Exception as init_error:
                self.log(f"Automation session warning: {init_error}", "warning")

            # Enable IME for clipboard access
            d.set_fastinput_ime()

            # Check if Twitter is running
            current = d.app_current()
            if current and TWITTER_PACKAGE not in (current.get("package", "") if isinstance(current, dict) else str(current)):
                self.log("Opening Twitter app...", "info")
                d.shell(f'monkey -p {TWITTER_PACKAGE} -c android.intent.category.LAUNCHER 1')
                time.sleep(5)

            self.log("Looking for video content...", "info")
            time.sleep(3)

            collected = 0
            for i in range(MAX_VIDEOS):
                if not self.is_running:
                    self.log("Auto-collection interrupted by user.", "warning")
                    break

                self.log(f"Video {i+1}/{MAX_VIDEOS} — collecting...", "info")
                time.sleep(1)

                # --- Step 1: Extract author @handle from video player overlay ---
                # From dump: author handle appears as text="@handle" (e.g. text="@MarioNawfal")
                handle = None
                width, height = d.window_size()

                # Wait up to 5 seconds for the @handle to appear (video may still be loading)
                for wait_attempt in range(10):
                    xml = d.dump_hierarchy()
                    matches = re.findall(r'text="(@[A-Za-z0-9_]+)"', xml)
                    if matches:
                        handle = matches[0]
                        self.log(f"  Found handle: {handle}", "info")
                        break
                    time.sleep(0.5)

                if not handle:
                    self.log(f"  Video {i+1}: could not find author handle — skipped.", "warning")
                    if i < MAX_VIDEOS - 1:
                        d.swipe(int(width * 0.5), int(height * 0.75), int(width * 0.5), int(height * 0.25), duration=0.3)
                        time.sleep(3)
                    continue

                # Construct profile URL from handle
                clean_handle = handle.lstrip("@")
                profile_url = f"https://x.com/{clean_handle}"
                self.log(f"  Profile URL: {profile_url}", "info")

                # --- Step 2: Get Video/Tweet URL via Share → Copy link ---
                video_url = None
                width, height = d.window_size()

                # Click the Share button on the video player
                # From dump: content-desc="Share" at bounds [604,1231][694,1352]
                share_btn = d(description="Share")
                if share_btn.exists:
                    share_btn.click()
                    self.log("  Clicked Share button", "info")
                else:
                    # Fallback: click the known bounds area
                    d.click(649, 1291)
                    self.log("  Clicked Share (bounds fallback)", "info")
                time.sleep(2)

                # Find and click "Copy link" in the share sheet
                # From dump: text="Copy link" at bounds [151,1320][286,1451]
                copy_link = None
                for attempt in range(15):
                    if d(text="Copy link").exists:
                        copy_link = d(text="Copy link")
                        break
                    time.sleep(0.5)

                if copy_link:
                    copy_link.click()
                    self.log("  Clicked Copy link", "info")
                    time.sleep(1.5)
                    video_url = d.clipboard
                    if video_url and ("x.com" in video_url or "twitter.com" in video_url):
                        self.log(f"  Video URL: {video_url}", "info")
                    else:
                        video_url = None
                        self.log(f"  Clipboard did not contain a valid URL", "warning")
                else:
                    self.log(f"  Could not find 'Copy link' button — retrying with scroll", "warning")
                    # Try scrolling the share sheet down to reveal Copy link
                    d.swipe(int(width * 0.5), int(height * 0.9), int(width * 0.5), int(height * 0.6), duration=0.3)
                    time.sleep(1)
                    copy_link2 = d(text="Copy link")
                    if copy_link2.exists:
                        copy_link2.click()
                        self.log("  Clicked Copy link (after scroll)", "info")
                        time.sleep(1.5)
                        video_url = d.clipboard
                        if video_url and ("x.com" in video_url or "twitter.com" in video_url):
                            self.log(f"  Video URL: {video_url}", "info")
                        else:
                            video_url = None
                    else:
                        d.press("back")
                        time.sleep(0.5)

                # Close share sheet WITHOUT pressing back (back exits video player)
                # From dump: content-desc="Close sheet" at bounds [0,0][720,336]
                close_sheet = d(description="Close sheet")
                if close_sheet.exists:
                    close_sheet.click()
                    self.log("  Dismissed share sheet", "info")
                    time.sleep(0.5)
                else:
                    # Tap the dark area above the share sheet to dismiss it
                    # The share sheet starts around y=1320, so tap above it
                    d.click(int(width * 0.5), int(height * 0.3))
                    self.log("  Tapped above share sheet to dismiss", "info")
                    time.sleep(0.5)

                # --- Step 3: Save the pair ---
                if handle and profile_url and video_url:
                    self._save_collected_pair(handle, "", profile_url, video_url, "")
                    collected += 1
                    self.root.after(0, self.update_stats)
                    self.log(f"  ✓ Collected: {handle}", "success")
                else:
                    missing = []
                    if not handle:
                        missing.append("handle")
                    if not video_url:
                        missing.append("video URL")
                    self.log(f"  Video {i+1}: missing {', '.join(missing)} — skipped.", "warning")

                # --- Step 4: Scroll to next video ---
                if i < MAX_VIDEOS - 1:
                    # Swipe up to go to next video
                    d.swipe(int(width * 0.5), int(height * 0.75), int(width * 0.5), int(height * 0.25), duration=0.3)
                    time.sleep(2)
                    # Tap screen to bring back overlay buttons (Share, @handle, etc.)
                    d.click(int(width * 0.5), int(height * 0.5))
                    time.sleep(1.5)

            self.log(f"Auto-collection finished — {collected} pairs collected.", "success")
            self.auto_collect_active = False
            self.root.after(0, lambda: self.btn_collect.config(text="🐦  START AUTO COLLECTION", bg=THEME["blue"]))
            self.root.after(0, lambda: self.btn_stop.config(state='disabled'))

        except Exception as e:
            self.log(f"Auto-collection error: {e}", "error")
            self.auto_collect_active = False
            self.root.after(0, lambda: self.btn_collect.config(text="🐦  START AUTO COLLECTION", bg=THEME["blue"]))
            self.root.after(0, lambda: self.btn_stop.config(state='disabled'))

    def _save_collected_pair(self, handle, twitter_id, account_url, video_url, email=""):
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
            writer.writerow([handle, twitter_id, account_url, video_url, email])
        self.log(f"Collected: {handle}", "success")

    # ===============================================================
    # Phase 1.5: Twitter ID Lookup
    # ===============================================================
    def start_twitter_id_lookup(self):
        """Look up Twitter IDs for all collected pairs that don't have one yet."""
        if not os.path.exists(COLLECTED_PAIRS_FILE) or self.get_pairs_count() == 0:
            messagebox.showinfo("No pairs", "No collected pairs to look up. Run auto-collection first.")
            return
        self.set_ui_state(True)
        threading.Thread(target=self._run_twitter_id_lookup, daemon=True).start()

    def _run_twitter_id_lookup(self):
        self.log("Twitter ID lookup started.", "info")

        # Read collected pairs
        rows = []
        with open(COLLECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            self.log("No pairs to process.", "warning")
            self.root.after(0, lambda: self.set_ui_state(False))
            return

        # Check which ones need ID lookup
        needs_lookup = [r for r in rows if not r.get('Twitter ID', '').strip()]
        if not needs_lookup:
            self.log("All pairs already have Twitter IDs.", "success")
            self.root.after(0, lambda: self.set_ui_state(False))
            return

        self.log(f"{len(needs_lookup)} pairs need Twitter ID lookup.", "info")

        driver = None
        try:
            profile = pick_chrome_profile()
            self.log(f"Using Chrome profile: {profile}", "info")

            driver = build_chrome_driver(profile)
            time.sleep(3)

            updated_count = 0
            for row in needs_lookup:
                if not self.is_running:
                    break

                handle = row.get('Handle', '').strip()
                if not handle:
                    continue

                self.log(f"Looking up ID for {handle}...", "info")
                twitter_id = lookup_twitter_id(driver, handle, timeout=20)

                if twitter_id:
                    row['Twitter ID'] = twitter_id
                    updated_count += 1
                    self.log(f"  {handle} → ID: {twitter_id}", "success")
                else:
                    self.log(f"  Failed to look up ID for {handle}", "warning")

                self.root.after(0, self.update_stats)
                time.sleep(random.uniform(2, 4))

            # Write back all rows with updated IDs
            if updated_count > 0:
                fieldnames = ["Handle", "Twitter ID", "Account URL", "Video URL", "Email"]
                with open(COLLECTED_PAIRS_FILE, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({k: row.get(k, '') for k in fieldnames})

            self.log(f"Twitter ID lookup finished — {updated_count} IDs found.", "success")

        except Exception as e:
            self.log(f"Twitter ID lookup error: {e}", "error")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            self.root.after(0, lambda: self.set_ui_state(False))

    # ===============================================================
    # Phase 2: Duplicate Check
    # ===============================================================
    def start_duplicate_check(self):
        if not os.path.exists(COLLECTED_PAIRS_FILE) or self.get_pairs_count() == 0:
            messagebox.showinfo("No pairs", "No collected pairs to check. Run auto-collection first.")
            return
        self.set_ui_state(True)
        threading.Thread(target=self._run_duplicate_check_task, daemon=True).start()

    def _run_duplicate_check_task(self):
        self.log("Duplicate check started.", "info")

        # Check if Twitter IDs are available
        pairs = []
        with open(COLLECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pairs.append(row)

        if not pairs:
            self.log("No pairs to process.", "warning")
            self.root.after(0, lambda: self.set_ui_state(False))
            return

        # Check for missing Twitter IDs
        missing_ids = [p for p in pairs if not p.get('Twitter ID', '').strip()]
        if missing_ids:
            self.log(f"WARNING: {len(missing_ids)} pairs are missing Twitter IDs. Run Phase 1.5 (Twitter ID Lookup) first.", "warning")
            self.root.after(0, lambda: self.set_ui_state(False))
            return

        # Load existing clean leads, blacklist, dupes cache
        existing_ids = set()
        for filepath in [CLEAN_LEADS_FILE, BLACKLIST_FILE, DUPLICATE_CACHE_FILE]:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    if filepath.endswith('.csv'):
                        reader = csv.DictReader(f)
                        for row in reader:
                            tid = row.get('Twitter ID')
                            if tid:
                                existing_ids.add(tid.strip())
                    else:
                        for line in f:
                            tid = line.strip()
                            if tid:
                                existing_ids.add(tid)

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
                twitter_id = row.get('Twitter ID', '').strip()
                account_url = row.get('Account URL', '').strip()
                video_url = row.get('Video URL', '').strip()
                email = row.get('Email', '').strip()

                if not handle or not twitter_id or not account_url or not video_url:
                    self.log(f"Incomplete row skipped: {handle}", "warning")
                    self._remove_collected_pair(handle, account_url, video_url)
                    continue

                if twitter_id in existing_ids:
                    self.log(f"Already known (ID: {twitter_id}): {handle}", "warning")
                    self._remove_collected_pair(handle, account_url, video_url)
                    continue

                self.log(f"Checking: {handle} (ID: {twitter_id})", "info")
                fresh = vt_check_twitter_id(driver, twitter_id, timeout=14)
                if fresh is True:
                    self._save_clean_lead(handle, twitter_id, account_url, video_url, email)
                    existing_ids.add(twitter_id)
                    self.log(f"Fresh lead: {handle}", "success")
                    self._remove_collected_pair(handle, account_url, video_url)
                elif fresh is False:
                    with open(DUPLICATE_CACHE_FILE, 'a', encoding='utf-8') as f:
                        f.write(twitter_id + "\n")
                    existing_ids.add(twitter_id)
                    self.log(f"Duplicate: {handle}", "warning")
                    self._remove_collected_pair(handle, account_url, video_url)
                else:
                    self.log(f"Timed out checking {handle} — will retry later.", "warning")

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

    def _save_clean_lead(self, handle, twitter_id, account_url, video_url, email=""):
        existing = set()
        if os.path.exists(CLEAN_LEADS_FILE):
            with open(CLEAN_LEADS_FILE, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    tid = row.get('Twitter ID')
                    if tid:
                        existing.add(tid.strip())
        if twitter_id in existing:
            return
        with open(CLEAN_LEADS_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([handle, twitter_id, "", email, account_url, video_url, "pending"])

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
            writer = csv.DictWriter(f, fieldnames=["Handle", "Twitter ID", "Account URL", "Video URL", "Email"])
            writer.writeheader()
            writer.writerows(rows)

    # ===============================================================
    # Phase 3: Vetting Console
    # ===============================================================
    def open_vetting_console(self):
        VettingWindow(self.root, self.log)


# =========================================================================
# ---- VettingWindow ----
# =========================================================================
class VettingWindow(tk.Toplevel):
    def __init__(self, parent, log_func):
        super().__init__(parent)
        self.title("Twitter Lead Vetting")
        self.geometry("340x720")
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
        send_to_discord(f"🚀 **Twitter Vetting Session Started**\nQueue: `{len(self.leads)}`")

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
        fieldnames = ['Handle', 'Twitter ID', 'Followers', 'Email', 'Account URL', 'Video URL', 'Status']
        with open(CLEAN_LEADS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.leads)

    def setup_ui(self):
        header = tk.Canvas(self, width=340, height=46, highlightthickness=0, bg=THEME["bg"])
        header.pack(fill="x")
        draw_gradient(header, 340, 46, [THEME["blue"], "#1a8cd8", THEME["light_blue"], THEME["blue"]])
        header.create_text(170, 23, text="TWITTER VETTING", font=("Segoe UI", 12, "bold"), fill="white")

        header_frame = tk.Frame(self, bg=THEME["card"], highlightbackground=THEME["card_border"], highlightthickness=1)
        header_frame.pack(fill="x", padx=8, pady=8)
        self.lbl_stats = tk.Label(header_frame, text=f"QUEUE: {len(self.leads)}", font=("Segoe UI", 11, "bold"), fg=THEME["success"], bg=THEME["card"])
        self.lbl_stats.pack(pady=8)

        info_frame = tk.LabelFrame(self, text=" CURRENT LEAD ", bg=THEME["card"], fg=THEME["blue"], font=("Segoe UI", 8, "bold"), bd=1)
        info_frame.pack(fill="x", padx=8, pady=5)
        self.lbl_current = tk.Label(info_frame, text="Press [S] to load", font=("Consolas", 8), wraplength=300, fg=THEME["text"], bg=THEME["card"], justify="left")
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
        style_button(b_start, THEME["blue"], THEME["light_blue"])
        b_start.pack(pady=3, fill="x")

        b_submit = tk.Button(btn_frame, text="[Y] SUBMIT", command=self.submit_lead)
        style_button(b_submit, THEME["success"], "#2dc980", fg="#0a0a0a")
        b_submit.pack(pady=3, fill="x")

        b_next = tk.Button(btn_frame, text="[N] NEXT", command=self.skip_lead)
        style_button(b_next, THEME["orange"], "#ff9e44", fg="#1a1a1a")
        b_next.pack(pady=3, fill="x")

        b_ban = tk.Button(btn_frame, text="[B] BANNED", command=self.ban_lead)
        style_button(b_ban, THEME["red"], "#ff5c5c")
        b_ban.pack(pady=3, fill="x")

        b_kill = tk.Button(btn_frame, text="[K] KILL CHROME & RETRY", command=self.kill_and_retry)
        style_button(b_kill, "#3a3a40", "#4a4a52")
        b_kill.pack(pady=3, fill="x")

        b_close = tk.Button(btn_frame, text="CLOSE", command=self.close_window)
        style_button(b_close, "#2a1010", "#3a1616", fg=THEME["red"])
        b_close.pack(pady=3, fill="x")

        self.bind('y', lambda e: self.handle_hotkey('y'))
        self.bind('n', lambda e: self.handle_hotkey('n'))
        self.bind('b', lambda e: self.handle_hotkey('b'))
        self.bind('s', lambda e: self.handle_hotkey('s'))
        self.bind('k', lambda e: self.handle_hotkey('k'))

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
        elif key_type == 'k':
            self.kill_and_retry()

    def kill_and_retry(self):
        self.lbl_action.config(text="Killing Chrome processes...", fg=THEME["warning"])
        kill_chrome_and_release_locks()
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        self.lbl_action.config(text="Chrome killed – press START again", fg=THEME["warning"])
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
        twitter_id_text = f"\nTwitter ID: {lead.get('Twitter ID', '')}" if lead.get('Twitter ID', '').strip() else ""
        self.lbl_current.config(
            text=f"Handle: {lead.get('Handle', 'Unknown')}{twitter_id_text}\nAccount: {lead.get('Account URL', '')}\nVideo: {lead.get('Video URL', '')}{email_text}",
            fg=THEME["text"]
        )
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
                    writer.writerow([lead['Handle'], lead.get('Twitter ID', ''), "Success", datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
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
            twitter_id = lead.get('Twitter ID', '')
            if twitter_id:
                with open(BLACKLIST_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{twitter_id}\n")
                with open(DUPLICATE_CACHE_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{twitter_id}\n")
            with open(BLACKLIST_FILE, 'a', encoding='utf-8') as f:
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

            # Select Twitter platform
            if not select_twitter_platform(self.driver, timeout=10):
                try:
                    select_el = self.driver.find_element(By.XPATH, "//select")
                    Select(select_el).select_by_visible_text("Twitter")
                except:
                    pass

            # Enter handle (Twitter ID for dedup, or handle)
            handle_box = self.wait_for_element("//input[@type='text']", timeout=12)
            handle_box.clear()
            handle_box.send_keys(lead.get('Twitter ID', lead['Handle']))
            time.sleep(0.5)
            try:
                check_btn = self.wait_for_element("//button[contains(., 'Check') or contains(., 'Verify')]")
                check_btn.click()
            except Exception:
                pass
            time.sleep(2)

            # Fill in the submission fields
            fields = [
                {"val": lead['Account URL'], "xp": "//input[contains(@placeholder, 'Account')] | //label[contains(., 'Account')]/..//input"},
                {"val": lead['Video URL'], "xp": "//input[contains(@placeholder, 'Video')] | //label[contains(., 'Video')]/..//input"},
                {"val": str(lead.get('Followers', '')), "xp": "//input[contains(@placeholder, 'Follower')] | //label[contains(., 'Follower')]/..//input | //input[contains(@placeholder, 'Subscribers')]"},
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
        send_to_discord(f"🛑 **Twitter Vetting Session Stopped**\nSuccessful Submissions: `{self.success_count}`\nRemaining Queue: `{len(self.leads)}`")
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
