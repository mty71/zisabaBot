import json
import logging
import os
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("DiscordBot")
ROLE_DATA_PATH = "./data/custom_roles.json"


def load_role_data():
    if not os.path.exists(ROLE_DATA_PATH):
        logger.debug(
            f"📂 [SelfRoleManager] 保存データが存在しないため新規作成します: {ROLE_DATA_PATH}"
        )
        return {}
    try:
        with open(ROLE_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug(
                f"📂 [SelfRoleManager] {len(data)} 件のカスタムロールデータを読み込みました。"
            )
            return data
    except Exception as e:
        logger.error(f"❌ [SelfRoleManager] ロールデータの読み込み失敗: {e}")
        return {}


def save_role_data(data):
    os.makedirs(os.path.dirname(ROLE_DATA_PATH), exist_ok=True)
    try:
        with open(ROLE_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            logger.debug("💾 [SelfRoleManager] カスタムロールデータをJSONへ保存しました。")
    except Exception as e:
        logger.error(f"❌ [SelfRoleManager] ロールデータの保存失敗: {e}")


class SelfRoleManager(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.role_data = load_role_data()

    role_group = app_commands.Group(
        name="myrole", description="自分が所有・管理する専用ロールの操作"
    )

    # 1. 専用ロールの作成 (自分の最高ロールの直下に作成)
    @role_group.command(name="create", description="自分が管理できる専用ロールを作成します")
    @app_commands.describe(
        name="作成するロール名",
        color_code="カラーコード (例: #FF0000 または RED)"
    )
    async def create_role(
        self, interaction: discord.Interaction, name: str, color_code: str = "#99AAB5"
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        logger.debug(
            f"🔍 [MyRole Create] RequestUser: {user.display_name} (ID: {user.id}) | RoleName: {name} | Color: {color_code}"
        )

        # カラーコードの変換
        try:
            if color_code.startswith("#"):
                color = discord.Color(int(color_code[1:], 16))
            else:
                color = getattr(
                    discord.Color, color_code.lower(), lambda: discord.Color.default()
                )()
        except Exception as e:
            logger.warning(
                f"⚠️ [MyRole Create] カラーコード判定エラー: {e} -> デフォルトカラーを適用"
            )
            color = discord.Color.default()

        # 作成者の最高位置を取得 (Bot位置と作成者位置の低い方を上限に設定)
        user_top_position = user.top_role.position
        bot_top_position = guild.me.top_role.position

        logger.debug(
            f"📊 [MyRole Position Check] UserTopPos: {user_top_position} ({user.top_role.name}) | BotTopPos: {bot_top_position} ({guild.me.top_role.name})"
        )

        target_position = min(user_top_position, bot_top_position) - 1
        if target_position <= 1:
            logger.warning(
                f"⚠️ [MyRole Create] 調整余地不足ため作成を中断 (TargetPos: {target_position})"
            )
            return await interaction.followup.send(
                "❌ ロールを作成できる階層の調整余地がありません。Botまたはあなたのロール順位を上げてください。",
                ephemeral=True,
            )

        try:
            # ロール作成
            new_role = await guild.create_role(
                name=name,
                color=color,
                reason=f"ユーザー {user.display_name} による専用ロール作成",
            )

            # 作成したロールの位置を自分の直下に移動
            await new_role.edit(position=target_position)

            # 自分の作成データとして保存
            str_role_id = str(new_role.id)
            self.role_data[str_role_id] = {
                "owner_id": user.id,
                "created_at": str(new_role.created_at),
            }
            save_role_data(self.role_data)

            # 作成者にロールを自動付与
            await user.add_roles(new_role)

            logger.info(
                f"✅ [MyRole 作成完了] Role: {new_role.name} (ID: {new_role.id}) | Owner: {user.display_name} | Pos: {target_position}"
            )

            await interaction.followup.send(
                f"✅ 専用ロール **{new_role.name}** を作成し、あなたに付与しました！\n"
                f"（位置: {user.top_role.name} の直下 / 位置番号: {target_position}）",
                ephemeral=True,
            )
        except discord.Forbidden:
            logger.error(
                "❌ [MyRole Create] 権限不足: Botのロール順位か「ロールの管理」権限を確認してください。"
            )
            await interaction.followup.send(
                "❌ 権限が不足しています。Botのロールが操作対象より上にあるか確認してください。",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(
                f"❌ [MyRole Create Error]: {e}", exc_info=True
            )
            await interaction.followup.send(
                f"❌ エラーが発生しました: {e}", ephemeral=True
            )

    # 2. 自分が作ったロールの削除
    @role_group.command(name="delete", description="自分が作成した専用ロールを削除します")
    @app_commands.describe(role="削除する自分が作成したロール")
    async def delete_role(
        self, interaction: discord.Interaction, role: discord.Role
    ):
        await interaction.response.defer(ephemeral=True)
        str_role_id = str(role.id)

        logger.debug(
            f"🔍 [MyRole Delete] RequestUser: {interaction.user.display_name} | TargetRole: {role.name} (ID: {role.id})"
        )

        # 所有権の検証
        role_info = self.role_data.get(str_role_id)
        if not role_info or (
            role_info["owner_id"] != interaction.user.id
            and not interaction.user.guild_permissions.administrator
        ):
            logger.warning(
                f"⚠️ [MyRole Delete 拒否] 所有権のないロール削除試行: {role.name}"
            )
            return await interaction.followup.send(
                "❌ あなたが作成したロールのみ削除できます。", ephemeral=True
            )

        try:
            await role.delete(
                reason=f"所有者 {interaction.user.display_name} による削除"
            )
            del self.role_data[str_role_id]
            save_role_data(self.role_data)

            logger.info(
                f"🗑️ [MyRole 削除完了] Role: {role.name} | ExecutedBy: {interaction.user.display_name}"
            )

            await interaction.followup.send(
                f"🗑️ ロール **{role.name}** を削除しました。", ephemeral=True
            )
        except Exception as e:
            logger.error(
                f"❌ [MyRole Delete Error]: {e}", exc_info=True
            )
            await interaction.followup.send(
                f"❌ 削除に失敗しました: {e}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(SelfRoleManager(bot))