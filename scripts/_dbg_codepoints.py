from pathlib import Path

p = Path(r"D:\codex\xiuxian\server\world.py")
text = p.read_text(encoding="utf-8")
for i, line in enumerate(text.splitlines(), 1):
    if 'action in ("/talk"' in line or "/交谈" in line and "action in" in line:
        print(i, repr(line))
        # 找出交谈的 codepoints
        if "/交谈" in line:
            j = line.index("/交谈")
            chunk = line[j : j + 4]
            print("codepoints", [hex(ord(c)) for c in chunk])

runtime = "/交谈"
print("runtime", [hex(ord(c)) for c in runtime])
