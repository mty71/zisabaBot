import logging
import os
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button
from dotenv import load_dotenv

from .utils import build_status_embed, load_vc_data, save_vc_data
from .views import PortalView, VcControlView

load_dotenv()
logger = logging.getLogger("DiscordBot")


def get_env_id(key: str) -> int:
    val = os.getenv(key, "0")
    try:
        return int(val)
    except ValueError:
        logger.error(
            f"⚠️ [環境変数エラー] {key} の値 '{val}' を数値に変換できません。"
        )
        return 0


CREATE_CHANNEL_ID = get_env_id("CREATE_CHANNEL_ID")
CATEGORY_ID = get_env_id("CATEGORY_ID")


class PrivateVC(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.vc_data = load_vc_data()

    def cog_unload(self):
        save_vc_data(self.vc_data)
        logger.info(
            "💾 [PrivateVC] 終了検知: 最新のVCデータをJSONへ保存しました。"
        )

    def get_user_vc(
        self, member: discord.Member
    ) -> discord.VoiceChannel | None:
        if member.voice and member.voice.channel:
            ch_id_str = str(member.voice.channel.id)
            if ch_id_str in self.vc_data:
                return member.voice.channel
        return None

    @commands.command(name="setup_portal")
    @commands.has_permissions(administrator=True)
    async def setup_portal_command(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🔐 プラチャポータル",
            description="🔔 下のボタンから、プライベートツールを作成できます！",
            color=discord.Color.from_rgb(180, 50, 50),
        )
        embed.add_field(
            name="の使い方",
            value=(
                "1. **「自分のルーム作成」** を押す\n"
                "2. ルーム名を入力\n"
                "3. 非表示の状態は招待か宣伝でユーザーを増やす\n"
                "4. 退出したい時は切断して、誰もいなければ消される(部屋を保存を押していなければ)"
            ),
            inline=False,
        )
        view = PortalView(cog_ref=self)
        await ctx.send(embed=embed, view=view)
        try:
            await ctx.message.delete()
        except Exception:
            pass

    @commands.command(name="vc")
    async def show_panel_command(self, ctx: commands.Context):
        channel = self.get_user_vc(ctx.author)
        if not channel:
            return await ctx.send(
                "❌ 管理対象のボイスチャンネルに参加した状態で実行してください。",
                delete_after=5,
            )

        try:
            await ctx.message.delete()
        except Exception:
            pass

        ch_id_str = str(channel.id)
        channel_data = self.vc_data[ch_id_str]

        view = VcControlView(
            voice_channel=channel,
            owner_id=channel_data["owner_id"],
            cog_ref=self,
        )
        embed = build_status_embed(channel, channel_data, ctx.guild)
        await ctx.send(embed=embed, view=view)

    vc_group = app_commands.Group(
        name="vc", description="プライベートVC操作コマンド"
    )

    @vc_group.command(
        name="panel", description="管理パネルを表示（自分にしか見えません）"
    )
    async def slash_panel(self, interaction: discord.Interaction):
        channel = self.get_user_vc(interaction.user)
        if not channel:
            return await interaction.response.send_message(
                "❌ 管理対象のボイスチャンネルに参加した状態で実行してください。",
                ephemeral=True,
            )

        ch_id_str = str(channel.id)
        channel_data = self.vc_data[ch_id_str]

        view = VcControlView(
            voice_channel=channel,
            owner_id=channel_data["owner_id"],
            cog_ref=self,
        )
        embed = build_status_embed(channel, channel_data, interaction.guild)
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(PortalView(cog_ref=self))

        for channel_id_str, data in list(self.vc_data.items()):
            ch_id = int(channel_id_str)
            channel = self.bot.get_channel(ch_id)
            if channel:
                view = VcControlView(
                    voice_channel=channel,
                    owner_id=data["owner_id"],
                    cog_ref=self,
                )
                if data.get("is_saved", False):
                    for child in view.children:
                        if (
                            isinstance(child, Button)
                            and child.label == "💾 部屋を保存/解除"
                        ):
                            child.style = discord.ButtonStyle.success
                self.bot.add_view(view)
            else:
                del self.vc_data[channel_id_str]
        save_vc_data(self.vc_data)
        logger.info(
            "✅ プライベートVCデータおよびポータルViewをJSONから登録しました。"
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        logger.debug(
            f"🔍 [Cog VoiceState] User: {member.display_name} | AfterChannel: {after.channel.id if after.channel else None} | TargetID: {CREATE_CHANNEL_ID}"
        )

        if after.channel and after.channel.id == CREATE_CHANNEL_ID:
            logger.info(
                f"🚀 [VC自動作成] {member.display_name} が作成用VCに入室しました。"
            )
            guild = member.guild
            category = guild.get_channel(CATEGORY_ID)

            if not category:
                logger.error(
                    f"❌ [エラー] CATEGORY_ID ({CATEGORY_ID}) が見つかりません。"
                )
                return

            overwrites = {
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    manage_channels=True,
                    mute_members=True,
                    deafen_members=True,
                    move_members=True,
                )
            }

            try:
                channel = await guild.create_voice_channel(
                    name=f"🔊 {member.display_name}の部屋",
                    category=category,
                    overwrites=overwrites,
                )
                logger.info(
                    f"✅ [VC作成完了] {channel.name} (ID: {channel.id})"
                )
            except Exception as e:
                logger.error(
                    f"❌ [チャンネル作成失敗]: {e}", exc_info=True
                )
                return

            ch_id_str = str(channel.id)
            channel_data = {
                "owner_id": member.id,
                "moderators": [],
                "is_saved": False,
            }
            self.vc_data[ch_id_str] = channel_data
            save_vc_data(self.vc_data)

            try:
                await member.move_to(channel)
            except Exception as e:
                logger.warning(f"⚠️ [メンバー移動失敗]: {e}")

            try:
                view = VcControlView(
                    voice_channel=channel, owner_id=member.id, cog_ref=self
                )
                embed = build_status_embed(channel, channel_data, guild)
                await channel.send(embed=embed, view=view)
            except Exception as e:
                logger.error(f"⚠️ [パネル送信失敗]: {e}")

        if before.channel and str(before.channel.id) in self.vc_data:
            ch_id_str = str(before.channel.id)
            channel_data = self.vc_data[ch_id_str]

            if len(before.channel.members) == 0:
                if not channel_data.get("is_saved", False):
                    del self.vc_data[ch_id_str]
                    save_vc_data(self.vc_data)
                    try:
                        await before.channel.delete()
                        logger.info(
                            f"🗑️ [VC自動削除] 空になった部屋 {before.channel.name} を削除しました。"
                        )
                    except Exception as e:
                        logger.error(f"❌ [VC削除失敗]: {e}")


async def setup(bot):
    await bot.add_cog(PrivateVC(bot))