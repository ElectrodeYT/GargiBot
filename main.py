import os
from typing import Callable, Awaitable

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

async def command_error_handler_impl(send_err_embed: Callable[[str], Awaitable[None]],
                                     error: commands.CommandError | app_commands.AppCommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions) or isinstance(error, app_commands.errors.MissingPermissions):
        await send_err_embed(f'You are missing the following permissions: {", ".join(error.missing_permissions)}')
    elif isinstance(error, commands.MissingRequiredArgument):
        await send_err_embed(f'You are missing the following required argument: {error.param.name}')
    elif isinstance(error, commands.BadArgument):
        await send_err_embed(f'You have provided an invalid argument: {error}')
    elif isinstance(error, commands.NoPrivateMessage) or isinstance(error, app_commands.errors.NoPrivateMessage):
        await send_err_embed('This command cannot be used in private messages.')
    elif isinstance(error, commands.CheckFailure) or isinstance(error, app_commands.errors.CheckFailure):
        await send_err_embed('You do not have permission to use this command.')
    elif isinstance(error, commands.BotMissingPermissions) or isinstance(error,
                                                                         app_commands.errors.BotMissingPermissions):
        await send_err_embed(f'I am missing the following permissions: {", ".join(error.missing_permissions)}')
    elif isinstance(error, commands.CommandOnCooldown) or isinstance(error, app_commands.errors.CommandOnCooldown):
        await send_err_embed(f'This command is on cooldown. Try again in {error.retry_after:.2f} seconds.')
    elif isinstance(error, commands.DisabledCommand):
        await send_err_embed('This command is disabled.')
    elif isinstance(error, commands.MaxConcurrencyReached):
        await send_err_embed(f'This command has reached its maximum concurrency limit: {error.number}')
    elif isinstance(error, commands.UserInputError):
        await send_err_embed(f'You have provided an invalid input: {error}')
    else:
        await send_err_embed(f'An unexpected error occurred: {error}')
        raise error

class ErrorHandlingTree(app_commands.CommandTree):
    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        print('in tree error handler: ', interaction, error)

        async def send_err_embed(description: str) -> None:
            embed = discord.Embed(description=description, colour=discord.Colour.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await command_error_handler_impl(send_err_embed, error)

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='.!', intents=intents, tree_cls=ErrorHandlingTree)

    async def startup(self) -> None:
        await bot.wait_until_ready()
        await bot.tree.sync()  # If you want to define specific guilds, pass a discord object with id (Currently, this is global)

        print('Sucessfully synced applications commands')

        print('Init DB for all guilds')
        for guild in bot.guilds:
            db.init_guild(guild)

        print(f'Finished bot startup, connected as {bot.user}')

    async def on_guild_join(self, guild: discord.Guild) -> None:
        print(f'Joined guild {guild.name} ({guild.id})')
        db.init_guild(guild)

    async def setup_hook(self) -> None:
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

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        print('in command error handler: ', ctx, error)

        async def send_err_embed(description: str) -> None:
            embed = discord.Embed(description=description, colour=discord.Colour.red())
            await ctx.send(embed=embed, ephemeral=True)

        await command_error_handler_impl(send_err_embed, error)

bot = Bot()
bot.run(token)