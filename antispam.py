from difflib import SequenceMatcher
from datetime import timedelta
import discord

from discord.ext import commands

class GuildAntispamEngine:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.users_last_messages = {}
        self.users_sus_count = {}

    def _is_sus(self, message: discord.Message) -> bool:
        # Check if the user has sent a message since the engine started, if not, remember it and return
        if message.author.id not in self.users_last_messages:
            self.users_last_messages[message.author.id] = message
            return False

        last_message = self.users_last_messages[message.author.id]
        # Remember this message now
        self.users_last_messages[message.author.id] = message

        # If the user has sent a message before, check if some time has passed since the last message
        if (message.created_at - last_message.created_at).total_seconds() > 5:
            # Some time has passed, probably not a spam message
            return False

        # Check if the message is very similar to the last message
        this_message_content = message.content.lower()
        last_message_content = last_message.content.lower()

        # Add attachment filenames to the mix
        for attachment in message.attachments:
            this_message_content += ' ' + attachment.filename.lower()
        for attachment in last_message.attachments:
            last_message_content += ' ' + attachment.filename.lower()

        # Check if the similarity is above 90%
        matcher = SequenceMatcher(None, this_message_content, last_message_content)
        if matcher.ratio() < 0.9:
            # Not similar, probably not a spam message
            return False

        # All checks passed, is a bit sus
        return True

    async def _do_user_mute(self, member: discord.Member, channel: discord.abc.Messageable) -> None:
        await member.timeout(timedelta(days=28), reason='Anti-Spam Engine')

        embed = discord.Embed()
        embed.title = 'Anti-Spam'
        embed.description = (f'Possible spam detected for user: {member.mention}; '
                             f'please contact a moderator to be unmuted')

        await channel.send(embed=embed)


    async def run_on_message(self, message: discord.Message) -> None:
        if type(message.author) is not discord.Member:
            return

        # We don't run the engine on admins
        if message.author.guild_permissions.administrator:
            return

        message_is_sus = self._is_sus(message)

        if message_is_sus:
            if message.author.id not in self.users_sus_count:
                self.users_sus_count[message.author.id] = 1
            else:
                self.users_sus_count[message.author.id] += 1

            if self.users_sus_count[message.author.id] >= 3:
                try:
                    await self._do_user_mute(message.author, message.channel)
                except discord.errors.Forbidden:
                    # We can not mute this user, ignore
                    pass



class AntiSpamCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_antispam_engines = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild.id not in self.guild_antispam_engines:
            self.guild_antispam_engines[message.guild.id] = GuildAntispamEngine(message.guild)

        await self.guild_antispam_engines[message.guild.id].run_on_message(message)
