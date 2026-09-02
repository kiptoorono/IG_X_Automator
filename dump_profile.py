import uiautomator2 as u2

d = u2.connect()
input("👉 Go to a profile, open the 3-dot menu, then press ENTER...")
xml = d.dump_hierarchy()
with open("profile_menu.xml", "w", encoding="utf-8") as f:
    f.write(xml)
print("✅ Dumped to profile_menu.xml")