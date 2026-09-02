import uiautomator2 as u2
import time
import sys
import csv
import os

# ====================================================
# CONFIGURATION
# ====================================================
PACKAGE_NAME = "com.instagold.android"   # IG Gold
MAX_REELS_TO_COPY = 20
CSV_FILE = "reel_links.csv"
# ====================================================

d = u2.connect()
print(f"✅ Connected to device: {d.info['productName']}")

# Android 10+ blocks background apps from reading the clipboard unless they
# are the active input method. uiautomator2 ships an IME for exactly this
# reason — this MUST be called once before d.clipboard will ever return
# anything real. Without this, d.clipboard silently returns None forever.
d.set_fastinput_ime()
print("⌨️  ATX input method enabled for clipboard reads.")


def adb_clipboard():
    """
    Legacy fallback — kept as a no-op stub. 'cmd clipboard get-text' is not a
    real Android shell command; on devices where it's unsupported the shell
    just echoes back an error string like 'No shell command implementation.'
    which was being mistaken for real clipboard content. Real clipboard
    reads go through d.clipboard (requires d.set_input_ime(), see below).
    """
    return None


def start_instagram():
    print("📱 Starting IG Gold...")
    d.shell('monkey -p {} -c android.intent.category.LAUNCHER 1'.format(PACKAGE_NAME))
    time.sleep(5)


def go_to_reels_feed():
    print("🔍 Navigating to Reels feed...")
    if d(resourceId="com.instagold.android:id/clips_tab").exists:
        d(resourceId="com.instagold.android:id/clips_tab").click()
    elif d(description="Reels").exists:
        d(description="Reels").click()
    elif d(text="Reels").exists:
        d(text="Reels").click()
    elif d(textContains="Reel").exists:
        d(textContains="Reel").click()
    else:
        print("❌ Could not find Reels button. Dumping UI for debugging...")
        print(d.dump_hierarchy())
        return False
    time.sleep(3)
    return True


def get_profile_url():
    print("   📌 Getting profile URL...")

    # Click username
    username_btn = d(resourceId="com.instagold.android:id/clips_author_username")
    if not username_btn.exists:
        username_btn = d(className="android.widget.Button", descriptionContains="and")
    if not username_btn.exists:
        print("   ⚠️ Username button not found. Trying coordinate tap...")
        width, height = d.window_size()
        d.click(int(width * 0.12), int(height * 0.12))
        time.sleep(2)
    else:
        username_btn.click()
        time.sleep(2)

    # Wait for profile
    if not d(resourceId="com.instagold.android:id/action_bar_title").wait(timeout=5):
        print("   ⚠️ Profile didn't load, but continuing...")

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
            print("   ❌ Could not find 'Copy' button.")
            d.press("back")
            return None

    copy_btn = d(description="Copy") if d(description="Copy").exists else d(text="Copy")
    if copy_btn.exists:
        copy_btn.click()
        time.sleep(1.5)
    else:
        print("   ❌ Copy button not found after wait.")
        d.press("back")
        return None

    # Read clipboard
    profile_url = d.clipboard
    if not profile_url:
        profile_url = adb_clipboard()
    if profile_url and ("instagram.com" in profile_url or "instagr.am" in profile_url):
        print(f"   ✅ Profile URL: {profile_url}")
    else:
        print(f"   ⚠️ No valid profile URL (got: {profile_url})")
        profile_url = None

    # Return to Reel – one Back press
    d.press("back")
    time.sleep(3)

    # Safety check: if still on profile, press Back again
    if d(resourceId="com.instagold.android:id/action_bar_title").exists(timeout=2):
        print("   🔄 Still on profile, pressing back again...")
        d.press("back")
        time.sleep(3)

    return profile_url


def get_reel_link():
    """
    Copy the current Reel's link.
    Restored from the older, working version: broader fallbacks for both
    the Share/More button and the 'Copy link' option, since the Reels UI
    doesn't always expose the same resourceId as the main feed.
    """
    print("   🎥 Getting Reel URL...")

    # Wait for the Reel to fully load (like_button is the correct resourceId
    # for the Reels screen — row_feed_icon_like belongs to the main feed and
    # never appears here, which was silently wasting 5s every loop)
    if not d(resourceId="com.instagold.android:id/like_button").wait(timeout=5):
        print("   ⏳ Reel didn't load in time, retrying...")
        time.sleep(2)

    share_btn = None

    # ---- 1. Find the Share / More button (broad fallback chain) ----
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
        print("   ⚠️ Share button not found by text/ID. Trying coordinate fallback...")
        width, height = d.window_size()
        d.click(int(width * 0.9), int(height * 0.2))
        time.sleep(1.5)
    else:
        share_btn.click()
        print("   📤 Clicked Share/More button.")
        time.sleep(1.5)

    # ---- 2. Find the "Copy link" option (broad fallback chain, WITH retries) ----
    # The share sheet has to render a whole grid of DM contacts before "Copy
    # link" appears, which can take longer than a fixed sleep on a real
    # device. An instant .exists check was firing before it rendered, so we
    # now poll for a few seconds instead of checking once.
    copy_btn = None
    for attempt in range(8):
        if d(description="Copy link").exists:
            copy_btn = d(description="Copy link")
            break
        if d(text="Copy link").exists:
            copy_btn = d(text="Copy link")
            break
        if d(text="Copy URL").exists:
            copy_btn = d(text="Copy URL")
            break
        if d(text="Salin tautan").exists:  # Indonesian language fallback
            copy_btn = d(text="Salin tautan")
            break
        if d(textContains="Copy").exists:
            copy_btn = d(textContains="Copy")
            break
        print(f"   ⏳ Waiting for 'Copy link' to render... attempt {attempt+1}/8")
        time.sleep(0.5)

    if copy_btn is None:
        print("   ❌ Could not find 'Copy link' button.")
        d.press("back")
        return None

    copy_btn.click()
    print("   📋 Clicked Copy link.")
    time.sleep(1.5)

    # ---- 3. Read the clipboard ----
    reel_url = d.clipboard
    if not reel_url:
        reel_url = adb_clipboard()
    if reel_url and ("instagram.com" in reel_url or "instagr.am" in reel_url):
        print(f"   ✅ Reel URL: {reel_url}")
    else:
        print(f"   ⚠️ No valid Reel URL (got: {reel_url})")
        reel_url = None

    # ---- 4. Close the share menu ----
    d.press("back")
    time.sleep(0.5)

    return reel_url


def scroll_to_next_reel():
    d.swipe(500, 800, 500, 300, duration=0.3)
    time.sleep(3)


def save_pair_to_csv(profile_url, reel_url):
    """Append one row to the CSV, writing the header only if the file is new."""
    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["profile_url", "reel_url"])
        writer.writerow([profile_url, reel_url])


# ====================================================
# MAIN LOOP
# ====================================================
if __name__ == "__main__":
    collected_pairs = []
    try:
        start_instagram()
        if not go_to_reels_feed():
            print("🚨 Failed to enter Reels.")
            sys.exit(1)

        for i in range(MAX_REELS_TO_COPY):
            print(f"\n{'='*40}")
            print(f"📱 Reel {i+1}/{MAX_REELS_TO_COPY}")
            print(f"{'='*40}")

            profile_url = get_profile_url()
            if profile_url is None:
                print("   ⚠️ Could not get profile URL. Skipping this reel.")
                if i < MAX_REELS_TO_COPY - 1:
                    scroll_to_next_reel()
                continue

            reel_url = get_reel_link()
            if reel_url is None:
                print("   ⚠️ Could not get reel URL. Skipping this reel.")
                if i < MAX_REELS_TO_COPY - 1:
                    scroll_to_next_reel()
                continue

            pair = f"{profile_url}, {reel_url}"
            collected_pairs.append(pair)

            save_pair_to_csv(profile_url, reel_url)

            print(f"   💾 Saved: {pair}")

            if i < MAX_REELS_TO_COPY - 1:
                print("   ⬆️ Scrolling to next reel...")
                scroll_to_next_reel()

        print(f"\n{'='*40}")
        print(f"🎉 Done! Collected {len(collected_pairs)} pairs.")
        print(f"📁 Saved to '{CSV_FILE}'")
        print(f"{'='*40}")

    except KeyboardInterrupt:
        print("\n⏹️ Script stopped by user.")
        print(f"✅ Saved {len(collected_pairs)} pairs so far.")
    except Exception as e:
        print(f"🔥 Unexpected error: {e}")
        try:
            print("\n--- Current UI Dump ---")
            print(d.dump_hierarchy())
        except:
            print("Could not dump UI.")