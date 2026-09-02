import uiautomator2 as u2
import time
import re

d = u2.connect()
print(f"CONNECTED: {d.info['productName']}")
d.set_fastinput_ime()

# Check current app
current = d.app_current()
print(f"Current app: {current.get('package', 'unknown')}")

if "twitter" not in str(current.get("package", "")).lower():
    print("Twitter not in foreground. Opening...")
    d.shell('monkey -p com.twitter.android -c android.intent.category.LAUNCHER 1')
    time.sleep(5)

print("\n--- TEST 1: Find @handle on screen ---")
# Use XML dump + regex for reliable handle extraction (Compose UI)
xml = d.dump_hierarchy()
matches = re.findall(r'text="(@[A-Za-z0-9_]+)"', xml)
if matches:
    for m in matches:
        print(f"  FOUND handle: {m}")
    handle = matches[0]
    print(f"  Using first: {handle}")
else:
    print("  No @handle found on screen")
    # Show all non-empty text elements for debugging
    texts = re.findall(r'text="([^"]+)"', xml)
    print(f"  All visible text: {texts[:20]}")

print("\n--- TEST 2: Find Share button ---")
# Try content-desc first
share_btn = d(description="Share")
if share_btn.exists:
    print(f"  FOUND Share button: content-desc=\"Share\"")
    info = share_btn.info
    print(f"     Bounds: {info.get('bounds', 'N/A')}")
    print(f"     Class: {info.get('className', 'N/A')}")
else:
    print("  content-desc='Share' not found, checking XML...")
    # Search XML for Share content-desc
    share_matches = re.findall(r'content-desc="(Share)"[^>]*bounds="(\[.+?\])"', xml)
    if share_matches:
        for desc, bounds in share_matches:
            print(f"  FOUND in XML: content-desc=\"{desc}\" bounds={bounds}")
    else:
        print("  Share not found in XML either")

print("\n--- TEST 3: Find 'Copy link' in share sheet ---")
print("  (Clicking Share button to open sheet...)")
share_btn = d(description="Share")
if share_btn.exists:
    share_btn.click()
    time.sleep(2)
    
    copy_link = d(text="Copy link")
    if copy_link.exists:
        print(f"  FOUND 'Copy link' button")
        print(f"     Bounds: {copy_link.info.get('bounds', 'N/A')}")
        
        # Test clipboard copy
        copy_link.click()
        time.sleep(1.5)
        clip = d.clipboard
        if clip:
            print(f"  Clipboard: {clip}")
        else:
            print("  Clipboard empty after click")
    else:
        print("  'Copy link' not found in share sheet")
        # List all visible text
        xml = d.dump_hierarchy()
        texts = re.findall(r'text="([^"]+)"', xml)
        print(f"  Visible texts: {[t for t in texts if t.strip()][:15]}")
    
    # Close sheet
    close = d(description="Close sheet")
    if close.exists:
        close.click()
        time.sleep(0.5)
    else:
        d.press("back")
        time.sleep(0.5)
else:        print("  Skipped (Share button not found)")

print("\n--- TEST 4: Find Back button ---")
back_btn = d(description="Back")
if back_btn.exists:
    print(f"  FOUND Back button: content-desc=\"Back\"")
else:
    print("  Back button not found")

print("\n--- TEST 5: Find More options ---")
more_btn = d(description="More options")
if more_btn.exists:
    print(f"  FOUND More options: content-desc=\"More options\"")
else:
    print("  More options not found")

print("\n--- DONE ---")
