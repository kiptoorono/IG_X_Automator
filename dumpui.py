import uiautomator2 as u2
import time

d = u2.connect()
print("✅ Connected.")
input("👉 Go to a Reel in IG Gold and press ENTER...")

xml = d.dump_hierarchy()
with open("reel_ui.xml", "w", encoding="utf-8") as f:
    f.write(xml)
print("✅ Dumped to reel_ui.xml")