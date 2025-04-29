import discord
import datetime

from discord.ext import commands, tasks
from common_helpers import get_formatted_user_string

from pprint import pprint

import db

class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.currently_known_guild_activity_levels = {}
        self.last_active_user_channel_update = {}
        self.do_total_user_count_update_globally.start()

    def _roles_array_to_string(self, roles: list) -> str:
        ret = ''
        for role in roles:
            if ret != '':
                ret += ', '
            ret += role.name
        return ret

    def _add_permission_changes_to_embed(self, embed, before, after):
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

    async def _handle_active_user_stat_change(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        db.update_user_activity(guild, user)

        active_user_stat_channel = db.get_guild_active_user_stat_channel(guild)
        if active_user_stat_channel is None:
            return

        active_user_count = db.get_this_day_active_user_count(guild)
        last_day_active_user_count = db.get_last_day_active_user_count(guild)
        if guild.id not in self.currently_known_guild_activity_levels or self.currently_known_guild_activity_levels[guild.id] != active_user_count:
            self.currently_known_guild_activity_levels[guild.id] = active_user_count
            if guild.id not in self.last_active_user_channel_update or (datetime.datetime.now(datetime.timezone.utc) - self.last_active_user_channel_update[guild.id]).total_seconds() > 60:
                self.last_active_user_channel_update[guild.id] = datetime.datetime.now(datetime.timezone.utc)
                await active_user_stat_channel.edit(name=f'Active Today: {active_user_count} ({active_user_count - last_day_active_user_count})')
                print(f'Active user count updated for guild {guild.id} to {active_user_count}')

    # We also run this function every night at 1 minute past UTC midnight
    @tasks.loop(time=datetime.time(hour=0, minute=1, tzinfo=datetime.timezone.utc))
    async def do_total_user_count_update_globally(self):
        print('Updating total user count globally')
        for guild in self.bot.guilds:
            await self._handle_total_user_count_change(guild)

    async def _handle_total_user_count_change(self, guild: discord.Guild) -> None:
        db.update_total_user_count(guild)

        total_user_count_stat_channel = db.get_guild_total_users_stat_channel(guild)
        if total_user_count_stat_channel is None:
            return

        assert guild.member_count is not None
        total_user_count = guild.member_count
        last_day_total_user_count = db.get_last_day_total_user_count(guild)

        await total_user_count_stat_channel.edit(name=f'Total Users: {total_user_count} '
                                                      f'({total_user_count - last_day_total_user_count if last_day_total_user_count is not None else 'N/A'})')

    #
    # Messages
    #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # We await this at the end to try and multitask this stuff a bit more
        if message.guild is not None and message.author is not None and message.author.id != self.bot.user.id:
            stat_update_coroutine = self._handle_active_user_stat_change(message.guild, message.author)
        db.insert_message_into_db(message)

        if 'stat_update_coroutine' in locals():
            await stat_update_coroutine

    @commands.Cog.listener()
    async def on_raw_message_delete(self, event: discord.RawMessageDeleteEvent) -> None:
        guild = self.bot.get_guild(event.guild_id)
        log_channel = db.get_guild_log_channel(guild)

        if log_channel is None:
            return

        embed = discord.Embed()

        if event.cached_message is not None:
            message = event.cached_message
            embed.title = 'Message deleted'
            embed.description = (f'By {get_formatted_user_string(message.author)}) in {message.channel.mention}\n'
                                 f'```\n{message.content}\n```')
        else:
            # See if we can get the message from DB
            logged_message = db.get_message_from_db(event.message_id)
            if logged_message is None:
                embed.title = 'Message deleted'
                embed.description = (f'Message ID: {event.message_id}\n'
                                     f'Message not in cache or DB, and therefore can not be logged!')
            else:
                embed.title = 'Message deleted'
                embed.description = (f'Message ID: {event.message_id}\n'
                                     f'Known contents:\n```\n{logged_message.contents}\n```\n'
                                     f'Message was stored in DB, not in cache - bot went offline between message '
                                     f'posting and message deleting')
                db.delete_message_from_db(event.message_id)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, event: discord.RawMessageUpdateEvent) -> None:
        # Do not log our own message edits
        if event.message.author.id == self.bot.user.id:
            return

        guild = self.bot.get_guild(event.guild_id)
        log_channel = db.get_guild_log_channel(guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Message edited'
        embed.description = (f'Message edited by {get_formatted_user_string(event.message.author)}) '
                             f'in {event.message.channel.mention} ([link]({event.message.jump_url}))')

        old_content: str | None = None

        # If the message is cached, use that to get the old content, else, check the DB
        if event.cached_message is not None:
            old_content = event.cached_message.content
        else:
            logged_message = db.get_message_from_db(event.message_id)
            if logged_message is not None:
                old_content = logged_message.contents
                embed.set_footer(text='Message found in DB, but not in cache when message edited; '
                                      'old version of message may not be the most recent previous '
                                      'version')

        # If the old and new content is the same, this likely was a embed-only edit; we can and should ignore this.
        if old_content is not None and old_content == event.message.content:
            return

        # Update the message in the DB
        db.insert_message_into_db(event.message)

        if old_content is not None:
            embed.add_field(name='Old message', value=f'```\n{old_content}\n```')
        else:
            embed.set_footer(text='Message not found in cache or DB; change can not be logged')

        embed.add_field(name='New message', value=f'```\n{event.data["content"]}\n```')

        await log_channel.send(embed=embed)

    #
    # Members and Users
    #

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild_total_member_count_update_coroutine = self._handle_total_user_count_change(member.guild)
        log_channel = db.get_guild_log_channel(member.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Member joined'
        embed.description = get_formatted_user_string(member)
        embed.add_field(name='Account created', value=member.created_at.strftime('%m/%d/%Y %I:%M:%S %p'))
        if member.display_avatar is not None:
            embed.set_thumbnail(url=member.display_avatar.url)

        await log_channel.send(embed=embed)
        await guild_total_member_count_update_coroutine

    @commands.Cog.listener()
    async def on_raw_member_remove(self, event: discord.RawMemberRemoveEvent) -> None:
        guild = self.bot.get_guild(event.guild_id)
        guild_total_member_count_update_coroutine = self._handle_total_user_count_change(guild)

        log_channel = db.get_guild_log_channel(guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Member left'
        embed.description = f'{get_formatted_user_string(event.user)})'
        if event.user.display_avatar is not None:
            embed.set_thumbnail(url=event.user.display_avatar.url)

        await log_channel.send(embed=embed)
        await guild_total_member_count_update_coroutine

    # Member ban logic
    # Turns out, finding out exactly who banned who when banning through the bot is a bit funny, lol
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        log_channel = db.get_guild_log_channel(guild)
        if log_channel is None:
            return

        # We fetch several, in case something delayed this function being called
        audit_log_entries = [entry async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.ban)]
        # Find the entry where this user was banned
        found_entry = None
        for entry in audit_log_entries:
            if entry.target is not None and entry.target.id == user.id:
                found_entry = entry
                break

        embed = discord.Embed()
        embed.title = 'Member banned'
        embed.colour = discord.Color.red()
        embed.add_field(name='Member', value=get_formatted_user_string(user))
        if found_entry is not None and found_entry.user is not None:
            embed.add_field(name='Ban reason', value=found_entry.reason)
            responsible_mod = found_entry.user
            # If the responsible mod is the bot itself, then we dont log here, the log was written by the ban command
            if responsible_mod.id == self.bot.user.id:
                return
            embed.add_field(name='Responsible mod', value=get_formatted_user_string(responsible_mod))
            embed.add_field(name='Reason', value=found_entry.reason)
        if user.display_avatar is not None:
            embed.set_thumbnail(url=user.display_avatar.url)
        await log_channel.send(embed=embed)

    async def _check_and_log_nick_update(self, before: discord.Member, after: discord.Member,
                                          log_channel: discord.TextChannel | discord.VoiceChannel) -> None:
        if before.nick != after.nick:
            embed = discord.Embed()
            embed.title = 'Nickname updated'
            embed.description = f'User: {get_formatted_user_string(after)}'
            embed.add_field(name='Old nickname', value=before.nick)
            embed.add_field(name='New nickname', value=after.nick)
            await log_channel.send(embed=embed)

    async def _check_and_log_roles_update(self, before: discord.Member, after: discord.Member,
                                           log_channel: discord.TextChannel | discord.VoiceChannel) -> None:
        if before.roles != after.roles:
            embed = discord.Embed()
            embed.title = 'Roles updated'
            embed.description = f'User: {get_formatted_user_string(after)}'
            embed.add_field(name='Old roles', value=self._roles_array_to_string(before.roles))
            embed.add_field(name='New roles', value=self._roles_array_to_string(after.roles))
            if after.display_avatar is not None:
                embed.set_thumbnail(url=after.display_avatar.url)
            await log_channel.send(embed=embed)

    async def _check_and_log_timeout_update(self, before: discord.Member, after: discord.Member,
                                             log_channel: discord.TextChannel | discord.VoiceChannel) -> None:
        if before.timed_out_until != after.timed_out_until:
            embed = discord.Embed()
            embed.title = 'Timeout updated'
            embed.description = f'User: {get_formatted_user_string(after)}'
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

    async def _check_and_log_username_update(self, before: discord.User, after: discord.User,
                                              log_channel: discord.TextChannel | discord.VoiceChannel) -> None:
        if before.name != after.name:
            embed = discord.Embed()
            embed.title = 'Username updated'
            embed.description = f'User: {get_formatted_user_string(after)}'
            embed.add_field(name='Old username', value=before.name)
            embed.add_field(name='New username', value=after.name)
            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        for guild in after.mutual_guilds:
            log_channel = db.get_guild_log_channel(guild)

            if log_channel is None:
                return

            await self._check_and_log_username_update(before, after, log_channel)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        log_channel = db.get_guild_log_channel(after.guild)

        if log_channel is None:
            return

        await self._check_and_log_nick_update(before, after, log_channel)
        await self._check_and_log_roles_update(before, after, log_channel)
        await self._check_and_log_timeout_update(before, after, log_channel)

    #
    # Channels
    #

    async def _is_ignored_channel(self, channel: discord.abc.GuildChannel, guild: discord.Guild) -> bool:
        log_channel = db.get_guild_log_channel(guild)
        if log_channel is not None and channel.id == log_channel.id:
            return True
        total_user_count_stat_channel = db.get_guild_total_users_stat_channel(guild)
        if total_user_count_stat_channel is not None and channel.id == total_user_count_stat_channel.id:
            return True
        active_user_stat_channel = db.get_guild_active_user_stat_channel(guild)
        if active_user_stat_channel is not None and channel.id == active_user_stat_channel.id:
            return True
        return False

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
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
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
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
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        log_channel = db.get_guild_log_channel(after.guild)

        if log_channel is None or await self._is_ignored_channel(after, after.guild) is True:
            return

        embed = discord.Embed()
        embed.title = 'Channel updated'
        embed.description = f'Channel: {after.name} ({after.id}, {after.mention})'

        # Check if name changed
        if before.name != after.name:
            embed.add_field(name='Old name', value=before.name)

        # Check if category changed
        if before.category != after.category:
            embed.add_field(name='Category', value=f'{before.category.name if before.category is not None else '(none)'} '
                                                   f'-> {after.category.name if after.category is not None else '(none)'}')

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
    async def on_guild_role_create(self, role: discord.Role) -> None:
        log_channel = db.get_guild_log_channel(role.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Role created'
        embed.description = f'Role: {role.name} ({role.id})'
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        log_channel = db.get_guild_log_channel(role.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Role deleted'
        embed.description = f'Role: {role.name} ({role.id})'
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        log_channel = db.get_guild_log_channel(after.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Role updated'
        embed.description = f'Role: {after.name} ({after.id})'

        # Check if name is different
        if before.name != after.name:
            embed.add_field(name='Old name', value=before.name)

        self._add_permission_changes_to_embed(embed, before, after)

        await log_channel.send(embed=embed)

    #
    # Voice state changes
    #

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        log_channel = db.get_guild_log_channel(member.guild)

        if log_channel is None:
            return

        embed = discord.Embed()
        embed.title = 'Voice state updated'
        embed.description = f'Member: {get_formatted_user_string(member)}'

        # Slightly weird pythonic code to make this a bit shorter and more easily extensible
        fields = ['deaf', 'mute', 'self_deaf', 'self_mute', 'self_stream', 'self_video', 'suppress',
                  'requested_to_speak_at', 'afk', 'channel']

        for field in fields:
            if getattr(before, field) != getattr(after, field):
                embed.add_field(name=field.capitalize().replace('_', ' '),
                                value=f'{getattr(before, field)} -> {getattr(after, field)}')

        await log_channel.send(embed=embed)
