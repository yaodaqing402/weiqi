"""PyInstaller 打包入口：用绝对导入，避免作为顶层脚本时的相对导入错误。"""
import sys

from weiqi.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
