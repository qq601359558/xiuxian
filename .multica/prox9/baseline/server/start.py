"""一键启动局域网服（避免 shell 引号问题）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.app import main

if __name__ == "__main__":
    main()
