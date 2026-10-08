# 围棋 · 少儿版 ⚫⚪

一款适合小朋友的围棋游戏，界面清爽、鼠标操作、带段位成长系统，从“吃子棋”启蒙到正式对局，陪孩子一步步提升棋力。支持 **Windows** 与 **macOS**。

![版本](https://img.shields.io/badge/version-1.0.0-black) ![平台](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)

## ✨ 功能特色

- 🧒 **两种玩法**
  - **吃子棋**：先吃够 1 / 3 / 5 子的一方获胜，少儿围棋启蒙最常用的玩法。
  - **正式对局**：中国规则数子法，黑贴 3¾ 子（7.5 目）；双方连续停一手后进入数子，可点击标记死子，自动算出胜负。
- 📐 **三种棋盘**：9 路 / 13 路 / 19 路，从小棋盘起步逐步过渡到正式棋盘。
- 🎯 **人机对战**：五档难度（入门 → 初级 → 中级 → 高级 → 大师），可选执黑先下或执白后下。
  - 正式对局由**内置的 KataGo** 引擎陪下，五档分别模仿 **20 级 / 15 级 / 10 级 / 5 级 / 业余 1 段** 的人类下法，且经过“不乱下”调校（见下文）。
  - 吃子棋由内置战术 AI 陪下（会提子、逃子、叫吃、征子）。
- 🏅 **段位成长系统**：赢棋积分晋级（小棋童 → 25 级 → … → 业余初段 → 围棋小国手），难度越高得分越多，输棋只小幅扣分。
- 👥 **双人对战**：同一台电脑上两人轮流下。
- 🌐 **局域网联机**：两台电脑连到同一 Wi-Fi，一台创建房间（执黑、决定玩法和棋盘）、一台输入 IP 加入即可对弈，数子时双方同步标记死子。
- 📚 **吃子练习**：叫吃提子、双叫吃、征子、枪吃、倒扑五关，每关带思路提示，白棋会拼命逃跑。
- 📖 **棋谱记录与回放**：每盘自动保存，支持逐步 / 自动回放、显示手数，可删除。
- 💡 **贴心提示**：被叫吃的棋子会亮橙色圈；打劫、禁着点会弹出说明；随时可悔棋、请求提示。
- 🔊 **落子音效**：落子、提子、叫吃、胜负均有音效（可在菜单开关）。

## 🚀 快速开始

### 方式一：下载打包好的应用（推荐）

前往 [Releases](../../releases) 下载对应系统的压缩包，解压后运行：
- **Windows**：解压后进入文件夹，双击 `WeiQi_vX.Y.Z.exe`
- **macOS**：解压得到 `WeiQi_vX.Y.Z.app`，右键 → 打开（首次需在「系统设置 → 隐私与安全性」允许运行）

### 方式二：源码运行

需要 Python 3.10+。

- **macOS**：双击 `启动围棋.command`（首次会自动装依赖）
- **Windows**：双击 `启动围棋.bat`

或手动：

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m weiqi
```

## 🤖 AI 引擎（KataGo，已内置）

安装包**自带** KataGo 引擎和两个模型，开箱即用，不需要另外安装：

| 内置内容 | 说明 |
|---|---|
| KataGo 程序 | macOS：Metal 版（Apple 芯片显卡加速）；Windows：OpenCL 显卡版 + Eigen-AVX2 CPU 版，显卡不可用时自动换 CPU 版 |
| 主模型 | `kata1-b18c384nbt`：负责搜索、判断好坏、数子时判断死子 |
| 人类风格模型 | `b18c384nbt-humanv0`：让各难度按“20 级～业余 1 段”模仿人类下法 |

**不乱下**：人类风格模型挑出的每一手都会先经 KataGo 搜索“验货”，明显亏损的着法会被压低概率（`humanSLChosenMovePiklLambda`），
并且始终计较目数（`dynamicScoreUtilityFactor`），胜负已定时也不会随手乱下；布局阶段孤零零的一线着法会被直接否决。
实测（9 路自对弈、强 KataGo 逐手评估）：亏 10 目以上的着法比例从调整前的 3%～18% 降到 0%～3%。

- Windows 首次使用显卡版会自动调优，可能需要等一两分钟。
- macOS 内置的是 Apple 芯片（M 系列）版本；Intel 芯片的 Mac 上内置引擎无法运行，正式对局会退回较弱的内置 AI（可自行 `brew install katago`，会被自动识别）。
- 想换用自己安装的 KataGo / 其它模型：主菜单 →「AI 引擎」→ 打开引擎文件夹放入文件，或在 `settings.json` 里填写 `katago_path`、`katago_model`、`katago_human_model`。
- 引擎文件夹：macOS `~/Library/Application Support/WeiQi/katago/`，Windows `%APPDATA%\WeiQi\katago\`。

## 🎮 操作说明

| 操作 | 说明 |
|------|------|
| 点击交叉点 | 落子（鼠标悬停处会显示空心预览）|
| 停一手 | 虚着；正式对局双方连续停一手即进入数子 |
| 数子阶段点击棋子 | 把整块棋标为死子（打叉）/ 取消；小方块表示每个点归谁 |
| 确认结果 / 继续下棋 | 确认数子胜负 / 发现还没下完，回到对局 |
| 悔棋 | 撤回上一步（人机模式撤回一整回合）|
| 提示 | 高亮一个推荐着点 |
| 回放里 ← / → | 上一手 / 下一手 |
| F11 或 Cmd/Ctrl+F | 切换全屏 |

## 🗂️ 项目结构

```
src/weiqi/
├── engine/        # 核心引擎：棋盘规则（提子/禁着/打劫/数子）、战术读子、内置 AI、KataGo(GTP) 接入
├── game/          # 业务层：控制器、记谱、棋谱记录、段位成长、吃子练习题
├── net/           # 局域网联机（TCP socket）
└── ui/            # 图形界面（pygame）：主题、音效、控件、棋盘绘制、各场景
tests/             # 回归测试（规则 / 读子 / 练习题 / AI / KataGo 通信 / 界面流程）
packaging/         # PyInstaller 打包脚本
.github/workflows/ # GitHub Actions：打 tag 自动测试、构建 Win/Mac 并发布 Release
```

## 🧪 开发与测试

```bash
pip install -r requirements.txt pytest
python -m pytest tests/
```

测试用 `tests/fake_gtp.py` 模拟 KataGo 的 GTP 应答，不需要真的安装 KataGo。

## 📦 打包

```bash
pip install pyinstaller
brew install katago                    # 仅 macOS：提供 Metal 版 KataGo
python packaging/fetch_katago.py       # 下载模型、准备 vendor/katago（约 200MB，已下载会跳过）
pyinstaller packaging/weiqi.spec --clean -y
# 产物在 dist/ 下（含 KataGo，约 270MB）
```

源码运行时如果存在 `vendor/katago`，也会优先使用其中的 KataGo。

## 📜 许可证

MIT License
