from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

RULES_URLS = [
    "https://rules2.clearurls.xyz/data.minify.json",
    "https://rules1.clearurls.xyz/data.minify.json",
    "https://raw.githubusercontent.com/ClearURLs/Rules/master/data.min.json",
]

CACHE_PATH = Path("clearurls_cache.json")
REFRESH_INTERVAL_HOURS = 24
MAX_URLS_PER_MESSAGE = 10
MAX_DISCORD_MSG_LEN = 1950


@dataclass
class Provider:
    name: str
    url_pattern: re.Pattern
    rules: list[re.Pattern]
    raw_rules: list[re.Pattern]
    referral_marketing: list[re.Pattern]
    exceptions: list[re.Pattern]
    complete_provider: bool = False


class ClearURLsRuleset:
    def __init__(self, cache_path: Path = CACHE_PATH):
        self.cache_path = cache_path
        self.providers: list[Provider] = []
        self._raw: dict | None = None
        self.last_updated: float = 0.0

    async def fetch_raw(self, session: aiohttp.ClientSession) -> dict | None:
        for url in RULES_URLS:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    data = json.loads(text)
                    if isinstance(data, dict) and "providers" in data:
                        log.info("Fetched ClearURLs rules from %s (%d providers)", url, len(data["providers"]))
                        return data
            except Exception as e:
                log.warning("Failed to fetch ClearURLs rules from %s: %s", url, e)
        return None

    def _compile(self, patterns: list[str]) -> list[re.Pattern]:
        compiled = []
        for p in patterns:
            try:
                compiled.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                log.debug("Skipping bad regex %r: %s", p, e)
        return compiled

    def load_from_dict(self, data: dict) -> None:
        providers = []
        for name, entry in data.get("providers", {}).items():
            if not isinstance(entry, dict):
                continue
            url_pat_str = entry.get("urlPattern")
            if not url_pat_str:
                continue
            try:
                url_pattern = re.compile(url_pat_str, re.IGNORECASE)
            except (KeyError, re.error):
                continue

            rules = self._compile([f"^{r}$" for r in entry.get("rules", [])])
            raw_rules = self._compile(entry.get("rawRules", []))
            referral = self._compile([f"^{r}$" for r in entry.get("referralMarketing", [])])
            exceptions = self._compile(entry.get("exceptions", []))

            providers.append(Provider(
                name=name,
                url_pattern=url_pattern,
                rules=rules,
                raw_rules=raw_rules,
                referral_marketing=referral,
                exceptions=exceptions,
                complete_provider=entry.get("completeProvider", False),
            ))
        self.providers = providers
        self._raw = data
        self.last_updated = time.time()

    def save_cache(self) -> None:
        if self._raw is None:
            return
        temp_path = self.cache_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps({
                "fetched_at": self.last_updated,
                "data": self._raw,
            }))
            temp_path.replace(self.cache_path)
        except Exception as e:
            log.warning("Failed to write ClearURLs cache: %s", e)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def load_cache(self) -> bool:
        if not self.cache_path.exists():
            return False
        try:
            cached = json.loads(self.cache_path.read_text())
            if not isinstance(cached, dict) or "data" not in cached:
                return False
            self.load_from_dict(cached["data"])
            self.last_updated = cached.get("fetched_at", 0.0)
            log.info("Loaded ClearURLs rules from disk cache (%d providers)", len(self.providers))
            return True
        except Exception as e:
            log.warning("Failed to load ClearURLs cache: %s", e)
            return False

    async def refresh(self, session: aiohttp.ClientSession) -> bool:
        data = await self.fetch_raw(session)
        if data is None:
            return False
        self.load_from_dict(data)
        self.save_cache()
        return True

    def providers_for(self, url: str) -> list[Provider]:
        return [p for p in self.providers if p.url_pattern.search(url)]


def _apply_raw_rules(url: str, providers: list[Provider]) -> tuple[str, bool]:
    changed = False
    current_url = url
    for p in providers:
        for pat in p.raw_rules:
            new_url, count = pat.subn("", current_url)
            if count > 0:
                current_url = new_url
                changed = True
    return current_url, changed


def _strip_query_params(url: str, providers: list[Provider], include_referral: bool) -> tuple[str, bool]:
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not query_params:
        return url, False

    all_param_patterns: list[re.Pattern] = []
    for p in providers:
        all_param_patterns.extend(p.rules)
        if include_referral:
            all_param_patterns.extend(p.referral_marketing)

    if not all_param_patterns:
        return url, False

    cleaned_params = []
    changed = False
    for key, val in query_params:
        if any(pat.match(key) for pat in all_param_patterns):
            changed = True
        else:
            cleaned_params.append((key, val))

    if not changed:
        return url, False

    new_query = urllib.parse.urlencode(cleaned_params)
    cleaned = urllib.parse.urlunparse(parsed._replace(query=new_query))
    return cleaned, True


def _is_excepted(url: str, providers: list[Provider]) -> bool:
    for p in providers:
        if any(exc.search(url) for exc in p.exceptions):
            return True
    return False


def _is_complete_block(url: str, providers: list[Provider]) -> bool:
    return any(p.complete_provider for p in providers)


def _trim_trailing_punct(url: str) -> str:
    while url and url[-1] in '.,;!?:)]}':
        if url[-1] == ')' and url.count('(') >= url.count(')'):
            break
        if url[-1] == ']' and url.count('[') >= url.count(']'):
            break
        if url[-1] == '}' and url.count('{') >= url.count('}'):
            break
        url = url[:-1]
    return url


class URLCleaner:
    def __init__(self, ruleset: ClearURLsRuleset, strip_referral_marketing: bool = False):
        self.ruleset = ruleset
        self.strip_referral_marketing = strip_referral_marketing

    def clean_text_urls(self, text: str) -> list[str]:
        suppressed_matches = set(re.findall(r'<https?://[^\s>]+>', text))
        suppressed_urls = {m.strip('<>') for m in suppressed_matches}

        urls = re.findall(r'https?://[^\s<>"]+', text)
        cleaned_urls = []
        seen = set()

        for url in urls:
            raw_url = _trim_trailing_punct(url)
            if raw_url in suppressed_urls:
                continue

            providers = self.ruleset.providers_for(raw_url)
            if not providers:
                continue
            if _is_excepted(raw_url, providers):
                continue
            if _is_complete_block(raw_url, providers):
                continue

            current_url, raw_changed = _apply_raw_rules(raw_url, providers)
            cleaned, query_changed = _strip_query_params(current_url, providers, self.strip_referral_marketing)

            if (raw_changed or query_changed) and cleaned not in seen:
                seen.add(cleaned)
                cleaned_urls.append(cleaned)
                if len(cleaned_urls) >= MAX_URLS_PER_MESSAGE:
                    break

        return cleaned_urls


class URLCleanerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ruleset = ClearURLsRuleset()
        self.cleaner = URLCleaner(self.ruleset)
        self._session: aiohttp.ClientSession | None = None

        self.ruleset.load_cache()
        self.refresh_rules.start()

    async def cog_unload(self) -> None:
        self.refresh_rules.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    @tasks.loop(hours=REFRESH_INTERVAL_HOURS)
    async def refresh_rules(self):
        session = await self._get_session()
        ok = await self.ruleset.refresh(session)d
        if not ok and not self.ruleset.providers:
            log.error("Could not fetch ClearURLs rules and no cache is available; URL cleaning disabled.")

    @refresh_rules.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self.ruleset.providers:
            return

        cleaned_urls = self.cleaner.clean_text_urls(message.content)
        if not cleaned_urls:
            return

        try:
            await message.edit(suppress=True)
        except (discord.Forbidden, discord.HTTPException):
            pass

        header = "Link without trackers: " if len(cleaned_urls) == 1 else "Links without trackers: "
        chunks = []
        current_chunk = header

        for url in cleaned_urls:
            item = f"{url} "
            if len(current_chunk) + len(item) > MAX_DISCORD_MSG_LEN:
                chunks.append(current_chunk.strip())
                current_chunk = item
            else:
                current_chunk += item

        if current_chunk and current_chunk.strip() != header.strip():
            chunks.append(current_chunk.strip())

        for chunk in chunks:
            try:
                await message.reply(chunk, mention_author=False)
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning("Failed to send cleaned URL reply: %s", e)
                break



async def setup(bot: commands.Bot):
    await bot.add_cog(URLCleanerCog(bot))