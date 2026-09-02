import uiautomator2 as u2
import time
import re
import csv
import os

MAX_VIDEOS = 5  # test with 5
TWITTER_PACKAGE = "com.twitter.android"
OUTPUT_FILE = "test_collected_pairs.csv"

d = u2.connect()
print(f"CONNECTED: {d.info['productName']}")
d.set_fastinput_ime()

# Ensure output file exists
if not os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        csv.writer(f).writerow(["Handle", "Account URL", "Video URL"])

collected = 0
width, height = d.window_size()
print(f"Screen: {width}x{height}")

for i in range(MAX_VIDEOS):
    print(f"\n{'='*50}")
    print(f"VIDEO {i+1}/{MAX_VIDEOS}")
    print(f"{'='*50}")

    time.sleep(1)

    # --- Step 1: Extract @handle from video player overlay ---
    handle = None
    for wait_attempt in range(10):
        xml = d.dump_hierarchy()
        matches = re.findall(r'text="(@[A-Za-z0-9_]+)"', xml)
        if matches:
            handle = matches[0]
            print(f"  HANDLE: {handle}")
            break
        time.sleep(0.5)
    if not handle:
        print("  SKIP: No @handle found after waiting")
        d.swipe(int(width * 0.5), int(height * 0.75), int(width * 0.5), int(height * 0.25), duration=0.3)
        time.sleep(3)
        continue

    # Construct profile URL
    clean_handle = handle.lstrip("@")
    profile_url = f"https://x.com/{clean_handle}"
    print(f"  PROFILE URL: {profile_url}")

    # --- Step 2: Click Share button ---
    video_url = None
    share_btn = d(description="Share")
    if share_btn.exists:
        share_btn.click()
        print("  Clicked Share")
        time.sleep(2)

        # --- Step 3: Click Copy link ---
        copy_link = None
        for attempt in range(15):
            if d(text="Copy link").exists:
                copy_link = d(text="Copy link")
                break
            time.sleep(0.5)
        if copy_link:
            copy_link.click()
            print("  Clicked Copy link")
            time.sleep(1.5)
            video_url = d.clipboard
            if video_url and ("x.com" in video_url or "twitter.com" in video_url):
                print(f"  VIDEO URL: {video_url}")
            else:
                print(f"  CLIPBOARD: {video_url}")
                video_url = None
        else:
            # Try scrolling share sheet to reveal Copy link
            print("  'Copy link' not found, trying scroll...")
            d.swipe(int(width * 0.5), int(height * 0.9), int(width * 0.5), int(height * 0.6), duration=0.3)
            time.sleep(1)
            copy_link2 = d(text="Copy link")
            if copy_link2.exists:
                copy_link2.click()
                print("  Clicked Copy link (after scroll)")
                time.sleep(1.5)
                video_url = d.clipboard
                if video_url and ("x.com" in video_url or "twitter.com" in video_url):
                    print(f"  VIDEO URL: {video_url}")
                else:
                    video_url = None
            else:
                # Dismiss share sheet without exiting video player
                d.click(int(width * 0.5), int(height * 0.3))
                time.sleep(0.5)

        # Close share sheet WITHOUT pressing back (back exits video player)
        close = d(description="Close sheet")
        if close.exists:
            close.click()
            print("  Dismissed share sheet")
            time.sleep(0.5)
        else:
            # Tap above the share sheet to dismiss it
            d.click(int(width * 0.5), int(height * 0.3))
            print("  Tapped above share sheet to dismiss")
            time.sleep(0.5)
    else:
        print("  Share button not found")

    # --- Step 4: Save ---
    if handle and video_url:
        with open(OUTPUT_FILE, 'a', encoding='utf-8', newline='') as f:
            csv.writer(f).writerow([handle, profile_url, video_url])
        collected += 1
        print(f"  SAVED ({collected} total)")
    else:
        missing = []
        if not handle: missing.append("handle")
        if not video_url: missing.append("video_url")
        print(f"  SKIP: missing {', '.join(missing)}")

    # --- Step 5: Scroll to next video ---
    if i < MAX_VIDEOS - 1:
        d.swipe(int(width * 0.5), int(height * 0.75), int(width * 0.5), int(height * 0.25), duration=0.3)
        time.sleep(2)
        # Tap screen to bring back overlay buttons
        d.click(int(width * 0.5), int(height * 0.5))
        print("  Scrolled + tapped to show overlays")
        time.sleep(1.5)

print(f"\n{'='*50}")
print(f"DONE - Collected {collected} pairs")
print(f"Saved to: {OUTPUT_FILE}")
print(f"{'='*50}")
