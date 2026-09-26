import logging
import os
import discord
from discord.ui import Button, Modal, Select, TextInput, UserSelect, View
from dotenv import load_dotenv

from .utils import build_status_embed, save_vc_data

load_dotenv()
logger = logging.getLogger("DiscordBot")
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "0"))


# --- VC参加者宛て DM送信モーダル ---
class SendVcDmModal(Modal):

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(title="📩 VC参加メンバーへDM送信")
        self.channel = channel

        self.message_input = TextInput(
            label="送信するメッセージを入力してください",
            style=discord.TextStyle.paragraph,
            placeholder="例: 次のゲームの部屋番号は 1234 です！",
            max_length=1000,
            required=True,
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        members = [m for m in self.channel.members if not m.bot]

        if not members:
            return await interaction.followup.send(
                "❌ 現在ボイスチャンネルに参加しているメンバーがいません。",
                ephemeral=True,
            )

        embed = discord.Embed(
            title=f"📩 {self.channel.name} からの通知",
            description=self.message_input.value,
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text=f"送信者: {interaction.user.display_name} | サーバー: {interaction.guild.name}"
        )

        success_count = 0
        failed_count = 0

        for member in members:
            try:
                await member.send(embed=embed)
                success_count += 1
            except discord.Forbidden:
                failed_count += 1
            except Exception as e:
                logger.error(
                    f"❌ [VC DM送信エラー] {member.display_name}: {e}"
                )
                failed_count += 1

        await interaction.followup.send(
            f"📨 **DM送信結果**\n"
            f"対象VC: {self.channel.name}\n"
            f"・成功: **{success_count}** 名\n"
            f"・失敗（受信拒否など）: **{failed_count}** 名",
            ephemeral=True,
        )


# --- ルーム作成モーダル ---
class CreateRoomModal(Modal):

    def __init__(self, cog_ref, is_hidden: bool):
        title_text = "非表示ルーム作成" if is_hidden else "通常ルーム作成"
        super().__init__(title=title_text)
        self.cog = cog_ref
        self.is_hidden = is_hidden

        self.room_name = TextInput(
            label="ルーム名を入力してください",
            placeholder="例: 自由な雑談部屋",
            default="",
            max_length=32,
        )
        self.add_item(self.room_name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        category = guild.get_channel(CATEGORY_ID)

        if not category:
            return await interaction.followup.send(
                "❌ カテゴリーIDが見つかりません。管理者へ連絡してください。",
                ephemeral=True,
            )

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

        if self.is_hidden:
            overwrites[guild.default_role] = discord.PermissionOverwrite(
                view_channel=False, connect=False
            )
            prefix = "🔒 "
        else:
            prefix = "🔊 "

        try:
            channel = await guild.create_voice_channel(
                name=f"{prefix}{self.room_name.value}",
                category=category,
                overwrites=overwrites,
            )
        except Exception as e:
            logger.error(f"❌ チャンネル作成失敗: {e}", exc_info=True)
            return await interaction.followup.send(
                "❌ チャンネル作成に失敗しました。", ephemeral=True
            )

        ch_id_str = str(channel.id)
        channel_data = {
            "owner_id": member.id,
            "moderators": [],
            "is_saved": False,
        }
        self.cog.vc_data[ch_id_str] = channel_data
        save_vc_data(self.cog.vc_data)

        if member.voice:
            try:
                await member.move_to(channel)
            except Exception:
                pass

        view = VcControlView(
            voice_channel=channel, owner_id=member.id, cog_ref=self.cog
        )
        embed = build_status_embed(channel, channel_data, guild)
        await channel.send(embed=embed, view=view)

        room_type = "非表示" if self.is_hidden else "通常"
        await interaction.followup.send(
            f"✅ {room_type}ルーム **{channel.name}** を作成しました！\n{channel.mention} に接続してください。",
            ephemeral=True,
        )


# --- ポータル画面 View ---
class PortalView(View):

    def __init__(self, cog_ref):
        super().__init__(timeout=None)
        self.cog = cog_ref

    @discord.ui.button(
        label="自分のルーム作成",
        style=discord.ButtonStyle.secondary,
        custom_id="portal_create_normal",
    )
    async def create_normal_button(
        self, interaction: discord.Interaction, button: Button
    ):
        await interaction.response.send_modal(
            CreateRoomModal(cog_ref=self.cog, is_hidden=False)
        )

    @discord.ui.button(
        label="自分のルーム作成 (非表示)",
        style=discord.ButtonStyle.green,
        custom_id="portal_create_hidden",
    )
    async def create_hidden_button(
        self, interaction: discord.Interaction, button: Button
    ):
        await interaction.response.send_modal(
            CreateRoomModal(cog_ref=self.cog, is_hidden=True)
        )

    @discord.ui.button(
        label="コントロールパネル",
        style=discord.ButtonStyle.blurple,
        custom_id="portal_show_panel",
    )
    async def show_panel_button(
        self, interaction: discord.Interaction, button: Button
    ):
        channel = self.cog.get_user_vc(interaction.user)
        if not channel:
            return await interaction.response.send_message(
                "❌ あなたが作成・管理権限を持つ対象VCに参加した状態で実行してください。",
                ephemeral=True,
            )

        ch_id_str = str(channel.id)
        channel_data = self.cog.vc_data[ch_id_str]

        view = VcControlView(
            voice_channel=channel,
            owner_id=channel_data["owner_id"],
            cog_ref=self.cog,
        )
        embed = build_status_embed(channel, channel_data, interaction.guild)
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )


# --- VCコントロールパネル View ---
class VcControlView(View):

    def __init__(
        self, voice_channel: discord.VoiceChannel, owner_id: int, cog_ref
    ):
        super().__init__(timeout=None)
        self.channel = voice_channel
        self.owner_id = owner_id
        self.cog = cog_ref

    def is_authorized(self, user: discord.Member) -> bool:
        if user.guild_permissions.administrator:
            return True
        channel_data = self.cog.vc_data.get(str(self.channel.id), {})
        moderators = set(channel_data.get("moderators", []))
        owner_id = channel_data.get("owner_id", self.owner_id)
        return user.id == owner_id or user.id in moderators

    async def interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        if not self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "❌ このVCの操作権限（オーナー、モデレーター、または管理者）がありません。",
                ephemeral=True,
            )
            return False
        return True

    async def update_panel(
        self, interaction: discord.Interaction, response_message: str
    ):
        ch_id = str(self.channel.id)
        channel_data = self.cog.vc_data.get(ch_id, {})

        is_saved = channel_data.get("is_saved", False)
        for child in self.children:
            if (
                isinstance(child, Button)
                and child.label == "💾 部屋を保存/解除"
            ):
                child.style = (
                    discord.ButtonStyle.success
                    if is_saved
                    else discord.ButtonStyle.secondary
                )

        embed = build_status_embed(
            self.channel, channel_data, interaction.guild
        )
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message(
            response_message, ephemeral=True
        )

    @discord.ui.button(
        label="💾 部屋を保存/解除", style=discord.ButtonStyle.secondary, row=0
    )
    async def toggle_saved(
        self, interaction: discord.Interaction, button: Button
    ):
        ch_id = str(self.channel.id)
        channel_data = self.cog.vc_data.get(ch_id, {})
        new_saved = not channel_data.get("is_saved", False)
        channel_data["is_saved"] = new_saved
        self.cog.vc_data[ch_id] = channel_data
        save_vc_data(self.cog.vc_data)

        msg = (
            "💾 **部屋の保存を有効化しました**（全員が退出しても削除されません）"
            if new_saved
            else "❌ **自動削除を有効化しました**"
        )
        await self.update_panel(interaction, msg)

    @discord.ui.button(
        label="🔓 鍵の開閉", style=discord.ButtonStyle.secondary, row=0
    )
    async def toggle_lock(
        self, interaction: discord.Interaction, button: Button
    ):
        guild = interaction.guild
        overwrite = self.channel.overwrites_for(guild.default_role)
        is_locked = overwrite.connect is False

        overwrite.connect = None if is_locked else False
        await self.channel.set_permissions(
            guild.default_role, overwrite=overwrite
        )

        msg = (
            "🔓 **部屋を公開に変更しました**"
            if is_locked
            else "🔒 **部屋を鍵付きに変更しました**"
        )
        await self.update_panel(interaction, msg)

    @discord.ui.button(
        label="👁️ 表示/非表示", style=discord.ButtonStyle.secondary, row=0
    )
    async def toggle_visibility(
        self, interaction: discord.Interaction, button: Button
    ):
        guild = interaction.guild
        overwrite = self.channel.overwrites_for(guild.default_role)
        is_hidden = overwrite.view_channel is False

        overwrite.view_channel = None if is_hidden else False
        await self.channel.set_permissions(
            guild.default_role, overwrite=overwrite
        )

        msg = (
            "👁️ **部屋を通常表示に変更しました**"
            if is_hidden
            else "🙈 **部屋を非表示に変更しました**"
        )
        await self.update_panel(interaction, msg)

    # ➕ 招待ボタン（指定フォーマットでの出力対応）
    @discord.ui.button(
        label="➕ 招待 (ユーザー/ロール)", style=discord.ButtonStyle.primary, row=1
    )
    async def invite_target(
        self, interaction: discord.Interaction, button: Button
    ):
        select_view = View()
        entity_select = Select(
            placeholder="招待したいユーザーまたはロールを選択",
            select_type=discord.ComponentType.mentionable_select,
            max_values=1,
        )

        async def callback(select_interaction: discord.Interaction):
            await select_interaction.response.defer(ephemeral=True)
            target = entity_select.values[0]
            guild = interaction.guild
            user = interaction.user

            try:
                # 権限の付与 (チャンネル表示・接続)
                await self.channel.set_permissions(
                    target, view_channel=True, connect=True
                )

                vc_link = f"https://discord.com/channels/{guild.id}/{self.channel.id}"
                invite_msg = (
                    f"✅ {target.mention} を招待しました！\n\n"
                    f"{user.display_name} さんから {guild.name} の一時VCへ招待されました。\n"
                    f"VC: #{self.channel.name}\n"
                    f"参加リンク: {vc_link}"
                )

                await select_interaction.followup.send(
                    invite_msg,
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"❌ 招待処理エラー: {e}", exc_info=True)
                await select_interaction.followup.send(
                    "❌ 招待処理中にエラーが発生しました。Botの権限を確認してください。",
                    ephemeral=True,
                )

        entity_select.callback = callback
        select_view.add_item(entity_select)
        await interaction.response.send_message(
            "招待する対象を選択してください:", view=select_view, ephemeral=True
        )

    # 📩 VC参加者宛て一括DM送信ボタン
    @discord.ui.button(
        label="📩 参加者にDM送信", style=discord.ButtonStyle.success, row=1
    )
    async def send_vc_dm(
        self, interaction: discord.Interaction, button: Button
    ):
        await interaction.response.send_modal(SendVcDmModal(channel=self.channel))

    @discord.ui.button(
        label="🛡️ モデレーター設定", style=discord.ButtonStyle.primary, row=2
    )
    async def manage_moderator(
        self, interaction: discord.Interaction, button: Button
    ):
        ch_id = str(self.channel.id)
        channel_data = self.cog.vc_data.get(ch_id, {})
        current_owner = channel_data.get("owner_id", self.owner_id)

        if (
            interaction.user.id != current_owner
            and not interaction.user.guild_permissions.administrator
        ):
            return await interaction.response.send_message(
                "❌ モデレーター設定はオーナーまたは管理者のみ操作できます。",
                ephemeral=True,
            )

        select_view = View()
        user_select = UserSelect(
            placeholder="モデレーターに設定/解除するユーザーを選択",
            max_values=1,
        )

        async def callback(select_interaction: discord.Interaction):
            await select_interaction.response.defer(ephemeral=True)
            target = user_select.values[0]
            moderators = channel_data.get("moderators", [])

            if target.id in moderators:
                moderators.remove(target.id)
                await self.channel.set_permissions(target, overwrite=None)
                msg = f"🗑️ {target.mention} のモデレーター権限を解除しました。"
            else:
                moderators.append(target.id)
                await self.channel.set_permissions(
                    target,
                    view_channel=True,
                    connect=True,
                    mute_members=True,
                    deafen_members=True,
                    move_members=True,
                )
                msg = f"🛡️ {target.mention} をモデレーターに追加しました。"

            channel_data["moderators"] = moderators
            self.cog.vc_data[ch_id] = channel_data
            save_vc_data(self.cog.vc_data)

            embed = build_status_embed(
                self.channel, channel_data, select_interaction.guild
            )
            await select_interaction.message.edit(embed=embed, view=self)
            await select_interaction.followup.send(msg, ephemeral=True)

        user_select.callback = callback
        select_view.add_item(user_select)
        await interaction.response.send_message(
            "モデレーターを選択してください:", view=select_view, ephemeral=True
        )

    @discord.ui.button(
        label="👑 オーナー譲渡", style=discord.ButtonStyle.danger, row=2
    )
    async def transfer_ownership(
        self, interaction: discord.Interaction, button: Button
    ):
        ch_id = str(self.channel.id)
        channel_data = self.cog.vc_data.get(ch_id, {})
        current_owner_id = channel_data.get("owner_id", self.owner_id)

        if (
            interaction.user.id != current_owner_id
            and not interaction.user.guild_permissions.administrator
        ):
            return await interaction.response.send_message(
                "❌ オーナー譲渡は現在のオーナーまたは管理者のみ可能です。",
                ephemeral=True,
            )

        members = [
            m for m in self.channel.members if m.id != current_owner_id
        ]
        if not members:
            return await interaction.response.send_message(
                "❌ 譲渡できるメンバーがVC内にいません。", ephemeral=True
            )

        select_view = View()
        user_select = UserSelect(
            placeholder="新オーナーを選択",
            max_values=1,
        )

        async def callback(select_interaction: discord.Interaction):
            await select_interaction.response.defer(ephemeral=True)
            new_owner = user_select.values[0]
            old_owner = interaction.guild.get_member(current_owner_id)

            if old_owner:
                await self.channel.set_permissions(old_owner, overwrite=None)

            await self.channel.set_permissions(
                new_owner,
                view_channel=True,
                connect=True,
                manage_channels=True,
                mute_members=True,
                deafen_members=True,
                move_members=True,
            )

            channel_data["owner_id"] = new_owner.id
            self.cog.vc_data[ch_id] = channel_data
            save_vc_data(self.cog.vc_data)
            self.owner_id = new_owner.id

            try:
                await self.channel.edit(
                    name=f"🔒 {new_owner.display_name}の部屋"
                )
            except Exception:
                pass

            msg = f"👑 オーナー権限を <@{current_owner_id}> から {new_owner.mention} に譲渡しました。"
            embed = build_status_embed(
                self.channel, channel_data, select_interaction.guild
            )
            await select_interaction.message.edit(embed=embed, view=self)
            await select_interaction.followup.send(msg, ephemeral=True)

        user_select.callback = callback
        select_view.add_item(user_select)
        await interaction.response.send_message(
            "新しいオーナーを選択してください:", view=select_view, ephemeral=True
        )