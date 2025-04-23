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
    @app_commands.describe(
        type='The type of channel to set',
        channel='The channel to set; don\'t pass to disable relevant feature'
    )
    async def set_channel(self, interaction: discord.Interaction, type: Literal['Log', 'Active Users', 'Total Users'],
                          channel: discord.TextChannel | discord.VoiceChannel | None = None):
        type_to_sql_column = {
            'Log': 'log_channel',
            'Active Users': 'active_user_stat_channel',
            'Total Users': 'total_users_stat_channel'
        }
        assert type in type_to_sql_column, f'Invalid type: {type}'

        cursor = db.sqlite_db.cursor()
        if channel is None:
            cursor.execute('UPDATE config SET ' + type_to_sql_column[type] + ' = NULL WHERE guild = ?', (interaction.guild.id,))
        else:
            cursor.execute('UPDATE config SET ' + type_to_sql_column[type] + ' = ? WHERE guild = ?', (channel.id, interaction.guild.id))

        cursor.close()
        db.sqlite_db.commit()

        if channel is None:
            await interaction.response.send_message(f'Successfully disabled {type} channel', ephemeral=True)
        else:
            await interaction.response.send_message(f'Successfully set {type} channel to {channel.mention}', ephemeral=True)

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
