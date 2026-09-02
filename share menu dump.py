import uiautomator2 as u2

d = u2.connect()
print("✅ Connected to phone.")

input("\n👉 On your phone, open IG Gold and play any Reel.")
input("👉 Tap the Share button (paper plane) to open the share menu.")
input("👉 Make sure the share menu is fully open, then press ENTER here...")

print("\n📸 Dumping UI...")
xml = d.dump_hierarchy()

with open("share_menu.xml", "w", encoding="utf-8") as f:
    f.write(xml)

print("✅ UI dumped to 'share_menu.xml' in this folder.")
print("\n🔍 Open 'share_menu.xml' in Notepad and search for:")
print("   - 'Copy'")
print("   - 'link'")
print("   - 'Share' (for the share button)")
print("\n📋 Copy the lines around those matches and paste them here.")