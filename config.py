import discord

from typing import Literal

from discord.ext import commands
from discord import app_commands

import db

class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command()
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        print(f'Setting log channel to {channel.name} ({channel.id}) for '
              f'guild {interaction.guild.name} ({interaction.guild.id})')
        cursor = db.sqlite_db.cursor()
        cursor.execute('UPDATE config SET log_channel = ? WHERE guild = ?', (channel.id, interaction.guild.id))
        cursor.close()
        db.sqlite_db.commit()

        print(db.get_guild_log_channel(interaction.guild))

        await interaction.response.send_message(f'Successfully set log channel to {channel.name}')

    @app_commands.command()
    @commands.has_permissions(administrator=True)
    async def disable_logging(self, interaction: discord.Interaction):
        cursor = db.sqlite_db.cursor()
        cursor.execute('UPDATE config SET log_channel = NULL WHERE guild = ?', (interaction.guild.id,))
        cursor.close()
        db.sqlite_db.commit()
        await interaction.response.send_message(f'Disabled logging')

    @app_commands.command()
    @commands.has_permissions(administrator=True)
    @app_commands.describe(type='The type of image to set', url='The URL of the image; leave empty to set to default.')
    async def set_image_url(self, interaction: discord.Interaction, type: Literal['ban', 'unban', 'kick'], url: str = None):
        db.set_image_url(interaction.guild, url, type)
        if url is not None:
            await interaction.response.send_message(f'Successfully set {type} image URL to {url}', ephemeral=True)
        else:
            await interaction.response.send_message(f'Successfully set {type} image URL to default', ephemeral=True)

    @commands.hybrid_command(name='about')
    async def about(self, ctx: commands.Context):
        embed = discord.Embed(
            title='GargiBot!',
            description='Open-source moderation discord bot\n'
                        'Source code: [here!](https://github.com/ElectrodeYT/GargiBot)',
            url='https://github.com/ElectrodeYT/GargiBot',
            colour=discord.Colour.blue()
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif')
        await ctx.send(embed=embed)