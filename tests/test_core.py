import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from bot.cogs.automod import INVITE_RE, LINK_RE, PHISHING_KEYWORDS
from bot.cogs.utility import _safe_eval, ast
from bot.core.bot import OmniBot
from bot.core.config import config
from bot.core.database import Database, db
from bot.utils import embeds, timeutil


class TestOmniBotCore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.original_path = config.get("database.sqlite_path")
        config.raw["database"]["sqlite_path"] = self.temp_db.name
        await db.connect()

    async def asyncTearDown(self):
        await db.close()
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        if self.original_path:
            config.raw["database"]["sqlite_path"] = self.original_path

    async def test_database_guild_settings_and_cache(self):
        guild_id = 123456789
        g = await db.get_guild(guild_id)
        self.assertEqual(g["guild_id"], guild_id)
        self.assertEqual(g["language"], "en")

        # Test setting prefix
        await db.set_guild_field(guild_id, "prefix", "?")
        g2 = await db.get_guild(guild_id)
        self.assertEqual(g2["prefix"], "?")

        # Test module toggles
        await db.set_module(guild_id, "music", False)
        self.assertFalse(await db.module_enabled(guild_id, "music"))
        self.assertTrue(await db.module_enabled(guild_id, "moderation"))

        # Test settings
        await db.set_guild_setting(guild_id, "starboard_threshold", 5)
        thresh = await db.get_guild_setting(guild_id, "starboard_threshold")
        self.assertEqual(thresh, 5)

    async def test_database_shop_and_inventory(self):
        guild_id = 987654321
        user_id = 111222333

        # Add shop item
        cur = await db.execute(
            "INSERT INTO shop_items (guild_id, name, description, price, role_id) VALUES (?, ?, ?, ?, ?)",
            (guild_id, "VIP Role", "Exclusive VIP status", 1000, 555)
        )
        item_id = cur.lastrowid

        # Query shop
        row = await db.fetchone("SELECT * FROM shop_items WHERE id = ?", (item_id,))
        self.assertEqual(row["name"], "VIP Role")
        self.assertEqual(row["price"], 1000)

        # Add to user inventory
        await db.execute(
            "INSERT INTO user_inventory (guild_id, user_id, item_id, quantity) VALUES (?, ?, ?, 1)",
            (guild_id, user_id, item_id)
        )
        inv = await db.fetchall("SELECT * FROM user_inventory WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["quantity"], 1)

    async def test_database_starboard_and_birthdays(self):
        guild_id = 112233
        # Starboard entry
        await db.execute(
            "INSERT INTO starboard (guild_id, message_id, channel_id, stars, posted_id) VALUES (?, ?, ?, ?, ?)",
            (guild_id, 1001, 2001, 5, 3001)
        )
        sb = await db.fetchone("SELECT * FROM starboard WHERE guild_id = ? AND message_id = ?", (guild_id, 1001))
        self.assertEqual(sb["stars"], 5)

        # Birthday entry
        await db.execute(
            "INSERT INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)",
            (guild_id, 4001, 7, 15)
        )
        bday = await db.fetchone("SELECT * FROM birthdays WHERE guild_id = ? AND user_id = ?", (guild_id, 4001))
        self.assertEqual(bday["month"], 7)
        self.assertEqual(bday["day"], 15)

    async def test_economy_stamping_and_balance(self):
        guild_id = 555
        user_id = 777
        now_str = timeutil.iso(timeutil.utcnow())

        # Test inserting with stamp on new row
        await db.execute(
            "INSERT INTO economy (guild_id, user_id, balance, last_daily) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = ?, last_daily = ?",
            (guild_id, user_id, 250, now_str, 250, now_str)
        )
        row = await db.fetchone("SELECT balance, last_daily FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        self.assertEqual(row["balance"], 250)
        self.assertEqual(row["last_daily"], now_str)

    def test_duration_parsing_and_formatting(self):
        d1 = timeutil.parse_duration("10m")
        self.assertEqual(d1.total_seconds(), 600)

        d2 = timeutil.parse_duration("1h30m")
        self.assertEqual(d2.total_seconds(), 5400)

        d3 = timeutil.parse_duration("2d")
        self.assertEqual(d3.total_seconds(), 172800)

        d4 = timeutil.parse_duration("7d")
        self.assertEqual(d4.total_seconds(), 604800)

        self.assertIsNone(timeutil.parse_duration("invalid"))

        # Test formatting
        formatted = timeutil.format_duration(d2)
        self.assertEqual(formatted, "1h 30m")

    def test_math_safe_evaluation(self):
        def eval_str(expr):
            return _safe_eval(ast.parse(expr, mode="eval").body)

        self.assertEqual(eval_str("2 + 2"), 4.0)
        self.assertEqual(eval_str("10 * 5 + 3"), 53.0)
        self.assertEqual(eval_str("(100 - 20) / 4"), 20.0)
        self.assertEqual(eval_str("2 ** 8"), 256.0)

        with self.assertRaises(Exception):
            eval_str("__import__('os').system('ls')")

    def test_automod_regexes(self):
        # Invite regex
        self.assertTrue(bool(INVITE_RE.search("Join my server: https://discord.gg/abcdef")))
        self.assertTrue(bool(INVITE_RE.search("discord.gg/xyz123")))
        self.assertFalse(bool(INVITE_RE.search("Hello world, no invite here!")))

        # Link regex
        self.assertTrue(bool(LINK_RE.search("Check out https://google.com for more")))
        self.assertFalse(bool(LINK_RE.search("Just plain text")))

        # Phishing check
        test_phish = "Free nitro here: https://dlscord-nitro.site/gift"
        has_phish = any(k in test_phish for k in PHISHING_KEYWORDS)
        self.assertTrue(has_phish)

    def test_i18n_translations(self):
        # English
        tr_en = config.tr("en", "mod_ban_success", user="TestUser#0001")
        self.assertIn("TestUser#0001", tr_en)
        self.assertIn("has been banned", tr_en)

        # Persian
        tr_fa = config.tr("fa", "mod_ban_success", user="TestUser#0001")
        self.assertIn("TestUser#0001", tr_fa)
        self.assertIn("بن شد", tr_fa)

    async def test_all_19_cogs_loadable(self):
        bot = OmniBot()
        cogs_dir = Path(__file__).resolve().parents[1] / "bot" / "cogs"
        loaded = 0
        for path in sorted(cogs_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            ext = f"bot.cogs.{path.stem}"
            await bot.load_extension(ext)
            loaded += 1
        self.assertEqual(loaded, 19)
        for name in list(bot.extensions):
            await bot.unload_extension(name)


if __name__ == "__main__":
    unittest.main()
