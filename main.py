import discord
from discord.ext import commands
from googleapiclient.discovery import build
import yt_dlp
import os
import re
import asyncio
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# Botのインテント設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# Botの初期化
bot = commands.Bot(command_prefix='!', intents=intents)

# ループ状態を管理するクラス
class MusicPlayer:
    def __init__(self):
        self.loop = False
        self.current_url = None

music_player = MusicPlayer()

# 環境変数からトークンなどを取得
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
# FFMPEGのパスを直接指定
FFMPEG_PATH = os.path.join(os.path.dirname(__file__), "ffmpeg", "ffmpeg-8.0-full_build", "ffmpeg-8.0-full_build", "bin")

# YouTube API の初期化
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# yt_dlp のオプション設定
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'cookiefile': 'youtube.com_cookies.txt',  # 有効なクッキーが必要
    'http_chunk_size': 10485760,  # チャンクサイズを10MBに設定
    'fragment_retries': 10,       # フラグメントの再試行回数
    'retries': 10,                # 接続の再試行回数
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
    }]
}

# YouTube検索関数（安全性向上版）
def search_youtube(query):
    request = youtube.search().list(
        part="snippet",
        maxResults=5,
        q=query,
        type="video"
    )
    try:
        response = request.execute()
    except Exception as e:
        print(f"[ERROR] Google API error: {e}")
        return None

    items = response.get("items", [])
    for item in items:
        video_id = item.get("id", {}).get("videoId")
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    return None

# YouTube URLかどうか判定
def is_youtube_url(text):
    youtube_url_pattern = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$'
    return re.match(youtube_url_pattern, text)

# !play コマンド
@bot.command()
async def play(ctx, *, search: str):
    if ctx.author.voice is None:
        await ctx.send("まずボイスチャンネルに入ってください。")
        return

    voice_channel = ctx.author.voice.channel

    try:
        if ctx.voice_client is None:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)
    except Exception as e:
        await ctx.send("ボイスチャンネルへの接続に失敗しました。")
        print(f"[ERROR] Voice connection error: {e}")
        return

    if is_youtube_url(search):
        url = search
    else:
        url = search_youtube(search)
        if url is None:
            await ctx.send("動画が見つかりませんでした。")
            return

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
        except Exception as e:
            await ctx.send("音声の取得に失敗しました。")
            print(f"[ERROR] yt_dlp error: {e}")
            return

    ffmpeg_options = {
        'options': '-vn',
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -thread_queue_size 4096'
    }

    try:
        source = discord.FFmpegPCMAudio(
            executable=os.path.join(FFMPEG_PATH, "ffmpeg.exe"),
            source=audio_url,
            **ffmpeg_options
        )
    except Exception as e:
        await ctx.send("音声ソースの作成に失敗しました。")
        print(f"[ERROR] FFmpeg source error: {e}")
        return

    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    def after_playing(error):
        if error:
            print(f"[ERROR] Playback error: {error}")
        elif music_player.loop and ctx.voice_client and ctx.voice_client.is_connected():
            # ループが有効な場合、同じ曲を再度再生
            asyncio.run_coroutine_threadsafe(play(ctx, search=music_player.current_url), bot.loop)

    ctx.voice_client.play(source, after=after_playing)
    music_player.current_url = url
    await ctx.send(f"再生します:{url}")

# !loop コマンド（ループ再生の切り替え）
@bot.command()
async def loop(ctx):
    music_player.loop = not music_player.loop
    status = "オン" if music_player.loop else "オフ"
    await ctx.send(f"ループ再生を{status}にしました。")

# !stop コマンド（音楽の再生だけ停止）
@bot.command()
async def stop(ctx):
    if ctx.voice_client is not None and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("音楽の再生を停止しました。")
    else:
        await ctx.send("現在再生中の音楽はありません。")

# !leave コマンド（ボイスチャンネルから退出）
@bot.command()
async def leave(ctx):
    if ctx.voice_client is not None:
        await ctx.voice_client.disconnect()
        await ctx.send("ボイスチャンネルから退出しました。")
    else:
        await ctx.send("Botはボイスチャンネルに接続していません。")

# Bot起動時の処理
@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user.name}')

# Botの起動
bot.run(DISCORD_TOKEN)
