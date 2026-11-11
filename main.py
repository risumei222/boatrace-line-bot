import os
import re
import sys
import glob
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Optional

# 必要なパッケージの自動インストール
for pkg in ["pandas", "requests"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import pandas as pd

# Botのメインコントローラーから処理をインポート
from bot_controller import run_mode_2_post_exhibition, parse_race_input

def process_cli_test(user_text: str):
    """
    ローカルテスト用の関数（LINEを通さずにターミナル等で実行する場合）
    """
    print(f"入力テスト: {user_text}")
    jcd, rno = parse_race_input(user_text)
    if not jcd or not rno:
        print("エラー: 会場名またはレース番号が正しく認識できませんでした。")
        return

    try:
        result = run_mode_2_post_exhibition(user_text)
        print("\n=== 予想結果 ===")
        print(result)
        print("================")
    except Exception as e:
        print(f"処理中にエラーが発生しました: {e}")

if __name__ == "__main__":
    # GitHubやRender上では app.py が動くため、この main.py は手動テスト用として機能します。
    print("Boatrace LINE Bot - ローカルテストモード")
    
    if len(sys.argv) > 1:
        test_input = sys.argv[1]
        process_cli_test(test_input)
    else:
        print("実行例: python main.py '大村5R'")
