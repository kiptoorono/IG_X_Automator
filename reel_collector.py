import uiautomator2 as u2
import time
import sys

# ====================================================
# CONFIGURATION
# ====================================================
PACKAGE_NAME = "com.instagold.android"   # IG Gold
MAX_REELS_TO_COPY = 20
# ====================================================

d = u2.connect()
print(f"✅ Connected to device: {d.info['productName']}")

def adb_clipboard():
    """Fallback to read clipboard via ADB."""
    result = d.shell('cmd clipboard get-text')
    return result.output.strip() if result.output else None

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
    else:
        print("❌ Could not find Reels button.")
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
    time.sleep(3)  # Give Reel time to reappear and stabilize
    
    # Safety check: if still on profile, press Back again
    if d(resourceId="com.instagold.android:id/action_bar_title").exists(timeout=2):
        print("   🔄 Still on profile, pressing back again...")
        d.press("back")
        time.sleep(3)
    
    return profile_url

def get_reel_link():
    """
    Copy the current Reel's link using UI selectors from the dump.
    """
    print("   🎥 Getting Reel URL...")

    # ---- Wait for the Reel UI to be fully loaded ----
    share_btn = None
    for attempt in range(6):
        share_btn = d(resourceId="com.instagold.android:id/direct_share_button")
        if share_btn.exists:
            break
        share_btn = d(description="Share")
        if share_btn.exists:
            break
        print(f"   ⏳ Waiting for Share button... attempt {attempt+1}/6")
        time.sleep(1)

    if share_btn is None or not share_btn.exists:
        print("   ❌ Share button not found after waiting.")
        # Try "More" button as fallback
        more_btn = d(description="More")
        if not more_btn.exists:
            more_btn = d(resourceId="com.instagold.android:id/clips_ufi_more_button_component")
        if more_btn.exists:
            print("   🔄 Falling back to 'More' button...")
            more_btn.click()
            time.sleep(1.5)
            copy_link_btn = d(description="Copy link") if d(description="Copy link").exists else d(text="Copy link")
            if copy_link_btn.exists:
                copy_link_btn.click()
                time.sleep(1.5)
                reel_url = d.clipboard or adb_clipboard()
                if reel_url and ("instagram.com" in reel_url or "instagr.am" in reel_url):
                    print(f"   ✅ Reel URL (via More): {reel_url}")
                    d.press("back")
                    return reel_url
                else:
                    print("   ❌ No valid Reel URL from More.")
                    d.press("back")
                    return None
        print("   ❌ Could not find Share or More button.")
        return None

    # ---- Share button found – click it ----
    share_btn.click()
    print("   📤 Clicked Share button.")
    time.sleep(2)

    # ---- Find and click "Copy link" ----
    copy_link_btn = None
    if d(description="Copy link").exists:
        copy_link_btn = d(description="Copy link")
    elif d(text="Copy link").exists:
        copy_link_btn = d(text="Copy link")
    elif d(textContains="Copy").exists:
        copy_link_btn = d(textContains="Copy")

    if copy_link_btn is None:
        print("   ❌ Could not find 'Copy link' in share menu.")
        d.press("back")
        return None

    copy_link_btn.click()
    print("   📋 Clicked Copy link.")
    time.sleep(1.5)

    # ---- Read the clipboard ----
    reel_url = d.clipboard
    if not reel_url:
        reel_url = adb_clipboard()
    if reel_url and ("instagram.com" in reel_url or "instagr.am" in reel_url):
        print(f"   ✅ Reel URL: {reel_url}")
    else:
        print(f"   ⚠️ No valid Reel URL (got: {reel_url})")
        reel_url = None

    # ---- Close share menu ----
    d.press("back")
    time.sleep(0.5)

    return reel_url

def scroll_to_next_reel():
    d.swipe(500, 800, 500, 300, duration=0.3)
    time.sleep(3)

# ====================================================
# MAIN LOOP
# ====================================================
if __name__ == "__main__":
    try:
        start_instagram()
        if not go_to_reels_feed():
            print("🚨 Failed to enter Reels.")
            sys.exit(1)
        
        collected_pairs = []
        
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
            
            with open("reel_links.txt", "a", encoding="utf-8") as f:
                f.write(pair + "\n")
            
            print(f"   💾 Saved: {pair}")
            
            if i < MAX_REELS_TO_COPY - 1:
                print("   ⬆️ Scrolling to next reel...")
                scroll_to_next_reel()
        
        print(f"\n{'='*40}")
        print(f"🎉 Done! Collected {len(collected_pairs)} pairs.")
        print(f"📁 Saved to 'reel_links.txt'")
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