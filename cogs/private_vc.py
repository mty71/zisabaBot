import os
import discord
from discord.ext import commands
from discord.ui import View, Button, UserSelect
from dotenv import load_dotenv

load_dotenv()

CREATE_CHANNEL_ID = int(os.getenv("CREATE_CHANNEL_ID", "0"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "0"))

# --- 管理パネル UI View ---
class VcControlView(View):
    def __init__(self, voice_channel: discord.VoiceChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.channel = voice_channel
        self.owner = owner
        self.moderators = set()  # モデレーターのユーザーID集合
        self.is_locked = False   # 鍵付き状態（connect権限）
        self.is_hidden = False   # 非表示状態（view_channel権限）

    def is_authorized(self, user: discord.Member) -> bool:
        """オーナーまたはモデレーター権限があるかチェック"""
        return user.id == self.owner.id or user.id in self.moderators

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "❌ このVCの操作権限（オーナーまたはモデレーター）がありません。", ephemeral=True
            )
            return False
        return True

    # 1. 公開 / 鍵付き (ロック) 切り替え
    @discord.ui.button(label="🔓 鍵の開閉 (接続許可)", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_lock(self, interaction: discord.Interaction, button: Button):
        self.is_locked = not self.is_locked
        guild = interaction.guild
        overwrite = self.channel.overwrites_for(guild.default_role)
        overwrite.connect = False if self.is_locked else None  # Noneでカテゴリ・全体権限を継承（標準公開）
        await self.channel.set_permissions(guild.default_role, overwrite=overwrite)

        status = "🔒 **鍵付き（参加不可）**" if self.is_locked else "🔓 **公開（誰でも参加可）**"
        await interaction.response.send_message(f"チャンネルの接続設定を {status} に変更しました。", ephemeral=True)

    # 2. 通常表示 / 非表示 切り替え
    @discord.ui.button(label="👁️ 表示/非表示 切替", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_visibility(self, interaction: discord.Interaction, button: Button):
        self.is_hidden = not self.is_hidden
        guild = interaction.guild
        overwrite = self.channel.overwrites_for(guild.default_role)
        overwrite.view_channel = False if self.is_hidden else None
        await self.channel.set_permissions(guild.default_role, overwrite=overwrite)

        status = "🙈 **非表示（隠れ部屋）**" if self.is_hidden else "👁️ **通常表示**"
        await interaction.response.send_message(f"チャンネルの表示設定を {status} に変更しました。", ephemeral=True)

    # 3. ユーザー招待（鍵付き・非表示の場合でも許可）
    @discord.ui.button(label="➕ ユーザー招待", style=discord.ButtonStyle.primary, row=1)
    async def invite_user(self, interaction: discord.Interaction, button: Button):
        select_view = View()
        user_select = UserSelect(placeholder="招待したいユーザーを選択", max_values=1)

        async def callback(select_interaction: discord.Interaction):
            target = user_select.values[0]
            await self.channel.set_permissions(target, connect=True, view_channel=True)
            await select_interaction.response.send_message(
                f"✅ {target.mention} をこの部屋に招待・接続許可しました。", ephemeral=True
            )

        user_select.callback = callback
        select_view.add_item(user_select)
        await interaction.response.send_message("招待するユーザーを選択してください:", view=select_view, ephemeral=True)

    # 4. モデレーター追加 / 削除
    @discord.ui.button(label="🛡️ モデレーター設定", style=discord.ButtonStyle.primary, row=1)
    async def manage_moderator(self, interaction: discord.Interaction, button: Button):
        # モデレーター追加はオーナーのみ可能
        if interaction.user.id != self.owner.id:
            return await interaction.response.send_message("❌ モデレーター設定はオーナーのみ操作できます。", ephemeral=True)

        select_view = View()
        user_select = UserSelect(placeholder="モデレーターに設定/解除するユーザーを選択", max_values=1)

        async def callback(select_interaction: discord.Interaction):
            target = user_select.values[0]
            if target.id in self.moderators:
                self.moderators.remove(target.id)
                msg = f"🗑️ {target.mention} のモデレーター権限を解除しました。"
            else:
                self.moderators.add(target.id)
                msg = f"🛡️ {target.mention} をモデレーターに追加しました。"
            
            await select_interaction.response.send_message(msg, ephemeral=True)

        user_select.callback = callback
        select_view.add_item(user_select)
        await interaction.response.send_message("モデレーターに指定するユーザーを選択してください:", view=select_view, ephemeral=True)

    # 5. VCキック（追い出し）
    @discord.ui.button(label="🚫 キック", style=discord.ButtonStyle.danger, row=2)
    async def kick_user(self, interaction: discord.Interaction, button: Button):
        members = [m for m in self.channel.members if m.id != self.owner.id]
        if not members:
            return await interaction.response.send_message("❌ キック対象のメンバーが部屋にいません。", ephemeral=True)

        select_view = View()
        user_select = UserSelect(placeholder="キックするユーザーを選択", max_values=1)

        async def callback(select_interaction: discord.Interaction):
            target = user_select.values[0]
            if target in self.channel.members:
                # 接続拒否権限を付与した上でVCから切断
                await self.channel.set_permissions(target, connect=False)
                await target.move_to(None)
                await select_interaction.response.send_message(f"💥 {target.display_name} をキック・接続拒否にしました。", ephemeral=True)
            else:
                await select_interaction.response.send_message("❌ 指定したユーザーはVC内にいません。", ephemeral=True)

        user_select.callback = callback
        select_view.add_item(user_select)
        await interaction.response.send_message("キックするユーザーを選択してください:", view=select_view, ephemeral=True)

    # 6. 他のVCへ一括移動
    @discord.ui.button(label="🚀 他VCへ移動", style=discord.ButtonStyle.secondary, row=2)
    async def move_all_users(self, interaction: discord.Interaction, button: Button):
        # 移動先の選択肢（同サーバー内の他のボイスチャンネル一覧）
        guild = interaction.guild
        voice_channels = [ch for ch in guild.voice_channels if ch.id != self.channel.id]

        if not voice_channels:
            return await interaction.response.send_message("❌ 移動可能な他のボイスチャンネルがありません。", ephemeral=True)

        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in voice_channels[:25]  # Selectメニューの最大上限25個
        ]
        
        select_view = View()
        channel_select = discord.ui.Select(placeholder="移動先のボイスチャンネルを選択", options=options)

        async def callback(select_interaction: discord.Interaction):
            target_ch_id = int(channel_select.values[0])
            target_ch = guild.get_channel(target_ch_id)

            if target_ch:
                members_to_move = list(self.channel.members)
                for m in members_to_move:
                    try:
                        await m.move_to(target_ch)
                    except Exception:
                        pass
                await select_interaction.response.send_message(f"🚚 全員を **{target_ch.name}** へ移動させました。", ephemeral=True)
            else:
                await select_interaction.response.send_message("❌ チャンネルが見つかりませんでした。", ephemeral=True)

        channel_select.callback = callback
        select_view.add_item(channel_select)
        await interaction.response.send_message("メンバー全員の移動先を選択してください:", view=select_view, ephemeral=True)

    # 7. オーナー権限譲渡
    @discord.ui.button(label="👑 オーナー譲渡", style=discord.ButtonStyle.danger, row=2)
    async def transfer_ownership(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.owner.id:
            return await interaction.response.send_message("❌ オーナー権限の譲渡は現在のオーナーのみ可能です。", ephemeral=True)

        members = [m for m in self.channel.members if m.id != self.owner.id]
        if not members:
            return await interaction.response.send_message("❌ 譲渡できるメンバーがVC内にいません。", ephemeral=True)

        select_view = View()
        user_select = UserSelect(placeholder="新オーナーを選択", max_values=1)

        async def callback(select_interaction: discord.Interaction):
            new_owner = user_select.values[0]
            
            # 旧オーナーの特権(ミュート・チャンネル管理権限)を解除し、新オーナーに付与
            await self.channel.set_permissions(self.owner, overwrite=None)
            await self.channel.set_permissions(
                new_owner,
                connect=True,
                manage_channels=True,
                mute_members=True,
                deafen_members=True,
                move_members=True
            )

            old_owner = self.owner
            self.owner = new_owner
            
            # チャンネル名を更新
            try:
                await self.channel.edit(name=f"🔊 {new_owner.display_name}の部屋")
            except Exception:
                pass

            await select_interaction.response.send_message(
                f"👑 VCのオーナー権限を {old_owner.mention} から {new_owner.mention} に譲渡しました。"
            )

        user_select.callback = callback
        select_view.add_item(user_select)
        await interaction.response.send_message("新しいオーナーを選択してください:", view=select_view, ephemeral=True)


# --- Cog 本体 ---
class PrivateVC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_channels = set()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 1. 「作成用VC」に入室した場合の自動生成＆移動処理
        if after.channel and after.channel.id == CREATE_CHANNEL_ID:
            guild = member.guild
            category = guild.get_channel(CATEGORY_ID)

            # 初期設定:
            # - @everyone: 公開状態 (connect/view_channelはデフォルト継承)
            # - 作成者 (オーナー): ミュート権限・スピーカー制御・メンバー移動・管理権限を付与
            overwrites = {
                member: discord.PermissionOverwrite(
                    connect=True,
                    manage_channels=True,
                    mute_members=True,
                    deafen_members=True,
                    move_members=True
                )
            }

            # VCの作成
            channel = await guild.create_voice_channel(
                name=f"🔊 {member.display_name}の部屋",
                category=category,
                overwrites=overwrites
            )

            self.active_channels.add(channel.id)
            
            # 作成者を作成したVCへ移動
            await member.move_to(channel)

            # VC内チャットに管理パネル（UI View）を送信
            view = VcControlView(voice_channel=channel, owner=member)
            await channel.send(
                content=(
                    f"👑 **{member.mention} のプライベートVC**\n"
                    "最初は **【公開VC】** として作成されました。\n"
                    "以下の管理パネルから各種操作を行えます。"
                ),
                view=view
            )

        # 2. 誰もいなくなったVCの自動削除
        if before.channel and before.channel.id in self.active_channels:
            if len(before.channel.members) == 0:
                self.active_channels.remove(before.channel.id)
                await before.channel.delete()


async def setup(bot):
    await bot.add_cog(PrivateVC(bot))