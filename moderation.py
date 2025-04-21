import discord
import db

from discord.ext import commands


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def __create_success_embed(self, user_affected, type):
        embed = discord.Embed()
        embed.title = f'Member {type}'
        embed.description = f'**{user_affected.name}** has been {type}.'

        if type == 'banned':
            embed.colour = discord.Colour.red()
        elif type == 'unbanned':
            embed.colour = discord.Colour.green()
        elif type == 'kick':
            embed.colour = discord.Colour.yellow()

        return embed

    def __create_text_embed(self, text):
        embed = discord.Embed()
        embed.description = text
        return embed

    def __create_log_embed(self, user_affected: discord.User, responsible_mod, reason, type):
        embed = discord.Embed()
        embed.title = f'Member {type}'

        if type == 'banned':
            embed.colour = discord.Colour.red()
        elif type == 'unbanned':
            embed.colour = discord.Colour.green()
        elif type == 'kick':
            embed.colour = discord.Colour.yellow()

        embed.add_field(name='Member', value=f'{user_affected.mention} ({user_affected.name} - {user_affected.id})')
        embed.add_field(name='Action', value=type)
        embed.add_field(name='Responsible Moderator', value=responsible_mod)
        return embed

    async def __send_embed_to_log(self, guild: discord.Guild, embed):
        log_channel = db.get_guild_log_channel(guild)
        if log_channel is None:
            return

        await log_channel.send(embed=embed)

    async def __send_dm(self, user_affected: discord.User, guild: discord.Guild, action_type, reason: str | None = None) -> bool:
        embed = discord.Embed()
        embed.title = f'You have been {action_type} from {guild.name}.'
        if reason is None:
            embed.description = f'You have been {action_type}.'
        else:
            embed.description = f'You have been {action_type} for the following reason: `{reason}`.'
        try:
            await user_affected.send(embed=embed)
        except discord.Forbidden:
            return False
        except discord.HTTPException:
            print(f'Failed to send DM to {user_affected.name} with HTTPException!')
            return False
        return True

    @commands.hybrid_command(name='ban', description='Ban a member from this guild.', aliases=['naenae'])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user_to_ban: discord.User, reason: str | None = None):
        print(f'Banning user {user_to_ban.name} (responsible mod: {ctx.author.name})')
        await self.__send_dm(user_to_ban, action_type='banned', guild=ctx.guild, reason=reason)

        db.add_ban(ctx.guild, banned_user=user_to_ban, responsible_mod=ctx.author)
        await ctx.guild.ban(user=user_to_ban, reason=f'By {ctx.author.name} - {reason}', delete_message_days=0)
        await ctx.send(embed=self.__create_success_embed(user_affected=user_to_ban, type="banned"))
        await self.__send_embed_to_log(ctx.guild, self.__create_log_embed(user_affected=user_to_ban,
                                                                          responsible_mod=ctx.author,
                                                                          reason=reason,
                                                                          type='banned'))

    @commands.hybrid_command(name='kick', description='Kick a member from this guild.', aliases=['dabon'])
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, user_to_kick: discord.User, reason: str | None = None):
        print(f'Kicking user {user_to_kick.name} (responsible mod: {ctx.author.name})')
        await self.__send_dm(user_to_kick, action_type='kicked', guild=ctx.guild, reason=reason)

        await ctx.guild.kick(user=user_to_kick, reason=reason)
        await ctx.send(embed=self.__create_success_embed(user_affected=user_to_kick, type="kicked"))
        await self.__send_embed_to_log(ctx.guild, self.__create_log_embed(user_affected=user_to_kick,
                                                                          responsible_mod=ctx.author,
                                                                          reason=reason,
                                                                          type='kicked'))

    @commands.hybrid_command(name='unban', description='Unban a member from this guild.', aliases=['whip'])
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_to_unban: discord.User, reason: str | None = None):
        print(f'Unbanning user {user_to_unban.name} (responsible mod: {ctx.author.name})')
        try:
            await ctx.guild.unban(user=user_to_unban, reason=reason)
        except discord.errors.NotFound:
            await ctx.send(embed=self.__create_text_embed('This user is not banned!'))
            return
        await ctx.send(embed=self.__create_success_embed(user_affected=user_to_unban, type="unbanned"))
        await self.__send_embed_to_log(ctx.guild, self.__create_log_embed(user_affected=user_to_unban,
                                                                          responsible_mod=ctx.author,
                                                                          reason=reason,
                                                                          type='unbanned'))

