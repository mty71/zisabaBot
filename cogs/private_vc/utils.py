import json
import os
import discord

DATA_PATH = "./data/vc_data.json"


def load_vc_data():
    if not os.path.exists(DATA_PATH):
        return {}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ JSONデータの読み込み失敗: {e}")
        return {}


def save_vc_data(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ JSONデータの保存失敗: {e}")


def build_status_embed(
    channel: discord.VoiceChannel, channel_data: dict, guild: discord.Guild
) -> discord.Embed:
    owner_id = channel_data.get("owner_id")
    moderators = channel_data.get("moderators", [])
    is_saved = channel_data.get("is_saved", False)

    default_role = guild.default_role
    overwrites = channel.overwrites_for(default_role)
    is_locked = overwrites.connect is False
    is_hidden = overwrites.view_channel is False

    mod_mentions = (
        [f"<@{m_id}>" for m_id in moderators] if moderators else ["なし"]
    )

    embed = discord.Embed(
        title=f"⚙️ {channel.name} コントロールパネル",
        color=discord.Color.blue(),
    )
    embed.add_field(name="👑 オーナー", value=f"<@{owner_id}>", inline=True)
    embed.add_field(
        name="💾 部屋の保存",
        value="🟢 有効 (保護中)" if is_saved else "⚪ 無効 (自動削除)",
        inline=True,
    )
    embed.add_field(
        name="🔒 接続制限",
        value="🔴 鍵付き (拒否)" if is_locked else "🟢 公開 (参加可)",
        inline=True,
    )
    embed.add_field(
        name="👁️ 表示設定",
        value="🙈 非表示" if is_hidden else "👁️ 通常表示",
        inline=True,
    )
    embed.add_field(
        name="🛡️ モデレーター", value=", ".join(mod_mentions), inline=False
    )
    embed.set_footer(
        text="※メンバーのキックや移動は、Discordの右クリック/長押しメニューから行えます。"
    )
    return embed