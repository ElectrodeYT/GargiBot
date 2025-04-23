import os
import discord
from discord.ext import commands
from discord import app_commands

import config
import db
import logger
import moderation
import tags

# Read token enviroment variable
token = os.environ["BOT_TOKEN"]

intents = discord.Intents.all()
added_cogs = False

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='.!', intents=intents)

    async def startup(self):
        await bot.wait_until_ready()
        await bot.tree.sync()  # If you want to define specific guilds, pass a discord object with id (Currently, this is global)
        print('Sucessfully synced applications commands')

        print('Init DB for all guilds')
        for guild in bot.guilds:
            db.init_guild(guild)

        print(f'Finished bot startup, connected as {bot.user}')

    async def on_guild_join(self, guild: discord.Guild):
        print(f'Joined guild {guild.name} ({guild.id})')
        db.init_guild(guild)

    async def setup_hook(self):
        global added_cogs

        # As far as I can tell, if the connection drops, this seems to fire again.
        # Stop adding the same cogs over and over again.
        if not added_cogs:
            await self.add_cog(config.ConfigCog(bot))
            await self.add_cog(logger.LoggerCog(bot))
            await self.add_cog(moderation.ModerationCog(bot))
            await self.add_cog(tags.TagCog(bot))
            added_cogs = True
        self.loop.create_task(self.startup())

bot = Bot()
bot.run(token)