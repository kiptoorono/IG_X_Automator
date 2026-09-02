import uiautomator2 as u2
import time
import sys
import re

# ====================================================
# CONFIGURATION - EDIT THESE TWO LINES
# ====================================================
PACKAGE_NAME = "com.instagold.android"
#PACKAGE_NAME = "com.instagram.android"  # Your modded APK package name
MAX_REELS_TO_COPY = 20                  # How many links you want
# ====================================================

# Connect to your phone via USB
d = u2.connect()
print(f"✅ Connected to device: {d.info['productName']}")

def start_instagram():
    """
    Force-start Instagram using ADB 'am start'.
    This works even with split APKs (modded versions).
    """
    print("📱 Starting Instagram...")
    # Try to stop it first (optional) then start
    # Use monkey command which is more robust
    result = d.shell('monkey -p {} -c android.intent.category.LAUNCHER 1'.format(PACKAGE_NAME))
    # Alternative if monkey fails:
    # d.shell('am start -n {}/com.instagram.mainactivity.MainActivity'.format(PACKAGE_NAME))
    time.sleep(5)  # Wait for app to load

def go_to_reels_feed():
    """
    Tap the 'Reels' icon at the bottom navigation bar.
    Uses multiple fallbacks for modded APKs.
    """
    print("🔍 Navigating to Reels feed...")
    
    # Try different ways to find the Reels button
    if d(description="Reels").exists:
        d(description="Reels").click()
    elif d(text="Reels").exists:
        d(text="Reels").click()
    elif d(textContains="Reel").exists:
        d(textContains="Reel").click()
    elif d(resourceId="com.instagold.android:id/reel_tab").exists:
        d(resourceId="com.instagold.android:id/reel_tab").click()
    else:
        # If we can't find it, dump the UI so we can debug
        print("❌ ERROR: Could not find Reels button. Dumping UI for debugging...")
        print(d.dump_hierarchy())
        return False
        
    time.sleep(3)  # Wait for the first Reel to load
    return True

def get_current_reel_link():
    """
    Finds the current playing Reel, clicks the share/more button,
    clicks 'Copy link', and returns the URL.
    """
    # Wait for the Reel to fully load (look for the like button as a sign)
    if not d(resourceId="com.instagold.android:id/row_feed_icon_like").wait(timeout=5):
        print("   ⏳ Reel didn't load in time, retrying...")
        time.sleep(2)

    share_btn = None
    
    # ---- 1. Find the Share / More button ----
    # Try Resource ID (standard Instagram)
    if d(resourceId="com.instagram.android:id/row_feed_action_share").exists:
        share_btn = d(resourceId="com.instagram.android:id/row_feed_action_share")
    # Try description
    elif d(description="Share").exists:
        share_btn = d(description="Share")
    elif d(descriptionContains="Share").exists:
        share_btn = d(descriptionContains="Share")
    # Try the 3-dots "More options" (some mods hide copy link here)
    elif d(description="More options").exists:
        share_btn = d(description="More options")
    
    # If still not found, try a generic XPath for any clickable icon on the right side
    if share_btn is None:
        print("   ⚠️ Share button not found by text/ID. Trying coordinate fallback...")
        # Usually the share icon is on the right side of the screen.
        # Let's click roughly at (90% width, 20% height) - adjust if needed
        width, height = d.window_size()
        d.click(width * 0.9, height * 0.2)
        time.sleep(1)
        # We'll try to find copy link in the menu that opens
    else:
        share_btn.click()
        time.sleep(1.5)

    # ---- 2. Find the "Copy link" option ----
    copy_btn = None
    if d(text="Copy link").exists:
        copy_btn = d(text="Copy link")
    elif d(text="Copy URL").exists:
        copy_btn = d(text="Copy URL")
    elif d(textContains="Copy").exists:
        copy_btn = d(textContains="Copy")
    elif d(text="Salin tautan").exists:  # Indonesian language fallback
        copy_btn = d(text="Salin tautan")
    
    if copy_btn is None:
        print("   ❌ Could not find 'Copy link' button.")
        # Press back to close whatever menu is open
        d.press("back")
        return None

    copy_btn.click()
    time.sleep(1)

    # ---- 3. Read the clipboard ----
    link = d.clipboard
    if link and ("instagram.com" in link or "instagr.am" in link):
        print(f"   ✅ Copied: {link}")
    else:
        print(f"   ⚠️ Clipboard doesn't contain an Instagram link (got: {link})")
        link = None

    # ---- 4. Close the share menu (press back) ----
    d.press("back")
    time.sleep(0.5)
    return link

def scroll_to_next_reel():
    """
    Swipe up on the screen to go to the next Reel.
    """
    # Swipe from the bottom-middle to the top-middle
    # Coordinates: (x1, y1) to (x2, y2)
    d.swipe(500, 800, 500, 300, duration=0.3)
    time.sleep(3)  # Wait for the next Reel to load

# ====================================================
# MAIN EXECUTION
# ====================================================
if __name__ == "__main__":
    try:
        start_instagram()
        time.sleep(2)

        if not go_to_reels_feed():
            print("🚨 Failed to navigate to Reels. Exiting.")
            sys.exit(1)

        collected_links = []
        print(f"🔄 Starting collection loop. Target: {MAX_REELS_TO_COPY} links.\n")

        for i in range(MAX_REELS_TO_COPY):
            print(f"--- Reel {i+1}/{MAX_REELS_TO_COPY} ---")
            
            link = get_current_reel_link()
            
            if link:
                collected_links.append(link)
                # Write to file immediately so we don't lose progress
                with open("reel_links.txt", "a", encoding="utf-8") as f:
                    f.write(link + "\n")
            else:
                print("   ⚠️ Skipping this reel (could not get link).")

            # Scroll to the next Reel (unless it's the last one)
            if i < MAX_REELS_TO_COPY - 1:
                print("   ⬆️ Scrolling to next reel...")
                scroll_to_next_reel()

        print(f"\n🎉 Done! Collected {len(collected_links)} links.")
        print(f"📁 Saved to 'reel_links.txt' in the same folder as this script.")

    except KeyboardInterrupt:
        print("\n⏹️ Script stopped by user.")
        print(f"✅ Saved {len(collected_links)} links so far.")
    except Exception as e:
        print(f"🔥 Unexpected error: {e}")
        # Try to print the current UI to help debug
        print("\n--- Current UI Dump (for debugging) ---")
        try:
            print(d.dump_hierarchy())
        except:
            print("Could not dump UI.")