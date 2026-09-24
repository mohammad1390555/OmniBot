# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Music: play/pause/skip/queue/volume/loop via voice + yt-dlp.

Optional module — if yt-dlp or FFmpeg is missing the cog loads but
commands reply with an install hint instead of crashing.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from bot.core.bot import OmniBot
from bot.core.config import config
from bot.utils import embeds
from bot.utils.checks import module_enabled

try:
    import yt_dlp  # type: ignore
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


@dataclass
class Track:
    title: str
    url: str
    duration: int = 0
    requester: int = 0
    thumbnail: str = ""


@dataclass
class GuildPlayer:
    queue: list[Track] = field(default_factory=list)
    current: Track | None = None
    loop: str = "off"  # off | track | queue
    next = asyncio.Event()


class Music(commands.Cog):
    def __init__(self, bot: OmniBot) -> None:
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def _player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    def _check_deps(self) -> str | None:
        if not HAS_YTDLP:
            return "Music requires `yt-dlp`. Install it: `pip install yt-dlp PyNaCl`"
        if shutil.which("ffmpeg") is None:
            return "Music requires **FFmpeg** installed and on PATH."
        
    async def _extract(self, query: str) -> Track | None:
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                "format": "bestaudio/best"}
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(opts).extract_info(query, download=False))
        except Exception:
                    if not info:
                    if "entries" in info:
            info = info["entries"][0]
        return Track(
            title=info.get("title", "Unknown"),
            url=info.get("webpage_url") or info.get("url", query),
            duration=int(info.get("duration") or 0),
            thumbnail=info.get("thumbnail", ""),
        )

    async def _play_next(self, guild: discord.Guild, player: GuildPlayer) -> None:
        while True:
            player.next.clear()
            if not player.queue:
                player.current = None
                return
            track = player.queue.pop(0)
            player.current = track

            source = await asyncio.get_event_loop().run_in_executor(
                None, lambda: discord.FFmpegPCMAudio(
                    track.url, executable="ffmpeg",
                    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"))
            voice = guild.voice_client
            if voice is None or not voice.is_connected():
                return
            voice.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(player.next.set))

            channel = None
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
            if channel:
                embed = embeds.titled(
                    await self.bot.tr(guild.id, "music_now_playing"),
                    f"**[{track.title}]({track.url})** — requested by <@{track.requester}>")
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

            await player.next.wait()

            if player.loop == "track" and track:
                player.queue.insert(0, track)
            elif player.loop == "queue" and track:
                player.queue.append(track)

    # ------------------------------------------------------------------
    @commands.hybrid_command(name="play", description="Play a song (URL or search terms).")
    @commands.guild_only()
    @module_enabled("music")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        err = self._check_deps()
        if err:
            return await ctx.send(embed=embeds.error(err))

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id, "music_not_in_voice")))

        voice = ctx.guild.voice_client
        if voice is None:
            await ctx.author.voice.channel.connect()
        elif voice.channel != ctx.author.voice.channel:
            await voice.move_to(ctx.author.voice.channel)

        msg = await ctx.send(embed=embeds.info(f"🔍 Searching for **{query}**..."))
        track = await self._extract(query)
        if track is None:
            return await msg.edit(embed=embeds.error("Couldn't find anything for that query."))
        track.requester = ctx.author.id

        player = self._player(ctx.guild.id)
        was_idle = player.current is None and not player.queue
        player.queue.append(track)
        await msg.edit(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "music_added_queue", title=track.title)))
        if was_idle:
            await self._play_next(ctx.guild, player)

    @commands.hybrid_command(name="pause", description="Pause playback.")
    @commands.guild_only()
    @module_enabled("music")
    async def pause(self, ctx: commands.Context) -> None:
        voice = ctx.guild.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "music_paused")))
        else:
            await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "music_not_playing")))

    @commands.hybrid_command(name="resume", description="Resume playback.")
    @commands.guild_only()
    @module_enabled("music")
    async def resume(self, ctx: commands.Context) -> None:
        voice = ctx.guild.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "music_resumed")))
        else:
            await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "music_not_playing")))

    @commands.hybrid_command(name="skip", description="Skip the current track.")
    @commands.guild_only()
    @module_enabled("music")
    async def skip(self, ctx: commands.Context) -> None:
        voice = ctx.guild.voice_client
        player = self._player(ctx.guild.id)
        if voice and voice.is_playing():
            voice.stop()
            await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "music_skipped")))
        else:
            await ctx.send(embed=embeds.error(await self.bot.tr(ctx.guild.id, "music_not_playing")))

    @commands.hybrid_command(name="stop", description="Stop and clear the queue.")
    @commands.guild_only()
    @module_enabled("music")
    async def stop(self, ctx: commands.Context) -> None:
        voice = ctx.guild.voice_client
        player = self._player(ctx.guild.id)
        player.queue.clear()
        player.loop = "off"
        if voice:
            voice.stop()
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, "music_stopped")))

    @commands.hybrid_command(name="queue", description="Show the music queue.")
    @commands.guild_only()
    @module_enabled("music")
    async def queue(self, ctx: commands.Context) -> None:
        player = self._player(ctx.guild.id)
        lines = []
        if player.current:
            lines.append(f"▶️ **Now:** {player.current.title}")
        for i, t in enumerate(player.queue[:15], 1):
            lines.append(f"`{i}.` {t.title}")
        if not lines:
            return await ctx.send(embed=embeds.info(
                await self.bot.tr(ctx.guild.id, "music_queue_empty")))
        await ctx.send(embed=embeds.titled(
            await self.bot.tr(ctx.guild.id, "music_queue_title"), "\n".join(lines)))

    @commands.hybrid_command(name="volume", description="Set playback volume (0-200).")
    @commands.guild_only()
    @module_enabled("music")
    async def volume(self, ctx: commands.Context, vol: int) -> None:
        max_vol = int(config.get("music.max_volume", 200))
        vol = max(0, min(vol, max_vol))
        voice = ctx.guild.voice_client
        if voice and voice.source:
            try:
                voice.source = discord.PCMVolumeTransformer(voice.source, volume=vol / 100)
            # FIXME: [auto-fix]: handle exception
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "music_volume", volume=vol)))

    @commands.hybrid_command(name="nowplaying", description="Show the current track.")
    @commands.guild_only()
    @module_enabled("music")
    async def nowplaying(self, ctx: commands.Context) -> None:
        player = self._player(ctx.guild.id)
        if not player.current:
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id, "music_not_playing")))
        t = player.current
        embed = embeds.titled(await self.bot.tr(ctx.guild.id, "music_now_playing"),
                              f"**[{t.title}]({t.url})** — requested by <@{t.requester}>")
        if t.thumbnail:
            embed.set_thumbnail(url=t.thumbnail)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="loop", description="Set loop mode: off | track | queue.")
    @commands.guild_only()
    @module_enabled("music")
    async def loop(self, ctx: commands.Context, mode: str) -> None:
        mode = mode.lower()
        if mode not in ("off", "track", "queue"):
            return await ctx.send(embed=embeds.error("Choose: off, track, queue"))
        player = self._player(ctx.guild.id)
        player.loop = mode
        key = {"off": "music_loop_off", "track": "music_loop_track", "queue": "music_loop_queue"}[mode]
        await ctx.send(embed=embeds.success(await self.bot.tr(ctx.guild.id, key)))

    @commands.hybrid_command(name="shuffle", description="Shuffle the queue.")
    @commands.guild_only()
    @module_enabled("music")
    async def shuffle(self, ctx: commands.Context) -> None:
        import random
        player = self._player(ctx.guild.id)
        if not player.queue:
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id, "music_queue_empty")))
        random.shuffle(player.queue)
        await ctx.send(embed=embeds.success("🔀 Queue shuffled."))

    @commands.hybrid_command(name="leave", description="Disconnect from voice.")
    @commands.guild_only()
    @module_enabled("music")
    async def leave(self, ctx: commands.Context) -> None:
        voice = ctx.guild.voice_client
        if voice:
            await voice.disconnect()
            await ctx.send(embed=embeds.success("👋 Disconnected."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Music(bot))
