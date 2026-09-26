import os

# .env ファイルの内容
env_content = """# Discord Bot Settings
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE

# Private VC Settings
CREATE_CHANNEL_ID=123456789012345678
CATEGORY_ID=123456789012345678

# Command Prefix (Optional)
COMMAND_PREFIX=!
"""

# .env.example ファイルの内容（Gitコミット用）
env_example_content = """# Discord Bot Settings
DISCORD_BOT_TOKEN=

# Private VC Settings
CREATE_CHANNEL_ID=
CATEGORY_ID=

# Command Prefix
COMMAND_PREFIX=!
"""

# .env の作成（既に存在する場合は上書きを防止）
if not os.path.exists(".env"):
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    print("✅ `.env` を作成しました。実際のトークンやIDに書き換えてください。")
else:
    print("⚠️ `.env` は既に存在するためスキップしました。")

# .env.example の作成
with open(".env.example", "w", encoding="utf-8") as f:
    f.write(env_example_content)
print("✅ `.env.example` を作成しました。")

# .gitignore に .env を追加
gitignore_path = ".gitignore"
if os.path.exists(gitignore_path):
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    if ".env" not in content:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n.env\n")
        print("✅ `.gitignore` に `.env` を追加しました。")
else:
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write(".env\n")
    print("✅ `.gitignore` を作成し `.env` を登録しました。")