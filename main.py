import asyncio
import logging
import os
import signal
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
from watchfiles import awatch

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "False").lower() == "true"

# --- ロガーの設定 ---
logger = logging.getLogger("DiscordBot")
logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# コンソール出力ハンドラ
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ファイル保存ハンドラ (LOG_TO_FILE=True の場合)
if LOG_TO_FILE:
    os.makedirs("./logs", exist_ok=True)
    file_handler = logging.FileHandler(
        "./logs/bot.log", encoding="utf-8", mode="a"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True


class CustomBot(commands.Bot):

    async def setup_hook(self):
        await load_all_extensions(self)

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(
                f"⚡ ギルド {GUILD_ID} に {len(synced)} 個のスラッシュコマンドを同期しました。"
            )
        else:
            synced = await self.tree.sync()
            logger.info(
                f"🌐 グローバルに {len(synced)} 個のスラッシュコマンドを同期しました。"
            )


bot = CustomBot(command_prefix=PREFIX, intents=intents)


def get_cog_modules():
    """cogs/ 直下の .py と サブフォルダ内の vc_main.py 等のエントリーポイントを検出"""
    modules = []
    for root, _, files in os.walk("./cogs"):
        for filename in files:
            if not filename.endswith(".py") or filename.startswith("__"):
                continue

            rel_path = os.path.relpath(os.path.join(root, filename), ".")
            module_name = rel_path.replace(os.sep, ".")[:-3]

            if root == "./cogs":
                modules.append(module_name)
            elif filename in ["vc_main.py", "main.py"]:
                modules.append(module_name)
    return modules


async def load_all_extensions(bot_instance):
    for cog_module in get_cog_modules():
        try:
            await bot_instance.load_extension(cog_module)
            logger.info(f"[LOAD] {cog_module}")
        except Exception as e:
            logger.error(
                f"[ERROR] {cog_module} のロード失敗: {e}", exc_info=DEBUG_MODE
            )


async def cog_watcher():
    await bot.wait_until_ready()
    logger.info("🔥 ホットロード監視中... (cogs/ 内の変更を自動検出します)")
    async for changes in awatch("./cogs"):
        for _, path in changes:
            if not path.endswith(".py") or os.path.basename(path).startswith(
                "__"
            ):
                continue

            for cog_module in get_cog_modules():
                try:
                    if cog_module in bot.extensions:
                        await bot.reload_extension(cog_module)
                        logger.info(f"🔄 [RELOAD] {cog_module}")
                    else:
                        await bot.load_extension(cog_module)
                        logger.info(f"✨ [LOAD] {cog_module}")

                    if GUILD_ID:
                        guild = discord.Object(id=GUILD_ID)
                        bot.tree.clear_commands(guild=guild)
                        bot.tree.copy_global_to(guild=guild)
                        await bot.tree.sync(guild=guild)
                    else:
                        await bot.tree.sync()
                    logger.info("🔄 スラッシュコマンドを再同期しました。")
                except Exception as e:
                    logger.error(
                        f"❌ [ERROR] {cog_module} のリロード失敗: {e}",
                        exc_info=DEBUG_MODE,
                    )


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"🔧 デバッグモード: {'ON' if DEBUG_MODE else 'OFF'}")
    logger.info(
        f"📝 ログファイル保存: {'ON (logs/bot.log)' if LOG_TO_FILE else 'OFF'}"
    )


@bot.event
async def on_voice_state_update(member, before, after):
    logger.debug(
        f"🔔 [VoiceStateUpdate] Member: {member.display_name} | Before: {before.channel} | After: {after.channel}"
    )


async def main():
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info(
            "\n🛑 終了シグナルを受信しました。シャットダウン処理を開始します..."
        )
        stop_event.set()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass

    async with bot:
        bot.loop.create_task(cog_watcher())
        bot_task = loop.create_task(bot.start(TOKEN))

        done, pending = await asyncio.wait(
            [bot_task, loop.create_task(stop_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stop_event.is_set():
            logger.info("💾 データを保存してBotをクローズします...")
            await bot.close()
            for task in pending:
                task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 プログラムが終了しました。")