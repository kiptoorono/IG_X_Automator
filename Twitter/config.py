import os
import sys

APP_NAME = "ViralTaskScouterTwitter"
LOCAL_APP_DATA = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
DATA_DIR = os.path.join(LOCAL_APP_DATA, APP_NAME)

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

RAW_LINKS_FILE = os.path.join(DATA_DIR, "raw_links_twitter.txt")
METADATA_FILE = os.path.join(DATA_DIR, "metadata_leads_twitter.csv")
CLEAN_LEADS_FILE = os.path.join(DATA_DIR, "clean_leads_twitter.csv")
SUBMITTED_FILE = os.path.join(DATA_DIR, "final_submissions_twitter.csv")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist_twitter.txt")
DUPLICATE_CACHE_FILE = os.path.join(DATA_DIR, "known_duplicates_twitter.txt")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots_twitter")

# Collected pairs: Handle, TwitterID, Account URL, Video URL, Email
COLLECTED_PAIRS_FILE = os.path.join(DATA_DIR, "collected_pairs_twitter.csv")

if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

# Chrome paths
USER_CHROME_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Google\Chrome\User Data Twitter")
BOT_PROFILE_NAME = "Default"
BOT_PROFILE_DIR = os.path.join(USER_CHROME_DATA_DIR, BOT_PROFILE_NAME)
if not os.path.exists(BOT_PROFILE_DIR):
    os.makedirs(BOT_PROFILE_DIR)


def find_chrome():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Google\Chrome\Application\chrome.exe")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

CHROME_PATH = find_chrome()
CURRENT_VERSION = "1.0.0"

# Discord/webhook fallback
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from config import get_hwid, get_user_name, send_to_discord, log_stats, DISCORD_WEBHOOK
except ImportError:
    DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")

    def get_hwid():
        try:
            import subprocess
            cmd = 'wmic csproduct get uuid'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                for line in lines:
                    if len(line) > 10 and '-' in line and line != 'uuid':
                        return line
        except:
            pass
        return "UNKNOWN_HWID"

    def get_user_name():
        return os.environ.get('USERNAME', 'UnknownUser')

    def send_to_discord(message, file_path=None):
        import requests
        if not DISCORD_WEBHOOK:
            return
        user_info = f"👤 **User:** `{get_user_name()}` | 🔑 **ID:** `{get_hwid()}`"
        payload = {"content": f"{user_info}\n{message}"}
        try:
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    requests.post(DISCORD_WEBHOOK, data=payload, files={'file': f})
            else:
                requests.post(DISCORD_WEBHOOK, json=payload)
        except:
            pass

    def log_stats(action, session_success=0, total_submitted=0):
        pass
