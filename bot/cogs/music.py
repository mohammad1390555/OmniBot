# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Music: play, pause, resume, skip, stop, queue, volume, loop, shuffle, controller UI."""

from __future__ import annotations

import asyncio
import random
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
    webpage_url: str
    stream_url: str
    duration: int = 0
    requester: int = 0
    thumbnail: str = ""


@dataclass
class GuildPlayer:
    queue: list[Track] = field(default_factory=list)
    current: Track | None = None
    loop: str = "off"  # off | track | queue
    volume: int = 50
    next: asyncio.Event = field(default_factory=asyncio.Event)


class MusicControlView(discord.ui.View):
    def __init__(self, cog: Music, guild_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="m_pause")
    async def toggle_pause(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        if not guild or not guild.voice_client:
            return await interaction.response.send_message(embed=embeds.error("Not playing."), ephemeral=True)
        vc = guild.voice_client
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed.", ephemeral=True)
        elif vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused.", ephemeral=True)
        else:
            await interaction.response.send_message("Not playing.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="m_skip")
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        if not guild or not guild.voice_client:
            return await interaction.response.send_message(embed=embeds.error("Not playing."), ephemeral=True)
        guild.voice_client.stop()
        await interaction.response.send_message("⏭️ Skipped track.", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="m_loop")
    async def loop(self, interaction: discord.Interaction, _: discord.ui.Button):
        player = self.cog._player(self.guild_id)
        modes = ["off", "track", "queue"]
        cur_idx = modes.index(player.loop) if player.loop in modes else 0
        player.loop = modes[(cur_idx + 1) % len(modes)]
        await interaction.response.send_message(f"🔁 Loop mode: **{player.loop}**", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="m_shuffle")
    async def shuffle(self, interaction: discord.Interaction, _: discord.ui.Button):
        player = self.cog._player(self.guild_id)
        if not player.queue:
            return await interaction.response.send_message("Queue is empty.", ephemeral=True)
        random.shuffle(player.queue)
        await interaction.response.send_message("🔀 Queue shuffled.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="m_stop")
    async def stop(self, interaction: discord.Interaction, _: discord.ui.Button):
        player = self.cog._player(self.guild_id)
        player.queue.clear()
        player.loop = "off"
        guild = interaction.guild
        if guild and guild.voice_client:
            guild.voice_client.stop()
        await interaction.response.send_message("⏹️ Playback stopped.", ephemeral=True)


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
            return "Music requires `yt-dlp`. Install with: `pip install yt-dlp PyNaCl`"
        if shutil.which("ffmpeg") is None:
            return "Music requires **FFmpeg** installed and accessible on PATH."
        return None

    async def _extract(self, query: str) -> Track | None:
        target = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "default_search": "auto",
        }
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(opts).extract_info(target, download=False)
            )
        except Exception:
            return None

        if not info:
            return None
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        stream_url = info.get("url") or ""
        webpage_url = info.get("webpage_url") or query

        return Track(
            title=info.get("title", "Unknown Title"),
            webpage_url=webpage_url,
            stream_url=stream_url,
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

            # If stream_url is expired or missing, re-extract
            if not track.stream_url or not track.stream_url.startswith("http"):
                fresh = await self._extract(track.webpage_url)
                if fresh and fresh.stream_url:
                    track.stream_url = fresh.stream_url

            ffmpeg_opts = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn"
            }

            try:
                source = discord.FFmpegPCMAudio(track.stream_url or track.webpage_url, **ffmpeg_opts)
                transformed = discord.PCMVolumeTransformer(source, volume=player.volume / 100)
            except Exception:
                continue

            voice = guild.voice_client
            if voice is None or not voice.is_connected():
                return

            voice.play(transformed, after=lambda e: self.bot.loop.call_soon_threadsafe(player.next.set))

            # Send Now Playing embed with controller view
            channel = None
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break

            if channel:
                dur_str = f"{track.duration // 60}:{track.duration % 60:02d}" if track.duration else "Live"
                embed = embeds.titled(
                    await self.bot.tr(guild.id, "music_now_playing"),
                    f"🎶 **[{track.title}]({track.webpage_url})**\n"
                    f"⏱️ **Duration:** `{dur_str}` | 👤 **Requested by:** <@{track.requester}>")
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                view = MusicControlView(self, guild.id)
                try:
                    await channel.send(embed=embed, view=view)
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
            return await msg.edit(embed=embeds.error("Couldn't find playable audio for that query."))
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
        if voice and (voice.is_playing() or voice.is_paused()):
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
            lines.append(f"▶️ **Now Playing:** {player.current.title}")
        for i, t in enumerate(player.queue[:15], 1):
            dur = f" ({t.duration//60}:{t.duration%60:02d})" if t.duration else ""
            lines.append(f"`{i}.` {t.title}{dur}")
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
        player = self._player(ctx.guild.id)
        player.volume = vol
        voice = ctx.guild.voice_client
        if voice and voice.source:
            try:
                voice.source.volume = vol / 100
            except Exception:
                pass
        await ctx.send(embed=embeds.success(await self.bot.tr(
            ctx.guild.id, "music_volume", volume=vol)))

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Show the current track.")
    @commands.guild_only()
    @module_enabled("music")
    async def nowplaying(self, ctx: commands.Context) -> None:
        player = self._player(ctx.guild.id)
        if not player.current:
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id, "music_not_playing")))
        t = player.current
        dur_str = f"{t.duration // 60}:{t.duration % 60:02d}" if t.duration else "Live"
        embed = embeds.titled(
            await self.bot.tr(ctx.guild.id, "music_now_playing"),
            f"**[{t.title}]({t.webpage_url})**\n⏱️ Duration: `{dur_str}` | Requested by: <@{t.requester}>"
        )
        if t.thumbnail:
            embed.set_thumbnail(url=t.thumbnail)
        view = MusicControlView(self, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

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
        player = self._player(ctx.guild.id)
        if not player.queue:
            return await ctx.send(embed=embeds.error(
                await self.bot.tr(ctx.guild.id, "music_queue_empty")))
        random.shuffle(player.queue)
        await ctx.send(embed=embeds.success("🔀 Queue shuffled."))

    @commands.hybrid_command(name="leave", description="Disconnect from voice channel.")
    @commands.guild_only()
    @module_enabled("music")
    async def leave(self, ctx: commands.Context) -> None:
        voice = ctx.guild.voice_client
        if voice:
            await voice.disconnect()
            player = self._player(ctx.guild.id)
            player.queue.clear()
            player.current = None
            await ctx.send(embed=embeds.success("👋 Disconnected."))


async def setup(bot: OmniBot) -> None:
    await bot.add_cog(Music(bot))
