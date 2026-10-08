"""准备随安装包附带的 KataGo（程序 + 模型），放到 vendor/katago/ 下，供 PyInstaller 打包。

    python packaging/fetch_katago.py

- 模型（两个平台共用）：主模型 kata1-b18 + 人类风格模型 b18-humanv0，下载一次后缓存。
- macOS：使用 Homebrew 安装的 katago（Metal 后端，需先 brew install katago），
  把它依赖的全部非系统动态库一并拷贝，改写为相对路径（@loader_path/lib），再做 ad-hoc 签名。
- Windows：下载官方 OpenCL 版（显卡加速）与 Eigen-AVX2 版（纯 CPU，显卡不可用时兜底）。
"""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "katago"

KATAGO_WIN_VERSION = "v1.18.1"
WIN_BACKENDS = ["opencl", "eigenavx2"]
MODELS = {
    "kata1-b18c384nbt-s9996604416-d4316597426.bin.gz":
        "https://media.katagotraining.org/uploaded/networks/models/kata1/"
        "kata1-b18c384nbt-s9996604416-d4316597426.bin.gz",
    "b18c384nbt-humanv0.bin.gz":
        "https://github.com/lightvector/KataGo/releases/download/v1.15.0/b18c384nbt-humanv0.bin.gz",
}


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"已存在，跳过：{dest.name}")
        return
    print(f"下载 {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "weiqi-packager"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)


def fetch_models() -> None:
    d = VENDOR / "models"
    d.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        dest = d / name
        download(url, dest)
        with gzip.open(dest, "rb") as g:      # 校验压缩包完整
            while g.read(1 << 22):
                pass


# ---------- macOS ----------
def _deps(path: Path) -> list:
    out = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
    deps = []
    for line in out.splitlines()[1:]:
        dep = line.strip().split(" (")[0]
        if dep:
            deps.append(dep)
    return deps


def _is_system(dep: str) -> bool:
    return dep.startswith("/usr/lib/") or dep.startswith("/System/")


def _resolve(dep: str, referrer: Path) -> Path:
    if dep.startswith("@loader_path/"):
        return (referrer.parent / dep[len("@loader_path/"):]).resolve()
    if dep.startswith("@rpath/"):
        name = dep[len("@rpath/"):]
        for cand in (referrer.parent / name, Path("/opt/homebrew/lib") / name):
            if cand.exists():
                return cand.resolve()
        raise FileNotFoundError(f"无法解析 {dep}（来自 {referrer}）")
    return Path(dep).resolve()


def bundle_macos() -> None:
    exe = shutil.which("katago") or "/opt/homebrew/bin/katago"
    if not os.path.exists(exe):
        sys.exit("未找到 katago，请先运行：brew install katago")
    exe = Path(os.path.realpath(exe))
    out = VENDOR / "macos"
    if out.exists():
        shutil.rmtree(out)
    lib = out / "lib"
    lib.mkdir(parents=True)
    target_exe = out / "katago"
    shutil.copy2(exe, target_exe)
    os.chmod(target_exe, 0o755)

    # 递归收集所有非系统依赖
    queue = [(exe, target_exe)]
    copied = {}
    while queue:
        src, dst = queue.pop()
        for dep in _deps(src):
            if _is_system(dep):
                continue
            real = _resolve(dep, src)
            name = Path(dep).name
            if real.name == src.name and dep.endswith(src.name) and src != exe:
                continue          # 自身 id
            if name not in copied:
                d = lib / name
                shutil.copy2(real, d)
                os.chmod(d, 0o755)
                copied[name] = d
                queue.append((real, d))
            # 主程序引用 @loader_path/lib/x，库之间互相引用 @loader_path/x
            new = f"@loader_path/lib/{name}" if dst == target_exe else f"@loader_path/{name}"
            subprocess.run(["install_name_tool", "-change", dep, new, str(dst)],
                           check=True, capture_output=True)
    for name, d in copied.items():
        subprocess.run(["install_name_tool", "-id", f"@loader_path/{name}", str(d)],
                       check=True, capture_output=True)
    # 改过加载路径后签名失效，Apple Silicon 必须重新（ad-hoc）签名才能运行
    for f in list(copied.values()) + [target_exe]:
        subprocess.run(["codesign", "--force", "-s", "-", str(f)], check=True, capture_output=True)
    # 自检：不能再引用 Homebrew 路径
    for f in list(copied.values()) + [target_exe]:
        bad = [x for x in _deps(f) if "/opt/homebrew" in x or "/usr/local/" in x]
        if bad:
            sys.exit(f"{f.name} 仍引用外部库：{bad}")
    ver = subprocess.run([str(target_exe), "version"], capture_output=True, text=True, timeout=60)
    print(ver.stdout.strip().splitlines()[0] if ver.stdout else ver.stderr)
    print(f"macOS KataGo 已打包：{len(copied)} 个依赖库")


# ---------- Windows ----------
def bundle_windows() -> None:
    out = VENDOR / "windows"
    out.mkdir(parents=True, exist_ok=True)
    cache = VENDOR / "cache"
    cache.mkdir(exist_ok=True)
    for backend in WIN_BACKENDS:
        name = f"katago-{KATAGO_WIN_VERSION}-{backend}-windows-x64.zip"
        url = f"https://github.com/lightvector/KataGo/releases/download/{KATAGO_WIN_VERSION}/{name}"
        z = cache / name
        download(url, z)
        dest = out / backend
        if dest.exists():
            shutil.rmtree(dest)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        exes = list(dest.rglob("katago.exe"))
        if not exes:
            sys.exit(f"{name} 里没有 katago.exe")
        # 统一成 dest/katago.exe（有的压缩包多一层目录）
        inner = exes[0].parent
        if inner != dest:
            for p in inner.iterdir():
                shutil.move(str(p), dest / p.name)
        # 官方压缩包里的示例配置/模型用不到，删掉省空间
        for p in dest.glob("*.cfg"):
            p.unlink()
        print(f"Windows KataGo（{backend}）已就绪")


def main() -> None:
    # Windows 控制台默认 cp1252，打印中文会报错
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    fetch_models()
    if sys.platform == "darwin":
        bundle_macos()
    elif os.name == "nt":
        bundle_windows()
    else:
        print("当前平台不打包 KataGo 程序，只准备了模型")


if __name__ == "__main__":
    main()
