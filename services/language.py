import json
import logging
from pathlib import Path

import discord
from discord import app_commands

from .database import get_guild_language

logger = logging.getLogger('MusicBot.Language')


class LanguageManager:
    def __init__(self) -> None:
        self.locales: dict[str, dict[str, str]] = {}
        self._reverse_en: dict[str, str] = {}  # English value → key (O(1) lookup)
        self.load_locales()

    def load_locales(self) -> None:
        locales_dir = Path('locales')
        locales_dir.mkdir(exist_ok=True)

        for filepath in locales_dir.glob('*.json'):
            lang_code = filepath.stem
            try:
                self.locales[lang_code] = json.loads(
                    filepath.read_text(encoding='utf-8')
                )
                logger.info("Loaded locale: %s", lang_code)
            except Exception as e:
                logger.error("Failed to load locale %s: %s", filepath.name, e)

        # Build reverse lookup for English strings (value → key)
        en = self.locales.get('en', {})
        self._reverse_en = {v: k for k, v in en.items()}

    async def get_string(self, guild_id: int, key: str, **kwargs: object) -> str:
        lang_code = await get_guild_language(guild_id)

        # Fallback to English if string isn't found in current language
        if lang_code not in self.locales or key not in self.locales[lang_code]:
            lang_code = 'en'

        string = self.locales.get(lang_code, {}).get(key, key)

        try:
            return string.format(**kwargs)
        except KeyError:
            return string  # Format failed, return raw string


language = LanguageManager()


class CommandTranslator(app_commands.Translator):
    def __init__(self) -> None:
        super().__init__()
        self.locale_map: dict[discord.Locale, str] = {
            discord.Locale.hungarian: 'hu',
            discord.Locale.american_english: 'en',
            discord.Locale.british_english: 'en',
        }

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        lang_code = self.locale_map.get(locale, 'en')

        locales_dict = language.locales.get(lang_code, {})

        # O(1) reverse lookup: find the key for this English string
        key = language._reverse_en.get(string.message)
        if key:
            return locales_dict.get(key, string.message)

        # Or if the string is already a key
        if string.message in locales_dict:
            return locales_dict[string.message]

        return None
