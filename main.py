import os
import asyncio
import discord
from discord.ext import commands
from watchfiles import awatch

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 初回Cog取得
async def load_all_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                print(f"[LOAD] {cog_name}")
            except Exception as e:
                print(f"[ERROR] {cog_name} のロード失敗: {e}")

# ホットロード監視タスク
async def cog_watcher():
    await bot.wait_until_ready()
    print("🔥 ホットロード監視中... (cogs/ 内の変更を自動検出します)")
    async for changes in awatch("./cogs"):
        for change_type, path in changes:
            if path.endswith(".py"):
                # ファイルパスからモジュール名を取得 (例: cogs/private_vc.py -> cogs.private_vc)
                filename = os.path.basename(path)[:-3]
                cog_name = f"cogs.{filename}"
                try:
                    # すでにロードされていればリロード、なければ新規ロード
                    if cog_name in bot.extensions:
                        await bot.reload_extension(cog_name)
                        print(f"🔄 [RELOAD] {cog_name}")
                    else:
                        await bot.load_extension(cog_name)
                        print(f"✨ [LOAD] {cog_name}")
                except Exception as e:
                    print(f"❌ [ERROR] {cog_name} のリロード失敗: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")

async def main():
    async with bot:
        await load_all_extensions()
        # ホットロード監視を非同期タスクとして開始
        bot.loop.create_task(cog_watcher())
        await bot.start("YOUR_BOT_TOKEN_HERE")

if __name__ == "__main__":
    asyncio.run(main())