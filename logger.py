import discord
import datetime

from discord.ext import commands
from discord import app_commands, role

from pprint import pprint

import db

class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def __get_user_string(self, user: discord.User | discord.Member) -> str:
        return f'{user.mention} ({user.name} - {user.id})'

    def __roles_array_to_string(self, roles: list) -> str:
        ret = ''
        for role in roles:
            if ret != '':
                ret += ', '
            ret += role.name
        return ret

    def __add_permission_changes_to_embed(self, embed, before, after):
        # Check if permissions are different
        if before.permissions != after.permissions:
            # Iterate both and add a field for each different one
            before_perms_itered = iter(before.permissions)
            after_perms_itered = iter(after.permissions)
            for compare in zip(before_perms_itered, after_perms_itered):
                before_perm = compare[0]
                after_perm = compare[1]

                # Assert the perm is the same
                assert before_perm[0] == after_perm[0]

                # If the value is not the same, add a field for that
                if before_perm[1] != after_perm[1]:
                    embed.add_field(name=f'Permission: {after_perm[0]}', value=f'{before_perm[1]} -> {after_perm[1]}')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        db.insert_message_into_db(message)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, event: discord.RawMessageDeleteEvent):
        guild = self.bot.get_guild(event.guild_id)
        log_channel = db.get_guild_log_channel(guild)

        if log_channel is None:
            return

        embed = discord.Embed()

        if event.cached_message is not None:
            message = event.cached_message
            embed.title = 'Message deleted'
            embed.description = (f'By {self.__get_user_string(message.author)})\n'
                                 f'```\n{message.content}\n```')
        else:
            # See if we can get the message from DB
            logged_message = db.get_message_from_db(event.message_id)
            if logged_message is None:
                embed.title = 'Message deleted'
                embed.description = (f'Message ID: {event.message_id}\n'
                                     f'Message not in cache, and therefore can not be logged!')
            else:
                embed.title = 'Message deleted'
                embed.description = (f'Message ID: {event.message_id}\n'
                                     f'Known contents:\n```\n{logged_message.contents}\n```\n'
                                     f'Message was stored in DB, not in cache - bot went offline between message '
                                     f'posting and message deleting')
                db.delete_message_from_db(event.message_id)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Do not log when we edit our own messages
        if before.author.id == self.bot.user.id:
            return

        log_channel = db.get_guild_log_channel(before.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Message edited'
        embed.description = (f'Message edited by {self.__get_user_string(after.author)})\n'
                             f'```\n{before.content}\n```\n->'
                             f'```\n{after.content}\n```\n')

        await log_channel.send(embed=embed)
        db.insert_message_into_db(after)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log_channel = db.get_guild_log_channel(member.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Member joined'
        embed.description = self.__get_user_string(member)
        embed.add_field(name='Account created', value=member.created_at.strftime('%m/%d/%Y %I:%M:%S %p'))
        if member.display_avatar is not None:
            embed.set_thumbnail(url=member.display_avatar.url)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_member_remove(self, event: discord.RawMemberRemoveEvent):
        guild = self.bot.get_guild(event.guild_id)
        log_channel = db.get_guild_log_channel(guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Member left'
        embed.description = f'{self.__get_user_string(event.user)})'
        if event.user.display_avatar is not None:
            embed.set_thumbnail(url=event.user.display_avatar.url)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        log_channel = db.get_guild_log_channel(guild)
        if log_channel is None:
            return

        # We fetch several, in case something delayed this function being called
        audit_log_entries = [entry async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.ban)]
        # Find the entry where this user was banned
        found_entry = None
        for entry in audit_log_entries:
            if entry.target.id == user.id:
                found_entry = entry
                break

        embed = discord.Embed()
        embed.title = 'Member banned'
        embed.description = f'{self.__get_user_string(user)})'
        if found_entry is not None:
            embed.add_field(name='Ban reason', value=found_entry.reason)
            responsible_mod = found_entry.user
            embed.add_field(name='Responsible mod', value=self.__get_user_string(responsible_mod))
        if user.display_avatar is not None:
            embed.set_thumbnail(url=user.display_avatar.url)
        await log_channel.send(embed=embed)

    async def __check_and_log_nick_update(self, before: discord.Member, after: discord.Member,
                                          log_channel: discord.TextChannel):
        if before.nick != after.nick:
            embed = discord.Embed()
            embed.title = 'Nickname updated'
            embed.description = f'User: {self.__get_user_string(after)}'
            embed.add_field(name='Old nickname', value=before.nick)
            embed.add_field(name='New nickname', value=after.nick)
            await log_channel.send(embed=embed)

    async def __check_and_log_roles_update(self, before: discord.Member, after: discord.Member,
                                           log_channel: discord.TextChannel):
        if before.roles != after.roles:
            embed = discord.Embed()
            embed.title = 'Roles updated'
            embed.description = f'User: {self.__get_user_string(after)}'
            embed.add_field(name='Old roles', value=self.__roles_array_to_string(before.roles))
            embed.add_field(name='New roles', value=self.__roles_array_to_string(after.roles))
            if after.display_avatar is not None:
                embed.set_thumbnail(url=after.display_avatar.url)
            await log_channel.send(embed=embed)

    async def __check_and_log_timeout_update(self, before: discord.Member, after: discord.Member,
                                             log_channel: discord.TextChannel):
        if before.timed_out_until != after.timed_out_until:
            embed = discord.Embed()
            embed.title = 'Timeout updated'
            embed.description = f'User: {self.__get_user_string(after)}'
            # Check if there was a previous timeout and if there was, check if it is in the past (aka expired)
            if before.timed_out_until is not None and before.timed_out_until > datetime.datetime.now(tz=datetime.timezone.utc):
                embed.add_field(name='Old timeout', value=f'Until <t:{int(before.timed_out_until.timestamp())}:f>')

            # Check if the timeout was removed manually.
            # We do not get events if the timeout lapsed, but we should get them if a moderator/bot removes it by hand.
            if after.timed_out_until is not None and after.timed_out_until > datetime.datetime.now(tz=datetime.timezone.utc):
                embed.add_field(name='New timeout', value=f'Until <t:{int(after.timed_out_until.timestamp())}:f>')
            else:
                embed.title = 'Timeout removed'
            if after.display_avatar is not None:
                embed.set_thumbnail(url=after.display_avatar.url)
            await log_channel.send(embed=embed)

    async def __check_and_log_username_update(self, before: discord.User, after: discord.User,
                                              log_channel: discord.TextChannel):
        if before.name != after.name:
            embed = discord.Embed()
            embed.title = 'Username updated'
            embed.description = f'User: {self.__get_user_string(after)}'
            embed.add_field(name='Old username', value=before.name)
            embed.add_field(name='New username', value=after.name)
            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        for guild in after.mutual_guilds:
            log_channel = db.get_guild_log_channel(guild)

            if log_channel is None:
                return

            await self.__check_and_log_username_update(before, after, log_channel)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        log_channel = db.get_guild_log_channel(after.guild)

        if log_channel is None:
            return

        await self.__check_and_log_nick_update(before, after, log_channel)
        await self.__check_and_log_roles_update(before, after, log_channel)
        await self.__check_and_log_timeout_update(before, after, log_channel)

    #
    # Channels
    #

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        log_channel = db.get_guild_log_channel(channel.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Channel created'
        embed.description = f'Channel: {channel.name} ({channel.id}, {channel.mention})'
        if channel.category is not None:
            embed.add_field(name='Category', value=channel.category.name)
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        log_channel = db.get_guild_log_channel(channel.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Channel deleted'
        embed.description = f'Channel: {channel.name} ({channel.id})'
        if channel.category is not None:
            embed.add_field(name='Category', value=channel.category.name)
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        log_channel = db.get_guild_log_channel(after.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Channel updated'
        embed.description = f'Channel: {after.name} ({after.id}, {after.mention})'

        # Check if name changed
        if before.name != after.name:
            embed.add_field(name='Old name', value=before.name)

        # Check if category changed
        if before.category != after.category:
            embed.add_field(name='Category', value=f'{before.category.name} -> {after.category.name}')

        # Check if position changed
        if before.position != after.position:
            embed.add_field(name='Position', value=f'{before.position} -> {after.position}')

        # Check if permissions now synced
        if before.permissions_synced != after.permissions_synced:
            embed.add_field(name='Permissions synced', value=f'{before.permissions_synced} -> {after.permissions_synced}')

        await log_channel.send(embed=embed)

    #
    # Roles
    #

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        log_channel = db.get_guild_log_channel(role.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Role created'
        embed.description = f'Role: {role.name} ({role.id})'
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        log_channel = db.get_guild_log_channel(role.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Role deleted'
        embed.description = f'Role: {role.name} ({role.id})'
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        log_channel = db.get_guild_log_channel(after.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Role updated'
        embed.description = f'Role: {after.name} ({after.id})'

        # Check if name is different
        if before.name != after.name:
            embed.add_field(name='Old name', value=before.name)

        self.__add_permission_changes_to_embed(embed, before, after)

        await log_channel.send(embed=embed)
