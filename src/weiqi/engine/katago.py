"""KataGo 引擎接入（GTP 协议）。

- 安装包自带 KataGo 与模型（vendor/katago，打包后位于程序目录的 katago/ 下），开箱即用；
  也会查找本机自行安装的 katago（设置里指定的路径、数据目录、PATH、Homebrew）。
- Windows 自带两个版本：OpenCL（显卡加速）优先，启动失败自动换 Eigen-AVX2（纯 CPU）。
- 难度：有 Human-SL 人类风格模型时按“级位”模仿人类下法；没有时按搜索量分档。
- 采用“无状态同步”：每次思考前 clear_board 后重放全部着法，悔棋/提示都不会和引擎状态错位。
"""
from __future__ import annotations

import atexit
import glob
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .stones import BLACK, COL_LETTERS, KOMI, Move, Point

# 难度：名称、人类模型的级位档案、坏棋抑制强度 λ（越小越不允许下 KataGo 认为亏的棋）、
#       无人类模型时的搜索量
# “不乱下”靠 humanSLChosenMovePiklLambda：人类模型挑出的着法若被 KataGo 搜索判定明显亏损，
# 出现概率按 exp(-亏损/λ) 压低，于是低级别仍像对应水平的人类，但不会走出离谱的棋。
# λ 取值来自实测（9 路自对弈，强 KataGo 逐手评估，配合下面的 dynamicScoreUtilityFactor=0.5）：
# 入门 λ=0.1 时 5.6% 的着法亏 10 目以上，λ=0.04 时 3.8%（都太松）；λ=0.03 时降到 0.6%；
# λ 再小就接近满强度、失去难度梯度。
LEVELS = [
    ("入门", "rank_20k", 0.025, 16),
    ("初级", "rank_15k", 0.02, 32),
    ("中级", "rank_10k", 0.015, 64),
    ("高级", "rank_5k", 0.01, 128),
    ("大师", "rank_1d", 0.005, 300),
]
OPENING_RETRIES = 3      # 布局阶段走出“孤零零的一线”时，最多重新要几次着法
HUMAN_VISITS = 200       # 人类风格模式下搜索量：只用于给候选着法“验货”和判断停一手/认输
CPU_VISITS = 64          # 纯 CPU（Eigen）版本的搜索量上限
LEVEL_RANK_CN = ["20 级", "15 级", "10 级", "5 级", "业余 1 段"]

START_TIMEOUT = 240.0     # 首次运行 OpenCL 调优可能较慢
MOVE_TIMEOUT = 90.0


class EngineError(RuntimeError):
    pass


# ---------- 坐标换算 ----------
def to_vertex(size: int, move: Move) -> str:
    if move is None:
        return "pass"
    r, c = move
    return f"{COL_LETTERS[c]}{size - r}"


def from_vertex(size: int, v: str) -> object:
    """GTP 坐标 -> (r,c)；pass 返回 None；resign 返回 'resign'。"""
    v = v.strip().upper()
    if v == "PASS":
        return None
    if v == "RESIGN":
        return "resign"
    c = COL_LETTERS.index(v[0])
    r = size - int(v[1:])
    return (r, c)


# ---------- 查找程序与模型 ----------
def _data_katago_dir() -> Path:
    from ..game.storage import data_dir
    d = data_dir() / "katago"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundle_root() -> Optional[Path]:
    """随程序附带的 KataGo 目录；源码运行时为仓库里的 vendor/katago。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))) / "katago"
    else:
        base = Path(__file__).resolve().parents[3] / "vendor" / "katago"
    return base if base.is_dir() else None


def bundled_executables() -> List[str]:
    root = bundle_root()
    if root is None:
        return []
    if sys.platform == "darwin":
        cands = [root / "macos" / "katago"]
    elif os.name == "nt":
        cands = [root / "windows" / b / "katago.exe" for b in ("opencl", "eigenavx2")]
    else:
        cands = []
    return [str(p) for p in cands if p.is_file()]


def find_all_katago(settings: Optional[Dict] = None) -> List[str]:
    """按优先级列出可用的 katago：设置里指定的 > 自带的 > 本机安装的。"""
    settings = settings or {}
    out: List[str] = []
    custom = settings.get("katago_path") or ""
    if custom and os.path.isfile(custom):
        out.append(custom)
    out += bundled_executables()
    exe = "katago.exe" if os.name == "nt" else "katago"
    cands = [str(_data_katago_dir() / exe)]
    found = shutil.which("katago")
    if found:
        cands.append(found)
    cands += ["/opt/homebrew/bin/katago", "/usr/local/bin/katago", "/usr/bin/katago"]
    for p in cands:
        if p and os.path.isfile(p) and os.access(p, os.X_OK) and p not in out:
            out.append(p)
    return out


def find_katago(settings: Optional[Dict] = None) -> Optional[str]:
    found = find_all_katago(settings)
    return found[0] if found else None


def is_bundled(path: Optional[str]) -> bool:
    root = bundle_root()
    return bool(path and root and os.path.realpath(path).startswith(os.path.realpath(root)))


def _model_dirs(katago_path: Optional[str]) -> List[str]:
    dirs = []
    root = bundle_root()
    if root is not None:
        dirs.append(str(root / "models"))
    dirs += [str(_data_katago_dir()), str(_data_katago_dir() / "models")]
    if katago_path:
        real = os.path.realpath(katago_path)
        dirs.append(os.path.dirname(real))
        # Homebrew：bin/katago -> Cellar/katago/x/bin/katago，模型在 share/katago
        prefix = os.path.dirname(os.path.dirname(real))
        dirs.append(os.path.join(prefix, "share", "katago"))
    dirs += ["/opt/homebrew/share/katago", "/usr/local/share/katago"]
    return dirs


def find_models(settings: Optional[Dict] = None, katago_path: Optional[str] = None
                ) -> Tuple[Optional[str], Optional[str]]:
    """返回 (主模型, 人类风格模型)。"""
    settings = settings or {}
    main = settings.get("katago_model") or None
    human = settings.get("katago_human_model") or None
    if main and not os.path.isfile(main):
        main = None
    if human and not os.path.isfile(human):
        human = None
    files: List[str] = []
    for d in _model_dirs(katago_path):
        for pat in ("*.bin.gz", "*.txt.gz", "*.bin"):
            files += glob.glob(os.path.join(d, pat))
    seen = set()
    files = [f for f in files if not (f in seen or seen.add(f))]
    humans = [f for f in files if "human" in os.path.basename(f).lower()]
    mains = [f for f in files if f not in humans]

    def pref(f: str) -> tuple:
        name = os.path.basename(f).lower()
        # 优先新一代 kata1 网络，其次中等体量（b18 > b28 > b40 > 其它）
        return (0 if name.startswith("kata1") else 1,
                0 if "b18" in name else 1 if "b28" in name else 2,
                -os.path.getmtime(f))
    mains.sort(key=pref)
    if main is None and mains:
        main = mains[0]
    if human is None and humans:
        human = humans[0]
    return main, human


def engine_status(settings: Optional[Dict] = None) -> Dict[str, Optional[str]]:
    exe = find_katago(settings)
    main, human = find_models(settings, exe)
    return {"katago": exe, "model": main, "human_model": human}


def is_available(settings: Optional[Dict] = None) -> bool:
    if settings is not None and not settings.get("use_katago", True):
        return False
    st = engine_status(settings)
    return bool(st["katago"] and st["model"])


# ---------- 配置 ----------
def _write_config(level: int, use_human: bool, extra: Optional[Dict] = None) -> str:
    _name, profile, pikl, visits = LEVELS[max(0, min(level, len(LEVELS) - 1))]
    d = _data_katago_dir()
    log_dir = d / "logs"
    log_dir.mkdir(exist_ok=True)
    cfg: Dict[str, object] = {
        "logDir": log_dir.as_posix(),
        "logAllGTPCommunication": "false",
        "logSearchInfo": "false",
        "logToStderr": "false",
        "rules": "chinese",
        "ponderingEnabled": "false",
        "allowResignation": "true",
        "resignThreshold": -0.97,
        "resignConsecTurns": 8,
        "resignMinScoreDifference": 30,
        "resignMinMovesPerBoardArea": 0.4,
        "numSearchThreads": 4,
        "nnCacheSizePowerOfTwo": 18,
        # OpenCL 调优文件等写到用户数据目录（程序目录可能不可写）
        "homeDataDir": d.as_posix(),
    }
    if use_human:
        # 参照 KataGo 官方 gtp_human5k_example.cfg
        cfg.update({
            "maxVisits": HUMAN_VISITS,
            "humanSLProfile": profile,
            "humanSLChosenMoveProp": 1.0,
            "humanSLChosenMoveIgnorePass": "true",
            "humanSLChosenMovePiklLambda": pikl,
            "humanSLRootExploreProbWeightless": 0.0,
            "humanSLRootExploreProbWeightful": 0.0,
            "humanSLPlaExploreProbWeightless": 0.0,
            "humanSLPlaExploreProbWeightful": 0.0,
            "humanSLOppExploreProbWeightless": 0.0,
            "humanSLOppExploreProbWeightful": 0.0,
            "humanSLCpuctExploration": 0.50,
            "humanSLCpuctPermanent": 0.2,
            "chosenMoveTemperatureEarly": 0.85,
            "chosenMoveTemperature": 0.70,
            "chosenMoveTemperatureHalflife": 80,
            "chosenMoveTemperatureOnlyBelowProb": 0.01,
            "rootNumSymmetriesToSample": 2,
            "useLcbForSelection": "false",
            "staticScoreUtilityFactor": 0.30,
            # 官方示例为 0。实测：胜负已定时目数不再影响“效用”，坏棋抑制失效，会出现一手亏 20+ 目的乱下；
            # 设为 0.5 后目数始终要紧，大亏着法消失。
            "dynamicScoreUtilityFactor": 0.50,
            "useUncertainty": "false",
            "subtreeValueBiasFactor": 0.0,
            "useNoisePruning": "false",
        })
    else:
        # 没有人类模型：只靠搜索量分档，温度很低，保证每一手都是“正经棋”
        cfg.update({
            "maxVisits": visits,
            "chosenMoveTemperatureEarly": 0.3,
            "chosenMoveTemperature": 0.1,
        })
    cfg.update(extra or {})
    lines = ["# 由 围棋·少儿版 自动生成，每次启动引擎都会覆盖"]
    lines += [f"{k} = {v}" for k, v in cfg.items()]
    path = d / f"weiqi_gtp_level{level}{'_human' if use_human else ''}.cfg"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


# ---------- GTP 进程 ----------
_live: Set["KataGo"] = set()


@atexit.register
def _kill_all() -> None:
    for e in list(_live):
        e.close()


class KataGo:
    """一个 KataGo GTP 进程。所有方法都会阻塞，应在后台线程调用。"""

    def __init__(self, level: int = 2, settings: Optional[Dict] = None,
                 prefer_human: bool = True, cmd: Optional[List[str]] = None,
                 extra_config: Optional[Dict] = None):
        self.level = level
        self.extra_config = extra_config
        self.settings = settings or {}
        self.prefer_human = prefer_human
        self._cmd_override = cmd          # 测试用：直接指定启动命令
        self.proc: Optional[subprocess.Popen] = None
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._lock = threading.Lock()
        self.uses_human = False
        self.exe = ""
        self.version = ""
        self.log_path = str(_data_katago_dir() / "katago_stderr.log")

    # ---------- 启动 / 关闭 ----------
    def start(self) -> None:
        if self._cmd_override:
            self._spawn(self._cmd_override)
            self._handshake()
            return
        exes = find_all_katago(self.settings)
        if not exes:
            raise EngineError("没有找到 KataGo 程序")
        last_err: Optional[Exception] = None
        for exe in exes:
            main, human = find_models(self.settings, exe)
            if not main:
                last_err = EngineError("没有找到 KataGo 模型文件")
                continue
            extra = dict(self.extra_config or {})
            if "eigen" in exe.lower() and "maxVisits" not in extra:
                extra["maxVisits"] = CPU_VISITS      # 纯 CPU 版较慢，少搜一些保证出棋速度
            attempts = ([True] if human and self.prefer_human else []) + [False]
            for use_human in attempts:
                cmd = [exe, "gtp", "-model", main, "-config",
                       _write_config(self.level, use_human, extra)]
                if use_human:
                    cmd += ["-human-model", human]
                try:
                    self._spawn(cmd)
                    self._handshake()
                    self.uses_human = use_human
                    self.exe = exe
                    return
                except EngineError as e:  # 旧版不认 -human-model / 显卡不可用等：换下一种再试
                    last_err = e
                    self.close()
        raise last_err or EngineError("KataGo 启动失败")

    def _spawn(self, cmd: List[str]) -> None:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._errf = open(self.log_path, "w", encoding="utf-8", errors="replace")
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._errf,
                text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)
        except OSError as e:
            raise EngineError(f"无法运行 KataGo：{e}")
        self._lines = queue.Queue()
        self._size = None
        threading.Thread(target=self._reader, args=(self.proc, self._lines), daemon=True).start()
        _live.add(self)

    @staticmethod
    def _reader(proc: subprocess.Popen, q: "queue.Queue[Optional[str]]") -> None:
        try:
            for line in proc.stdout:
                q.put(line.rstrip("\r\n"))
        except (OSError, ValueError):
            pass
        q.put(None)

    def _handshake(self) -> None:
        self.command("name", timeout=START_TIMEOUT)
        try:
            self.version = self.command("version", timeout=10)
        except EngineError:
            self.version = ""

    def close(self) -> None:
        _live.discard(self)
        p = self.proc
        self.proc = None
        if p is not None:
            try:
                if p.poll() is None:
                    try:
                        p.stdin.write("quit\n")
                        p.stdin.flush()
                    except (OSError, ValueError):
                        pass
                    try:
                        p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        p.kill()
            except OSError:
                pass
        f = getattr(self, "_errf", None)
        if f is not None:
            try:
                f.close()
            except OSError:
                pass

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _stderr_tail(self) -> str:
        try:
            text = Path(self.log_path).read_text(encoding="utf-8", errors="replace")
            lines = [l for l in text.splitlines() if l.strip()]
            return lines[-1][:120] if lines else ""
        except OSError:
            return ""

    # ---------- GTP ----------
    def command(self, cmd: str, timeout: float = MOVE_TIMEOUT) -> str:
        with self._lock:
            if not self.alive:
                raise EngineError("KataGo 未运行" + (f"：{self._stderr_tail()}" if self._stderr_tail() else ""))
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError) as e:
                raise EngineError(f"KataGo 通信失败：{e}")
            resp: List[str] = []
            started = False
            while True:
                try:
                    line = self._lines.get(timeout=timeout)
                except queue.Empty:
                    raise EngineError(f"KataGo 响应超时（{cmd.split()[0]}）")
                if line is None:
                    tail = self._stderr_tail()
                    raise EngineError("KataGo 已退出" + (f"：{tail}" if tail else ""))
                if not started:
                    if not line.strip():
                        continue
                    started = True
                if line == "":
                    break
                resp.append(line)
            text = "\n".join(resp)
            if text.startswith("?"):
                raise EngineError(f"KataGo 拒绝命令 {cmd}：{text[1:].strip()}")
            return text[1:].strip() if text.startswith("=") else text.strip()

    def sync(self, size: int, moves: List[Tuple[str, Move]], komi: float = KOMI) -> None:
        """把引擎局面同步为：空棋盘 + 依次落下 moves。"""
        if getattr(self, "_size", None) != size:
            self.command(f"boardsize {size}")
            self._size = size
        self.command("clear_board")
        self.command(f"komi {komi}")
        for color, mv in moves:
            self.command(f"play {'B' if color == BLACK else 'W'} {to_vertex(size, mv)}")

    def genmove(self, size: int, moves: List[Tuple[str, Move]], color: str,
                komi: float = KOMI) -> object:
        """返回 (r,c) / None(停一手) / 'resign'。"""
        mv = None
        for _ in range(OPENING_RETRIES + 1):
            self.sync(size, moves, komi)
            v = self.command(f"genmove {'B' if color == BLACK else 'W'}")
            mv = from_vertex(size, v)
            if not _lonely_edge_move(size, moves, mv):
                break
        return mv

    def dead_stones(self, size: int, moves: List[Tuple[str, Move]],
                    komi: float = KOMI) -> Set[Point]:
        self.sync(size, moves, komi)
        out: Set[Point] = set()
        text = self.command("final_status_list dead")
        for tok in text.split():
            try:
                p = from_vertex(size, tok)
            except (ValueError, IndexError):
                continue
            if isinstance(p, tuple):
                out.add(p)
        return out


def _lonely_edge_move(size: int, moves: List[Tuple[str, Move]], mv: object) -> bool:
    """布局阶段（盘上子还很少）下在一线、且周围 2 路内没有任何棋子——典型的“乱下”。"""
    if not isinstance(mv, tuple):
        return False
    r, c = mv
    if min(r, c, size - 1 - r, size - 1 - c) != 0:
        return False
    placed = [m for _c, m in moves if m is not None]
    if len(placed) >= size * size // 4:
        return False          # 已到中后盘：一线可能是收官，不管
    return all(abs(pr - r) + abs(pc - c) > 2 for pr, pc in placed)


def open_folder(path: str) -> None:
    """在系统文件管理器中打开文件夹。"""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


def katago_folder() -> str:
    return str(_data_katago_dir())
