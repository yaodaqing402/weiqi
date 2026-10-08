"""测试用的假 GTP 引擎：模拟 KataGo 的应答格式（不下真正的好棋）。

genmove 返回棋盘上第一个空点（按 A9→J1 顺序）；final_status_list dead 返回所有白子。
"""
import sys

LETTERS = "ABCDEFGHJKLMNOPQRST"
size = 19
stones = {}


def reply(text="", ok=True):
    sys.stdout.write(("= " if ok else "? ") + text + "\n\n")
    sys.stdout.flush()


for line in sys.stdin:
    parts = line.strip().split()
    if not parts:
        continue
    cmd, args = parts[0], parts[1:]
    if cmd == "name":
        reply("FakeGo")
    elif cmd == "version":
        reply("0.1")
    elif cmd == "boardsize":
        size = int(args[0])
        stones = {}
        reply()
    elif cmd == "clear_board":
        stones = {}
        reply()
    elif cmd == "komi":
        reply()
    elif cmd == "play":
        if args[1].lower() != "pass":
            stones[args[1].upper()] = args[0].upper()
        reply()
    elif cmd == "genmove":
        for row in range(size, 0, -1):
            done = False
            for col in LETTERS[:size]:
                v = f"{col}{row}"
                if v not in stones:
                    stones[v] = args[0].upper()
                    reply(v)
                    done = True
                    break
            if done:
                break
        else:
            reply("pass")
    elif cmd == "final_status_list":
        reply(" ".join(v for v, c in stones.items() if c == "W"))
    elif cmd == "quit":
        reply()
        break
    else:
        reply("unknown command", ok=False)
