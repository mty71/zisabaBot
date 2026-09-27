import json
import logging
import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("DiscordBot")

ROLE_DATA_PATH = "./data/custom_roles.json"
BASE_ROLE_ID = int(os.getenv("BASE_ROLE_ID", "0"))


def load_role_data():
    if not os.path.exists(ROLE_DATA_PATH):
        return {}
    try:
        with open(ROLE_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
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

    # 1. 専用ロールの作成 (指定された仕切りロールの直下に作成)
    @role_group.command(name="create", description="仕切りロールの直下に専用ロールを作成します")
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
            f"🔍 [MyRole Create] User: {user.display_name} | RoleName: {name} | Color: {color_code}"
        )

        # 基準ロールの特定 (ID一致、または名前「---この以下自動ロール---」で検索)
        base_role = guild.get_role(BASE_ROLE_ID)
        if not base_role:
            base_role = discord.utils.get(guild.roles, name="---この以下自動ロール---")

        if not base_role:
            logger.error("❌ [MyRole Create] 基準となる仕切りロールが見つかりません。")
            return await interaction.followup.send(
                "❌ 基準となる仕切りロール（---この以下自動ロール---）が見つかりませんでした。管理者にお問い合わせください。",
                ephemeral=True,
            )

        # カラーコードの変換
        try:
            if color_code.startswith("#"):
                color = discord.Color(int(color_code[1:], 16))
            else:
                color = getattr(
                    discord.Color, color_code.lower(), lambda: discord.Color.default()
                )()
        except Exception:
            color = discord.Color.default()

        # 基準ロールの1つ下の位置を算出
        target_position = max(1, base_role.position - 1)

        logger.debug(
            f"📊 [MyRole Position] BaseRole: {base_role.name} (Pos: {base_role.position}) -> TargetPos: {target_position}"
        )

        try:
            # ロール作成
            new_role = await guild.create_role(
                name=name,
                color=color,
                reason=f"ユーザー {user.display_name} による専用ロール作成",
            )

            # 位置を仕切りロールの直下に設定
            await new_role.edit(position=target_position)

            # 作成データとして保存
            str_role_id = str(new_role.id)
            self.role_data[str_role_id] = {
                "owner_id": user.id,
                "created_at": str(new_role.created_at),
            }
            save_role_data(self.role_data)

            # 作成者本人にロールを付与
            await user.add_roles(new_role)

            logger.info(
                f"✅ [MyRole 作成完了] Role: {new_role.name} (ID: {new_role.id}) | Owner: {user.display_name} | Pos: {target_position}"
            )

            await interaction.followup.send(
                f"✅ 仕切りロール **{base_role.name}** の下に専用ロール **{new_role.name}** を作成し、あなたに付与しました！",
                ephemeral=True,
            )
        except discord.Forbidden:
            logger.error("❌ [MyRole Create] Botのロール権限が不足しています。")
            await interaction.followup.send(
                "❌ Botの権限が不足しています。Botのロール順位を仕切りロールより上に移動してください。",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"❌ [MyRole Create Error]: {e}", exc_info=True)
            await interaction.followup.send(f"❌ エラーが発生しました: {e}", ephemeral=True)

    # 2. 削除コマンド用 Autocomplete (自分が作成したロールのみ候補に表示)
    async def user_created_roles_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        self.role_data = load_role_data()
        user_id = interaction.user.id
        guild = interaction.guild

        choices = []
        for role_id_str, data in self.role_data.items():
            # 自分が作成したロール（または管理者）のみを抽出
            if data.get("owner_id") == user_id or interaction.user.guild_permissions.administrator:
                role = guild.get_role(int(role_id_str))
                if role and current.lower() in role.name.lower():
                    choices.append(app_commands.Choice(name=role.name, value=role_id_str))

        return choices[:25]  # Discordの仕様上、候補は最大25個

    # 3. 自分が作ったロールの削除
    @role_group.command(name="delete", description="自分が作成した専用ロールを削除します")
    @app_commands.describe(role_id="削除する自分が作成したロール")
    @app_commands.autocomplete(role_id=user_created_roles_autocomplete)
    async def delete_role(
        self, interaction: discord.Interaction, role_id: str
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # IDからロールオブジェクトを取得
        role = guild.get_role(int(role_id)) if role_id.isdigit() else None
        if not role:
            return await interaction.followup.send(
                "❌ 該当するロールが見つからないか、既に削除されています。", ephemeral=True
            )

        role_info = self.role_data.get(role_id)
        if not role_info or (
            role_info["owner_id"] != interaction.user.id
            and not interaction.user.guild_permissions.administrator
        ):
            return await interaction.followup.send(
                "❌ あなたが作成したロールのみ削除できます。", ephemeral=True
            )

        try:
            role_name = role.name
            await role.delete(
                reason=f"所有者 {interaction.user.display_name} による削除"
            )
            del self.role_data[role_id]
            save_role_data(self.role_data)

            logger.info(
                f"🗑️ [MyRole 削除完了] Role: {role_name} | ExecutedBy: {interaction.user.display_name}"
            )

            await interaction.followup.send(
                f"🗑️ ロール **{role_name}** を削除しました。", ephemeral=True
            )
        except Exception as e:
            logger.error(f"❌ [MyRole Delete Error]: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ 削除に失敗しました: {e}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(SelfRoleManager(bot))