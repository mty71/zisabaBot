import logging
import os
import re
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("DiscordBot")

raw_role_id = os.getenv("DEFAULT_ROLE_ID", "0")
clean_role_id = re.sub(r"\D", "", raw_role_id)
DEFAULT_ROLE_ID = int(clean_role_id) if clean_role_id else 0


class AutoRole(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.debug(
            f"👤 [MemberJoin] {member.display_name} (ID: {member.id}) が参加しました。"
        )

        if DEFAULT_ROLE_ID == 0:
            logger.warning(
                "⚠️ [AutoRole] DEFAULT_ROLE_ID が正しく設定されていません。"
            )
            return

        guild = member.guild
        role = guild.get_role(DEFAULT_ROLE_ID)

        if role is None:
            logger.error(
                f"❌ [AutoRole] ロールID ({DEFAULT_ROLE_ID}) が見つかりませんでした。"
            )
            return

        try:
            await member.add_roles(
                role, reason="新規参加者へのデフォルトロール自動付与"
            )
            logger.info(
                f"✅ [AutoRole] {member.display_name} にロール「{role.name}」を付与しました。"
            )
        except discord.Forbidden:
            logger.error(
                "❌ [AutoRole] 権限不足: Botのロール順位か「ロールの管理」権限を確認してください。"
            )
        except Exception as e:
            logger.error(
                f"❌ [AutoRole] ロール付与エラー: {e}", exc_info=True
            )


async def setup(bot):
    await bot.add_cog(AutoRole(bot))