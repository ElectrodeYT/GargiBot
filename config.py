import sqlite3
import discord

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
        cursor = db.config_db.cursor()
        cursor.execute('INSERT OR REPLACE INTO config(guild, log_channel) VALUES (?, ?)',
                       (interaction.guild.id, channel.id))
        cursor.close()
        db.config_db.commit()

        print(db.get_guild_log_channel(interaction.guild))

        await interaction.response.send_message(f'Successfully set log channel to {channel.name}')

    @app_commands.command()
    @commands.has_permissions(administrator=True)
    async def disable_logging(self, interaction: discord.Interaction):
        cursor = db.config_db.cursor()
        cursor.execute('INSERT OR REPLACE INTO config(guild, log_channel) VALUES (?, ?)',
                       (interaction.guild.id, 0))
        cursor.close()
        db.config_db.commit()
        await interaction.response.send_message(f'Disabled logging')


    @commands.hybrid_command(name='about')
    async def about(self, ctx: commands.Context):
        embed = discord.Embed(
            title='GargiBot!',
            description='Open-source moderation discord bot\n'
                        'Source code: [here!](https://github.com/ElectrodeYT/GargiBot)',
            url='https://github.com/ElectrodeYT/GargiBot',
            colour=discord.Colour.blue()
        )
        embed.set_image(url='https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif')
        await ctx.send(embed=embed)