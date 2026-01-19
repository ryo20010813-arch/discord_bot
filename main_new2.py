import discord
from discord.ext import commands
import yt_dlp
import os
import re
import asyncio
from dotenv import load_dotenv
from googleapiclient.discovery import build

# 環境変数読み込み
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")  # もし YouTube 検索機能を使うなら使う

# パス設定
BASE_DIR = os.path.dirname(__file__)
# ffmpeg の実行ファイルパス（環境に合わせて修正）
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg", "ffmpeg-8.0-full_build", "ffmpeg-8.0-full_build", "bin", "ffmpeg.exe")

# Bot 初期化
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ループ再生管理クラス
class MusicPlayer:
    def __init__(self):
        self.loop = False
        self.current_search = None

music_player = MusicPlayer()

# yt_dlp のオプション（クッキーなし版）
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'http_chunk_size': 10485760,
    'fragment_retries': 10,
    'retries': 10,
    'extract_flat': True,
    'force_generic_extractor': False,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
    }]
}

# YouTube URL かどうか判定
def is_youtube_url(text: str) -> bool:
    pattern = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$'
    return re.match(pattern, text) is not None

# YouTube 検索（YouTube Data API が使える場合のみ。なくても動くが検索機能は制限される）
from googleapiclient.discovery import build

youtube = None
if YOUTUBE_API_KEY:
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

def search_youtube(query: str) -> str | None:
    if youtube is None:
        return None
    try:
        req = youtube.search().list(
            part="snippet", q=query, maxResults=1, type="video"
        )
        res = req.execute()
        items = res.get("items", [])
        if not items:
            return None
        vid = items[0]["id"]["videoId"]
        return f"https://www.youtube.com/watch?v={vid}"
    except Exception as e:
        print(f"[ERROR] YouTube search failed: {e}")
        return None

# !play コマンド
@bot.command()
async def play(ctx, *, search: str):
    # ユーザーがボイスチャンネルにいなければ拒否
    if ctx.author.voice is None:
        await ctx.send("まずボイスチャンネルに入ってください。")
        return

    voice_channel = ctx.author.voice.channel

    # ボットをボイスチャンネルに接続 or 移動
    if ctx.voice_client is None:
        await voice_channel.connect()
    elif ctx.voice_client.channel != voice_channel:
        await ctx.voice_client.move_to(voice_channel)

    # URL かキーワードか判断
    if is_youtube_url(search):
        url = search
    else:
        url = search_youtube(search)
        if url is None:
            await ctx.send("なかったお。うんぽうんぽ")
            return

    # yt-dlp で音声情報取得
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
    except Exception as e:
        await ctx.send("秤屋直樹の性奴隷になります。")
        print(f"[ERROR] yt_dlp error: {e}")
        return

    # ffmpeg 再生設定
    ffmpeg_opts = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -thread_queue_size 4096',
        'options': '-vn'
    }

    try:
        source = discord.FFmpegPCMAudio(
            executable=FFMPEG_PATH,
            source=audio_url,
            **ffmpeg_opts
        )
    except Exception as e:
        await ctx.send("音声ソースの作成に失敗しました。")
        print(f"[ERROR] FFmpeg source error: {e}")
        return

    # もし既に再生中なら止める
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    def after_playing(error):
        if error:
            print(f"[ERROR] Playback error: {error}")
        elif music_player.loop and ctx.voice_client and ctx.voice_client.is_connected():
            # ループ再生
            asyncio.run_coroutine_threadsafe(play(ctx, search=music_player.current_search), bot.loop)

    music_player.current_search = search
    ctx.voice_client.play(source, after=after_playing)
    await ctx.send(f"でる: {url}")

# デフォルトの help コマンドを削除してカスタマイズ
bot.remove_command('help')

# !help コマンド
@bot.command(name='help')
async def help_command(ctx):
    help_text = """```
【利用可能なコマンド】

!play <URL or キーワード>
  - YouTubeの音楽を再生します
  - 例: !play https://www.youtube.com/watch?v=xxxxx
  - 例: !play みどり

!loop
  - ループ再生をオン/オフに切り替えます

!stop
  - 現在再生中の音楽を停止します

!leave
  - ボットをボイスチャンネルから退出させます

!help
  - このヘルプメッセージを表示します

【使用方法】
1. ボイスチャンネルに接続します
2. !play コマンドで曲を検索・再生します
3. !loop でループ再生を有効にすると、曲が終わったら自動的に同じ曲が再生されます
4. !stop で再生を停止し、!leave でボットを退出させます```"""
    await ctx.send(help_text)

# !loop コマンド
@bot.command()
async def loop(ctx):
    music_player.loop = not music_player.loop
    await ctx.send(f"ループ再生を {'オン' if music_player.loop else 'オフ'} にしました。")

# !stop コマンド
@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("再生を停止しました。")
    else:
        await ctx.send("現在再生中の音楽はありません。")

# !leave コマンド
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("ボイスチャンネルから退出しました。")
    else:
        await ctx.send("Botはボイスチャンネルに接続していません。")

# 起動時イベント
@bot.event
async def on_ready():
    print(f"Bot is ready: {bot.user.name}")

# 実行
if __name__ == "__main__":
    # ffmpeg.exe が存在するか確認（デバッグ用）
    if not os.path.exists(FFMPEG_PATH):
        print(f"[WARNING] ffmpeg が見つかりません: {FFMPEG_PATH}")
    bot.run(DISCORD_TOKEN)
