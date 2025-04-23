import discord
import math

from discord.ext import commands
from discord import app_commands

import db

class TagCog(commands.Cog):
    class TagPaginationView(discord.ui.View):
        def __init__(self, tags: dict[str, str], per_page: int = 25):
            super().__init__(timeout=180)  # 3 minute timeout
            self.tags = tags
            self.per_page = per_page
            self.current_page = 0
            self.total_pages = math.ceil(len(tags) / per_page)
            self.message: discord.Message | None = None

        def get_page_content(self) -> discord.Embed:
            start_idx = self.current_page * self.per_page
            end_idx = start_idx + self.per_page
            current_tags_keys = list(self.tags.keys())[start_idx:end_idx]

            embed = discord.Embed(title="Server Tags")
            for tag_name in current_tags_keys:
                embed.add_field(name=tag_name, value=self.tags[tag_name][:20] + '...' if len(self.tags[tag_name]) > 20 else self.tags[tag_name], inline=False)
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
            return embed

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            if self.current_page > 0:
                self.current_page -= 1
                await interaction.response.edit_message(embed=self.get_page_content(), view=self)
            else:
                await interaction.response.defer()

        @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            if self.current_page < self.total_pages - 1:
                self.current_page += 1
                await interaction.response.edit_message(embed=self.get_page_content(), view=self)
            else:
                await interaction.response.defer()

        async def on_timeout(self) -> None:
            # Remove buttons when the view times out
            self.clear_items()
            if self.message is not None:
                await self.message.edit(view=self)

    def __init__(self, bot):
        self.bot = bot

    def _create_tag_embed(self, tag_name: str, tag_content: str) -> discord.Embed:
        embed = discord.Embed(title=tag_name)
        embed.description = tag_content
        return embed

    @commands.hybrid_command(name='tag', aliases=['t', 'rtfm'])
    async def tag(self, ctx: commands.Context, tag_name: str) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild!', ephemeral=True)
            return

        tag_contents = db.get_guild_tag(ctx.guild, tag_name)
        if tag_contents is None:
            await ctx.send(f'Tag `{tag_name}` not found!', ephemeral=True)
            return
        else:
            await ctx.send(embed=self._create_tag_embed(tag_name, tag_contents))

    @app_commands.command()
    async def set_tag(self, interaction: discord.Interaction, tag_name: str, tag_content: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('This command can only be used in a guild!', ephemeral=True)
            return

        if len(tag_content) > 2000:
            await interaction.response.send_message('Tag content is too long!', ephemeral=True)
            return

        db.set_guild_tag(interaction.guild, tag_name, tag_content)
        await interaction.response.send_message(f'Successfully set tag `{tag_name}`')

    @app_commands.command()
    async def delete_tag(self, interaction: discord.Interaction, tag_name: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('This command can only be used in a guild!', ephemeral=True)
            return

        db.remove_guild_tag(interaction.guild, tag_name)
        await interaction.response.send_message(f'Successfully deleted tag `{tag_name}`')

    @app_commands.command()
    async def get_all_tags(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('This command can only be used in a guild!', ephemeral=True)
            return

        tags = db.get_all_guild_tags(interaction.guild)
        if len(tags) == 0:
            await interaction.response.send_message('No tags found!', ephemeral=True)
            return

        # Create the pagination view
        view = self.TagPaginationView(tags)
        # Send initial message
        await interaction.response.send_message(embed=view.get_page_content(), view=view)
        # Store the message for timeout handling
        view.message = await interaction.original_response()


