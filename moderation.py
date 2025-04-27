from datetime import datetime, UTC, timezone, timedelta
from typing import Literal, List
from dateutil.relativedelta import relativedelta
from pathlib import Path

import discord
import os
import db
from pytimeparse.timeparse import timeparse

from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands

purge_logs_location = Path(os.environ.get('PURGE_LOGS_LOCATION', 'purge_logs/'))
purge_logs_location.mkdir(parents=True, exist_ok=True)

purge_logs_url_prepend = os.environ.get('PURGE_LOGS_URL_PREPEND')


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _create_success_embed(self, user_affected: discord.User | discord.Member, type: str,
                              guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed()
        embed.title = f'Member {type}'
        embed.description = f'**{user_affected.name}** has been {type}.'

        if type == 'banned':
            embed.colour = discord.Colour.red()
            embed.set_thumbnail(url=db.get_ban_image_url(guild))
        elif type == 'unbanned':
            embed.colour = discord.Colour.green()
            embed.set_thumbnail(url=db.get_unban_image_url(guild))
        elif type == 'kick':
            embed.colour = discord.Colour.yellow()
            embed.set_thumbnail(url=db.get_kick_image_url(guild))

        return embed

    def _create_text_embed(self, text: str) -> discord.Embed:
        embed = discord.Embed()
        embed.description = text
        return embed

    def _create_log_embed(self, user_affected: discord.User | discord.Member,
                          responsible_mod: discord.User | discord.Member, reason: str | None,
                          log_type: str) -> discord.Embed:
        embed = discord.Embed()
        embed.title = f'Member {log_type}'

        if log_type == 'banned':
            embed.colour = discord.Colour.red()
        elif log_type == 'unbanned':
            embed.colour = discord.Colour.green()
        elif log_type == 'kick':
            embed.colour = discord.Colour.yellow()

        embed.add_field(name='Member', value=f'{user_affected.mention} ({user_affected.name} - {user_affected.id})')
        embed.add_field(name='Responsible Moderator', value=responsible_mod)
        embed.add_field(name='Reason', value='(none)' if reason is None else reason)
        return embed

    async def _send_embed_to_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        log_channel = db.get_guild_log_channel(guild)
        if log_channel is None:
            return

        await log_channel.send(embed=embed)

    async def _send_dm(self, user_affected: discord.User | discord.Member, guild: discord.Guild, action_type: str,
                       reason: str | None = None) -> bool:
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
    @app_commands.describe(user_to_ban='The user to ban.', reason='The reason for the ban.')
    async def ban(self, ctx: commands.Context, user_to_ban: discord.User | discord.Member, *,
                  reason: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        if user_to_ban.id == self.bot.user.id:
            await ctx.send('You cannot ban me!', ephemeral=True)
            return

        if ctx.author is None:
            await ctx.send('Somehow, the author of the command could not be determined; '
                           'please report this bug to electrode!', ephemeral=True)
            return

        print(f'Banning user {user_to_ban.name} (responsible mod: {ctx.author.name})')
        await self._send_dm(user_to_ban, action_type='banned', guild=ctx.guild, reason=reason)

        db.add_ban(ctx.guild, banned_user=user_to_ban, responsible_mod=ctx.author)
        await ctx.guild.ban(user=user_to_ban, reason=f'By {ctx.author.name} - {reason}', delete_message_days=0)
        await ctx.send(embed=self._create_success_embed(user_affected=user_to_ban, type="banned", guild=ctx.guild))
        await self._send_embed_to_log(ctx.guild, self._create_log_embed(user_affected=user_to_ban,
                                                                        responsible_mod=ctx.author,
                                                                        reason=reason,
                                                                        log_type='banned'))

    @commands.hybrid_command(name='kick', description='Kick a member from this guild.', aliases=['dabon'])
    @commands.has_permissions(kick_members=True)
    @app_commands.describe(user_to_kick='The user to kick.', reason='The reason for the kick.')
    async def kick(self, ctx: commands.Context, user_to_kick: discord.User | discord.Member, *,
                   reason: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        if user_to_kick.id == self.bot.user.id:
            await ctx.send('You cannot kick me!', ephemeral=True)
            return

        if ctx.author is None:
            await ctx.send('Somehow, the author of the command could not be determined; '
                           'please report this bug to electrode!', ephemeral=True)
            return

        print(f'Kicking user {user_to_kick.name} (responsible mod: {ctx.author.name})')
        await self._send_dm(user_to_kick, action_type='kicked', guild=ctx.guild, reason=reason)

        await ctx.guild.kick(user=user_to_kick, reason=reason)
        await ctx.send(embed=self._create_success_embed(user_affected=user_to_kick, type="kicked", guild=ctx.guild))
        await self._send_embed_to_log(ctx.guild, self._create_log_embed(user_affected=user_to_kick,
                                                                        responsible_mod=ctx.author,
                                                                        reason=reason,
                                                                        log_type='kicked'))

    @commands.hybrid_command(name='unban', description='Unban a member from this guild.', aliases=['whip'])
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(user_to_unban='The user to unban.', reason='The reason for the unban.')
    async def unban(self, ctx: commands.Context, user_to_unban: discord.User | discord.Member, *,
                    reason: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        if ctx.author is None:
            await ctx.send('Somehow, the author of the command could not be determined; '
                           'please report this bug to electrode!', ephemeral=True)
            return

        print(f'Unbanning user {user_to_unban.name} (responsible mod: {ctx.author.name})')
        try:
            await ctx.guild.unban(user=user_to_unban, reason=reason)
        except discord.errors.NotFound:
            await ctx.send(embed=self._create_text_embed('This user is not banned!'))
            return
        await ctx.send(embed=self._create_success_embed(user_affected=user_to_unban, type="unbanned", guild=ctx.guild))
        await self._send_embed_to_log(ctx.guild, self._create_log_embed(user_affected=user_to_unban,
                                                                        responsible_mod=ctx.author,
                                                                        reason=reason,
                                                                        log_type='unbanned'))

    @commands.hybrid_command(name='mute', description='Mute a member from this guild.', aliases=['shush', 'timeout'])
    @commands.has_permissions(kick_members=True)
    @app_commands.describe(user_to_mute='The user to mute.',
                           time='The time to mute for; leave empty for as long as possible',
                           reason='The reason for the mute.')
    async def mute(self, ctx: commands.Context, user_to_mute: discord.Member, time: str | None = None, *,
                   reason: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        if user_to_mute.id == self.bot.user.id:
            await ctx.send('You cannot mute me!', ephemeral=True)

        if ctx.author is None:
            await ctx.send('Somehow, the author of the command could not be determined; '
                           'please report this bug to electrode!', ephemeral=True)
            return

        mute_time_delta: timedelta | None = None
        indefinite_mute: bool = False

        if time is not None:
            mute_time_seconds = timeparse(time)
            if mute_time_seconds is None:
                # If the time parse failed, then prepend this to the reason
                if reason is None:
                    reason = time
                else:
                    reason = time + ' ' + reason
            else:
                # We can only mute in int amount of seconds
                mute_time_seconds = int(mute_time_seconds)

                if mute_time_seconds <= 0:
                    await ctx.send('The amount of time to mute for must be positive!', ephemeral=True)
                    return

                mute_time_delta = timedelta(seconds=mute_time_seconds)

        # If we have no passed time, or time passing failed, mute as long as we can
        if mute_time_delta is None:
            mute_time_delta = timedelta(days=28)
            indefinite_mute = True

        await user_to_mute.timeout(mute_time_delta, reason=f'By {ctx.author.name} - {reason}')

        # Send the embed that is sent into the channel
        embed = discord.Embed(description=f'Muted {user_to_mute.mention} '
                                          f'{('for' + str(mute_time_delta)) if not indefinite_mute else 'indefinitely'}'
                                          f' - `{reason}`', color=discord.Color.orange())
        await ctx.send(embed=embed)

        # Send a log for this
        embed = self._create_log_embed(user_affected=user_to_mute,
                                       responsible_mod=ctx.author,
                                       reason=reason,
                                       log_type='muted')
        embed.add_field(name='Duration', value=str(mute_time_delta)
                                               + (' (as long as possible)' if indefinite_mute else ''),
                        inline=False)
        await self._send_embed_to_log(ctx.guild, embed)

    @commands.hybrid_command(name='unmute', description='Unmute a member from this guild.', aliases=['unshush'])
    @commands.has_permissions(kick_members=True)
    @app_commands.describe(user_to_unmute='The user to unmute.')
    async def unmute(self, ctx: commands.Context, user_to_unmute: discord.Member) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        if user_to_unmute.id == self.bot.user.id:
            await ctx.send('You cannot unmute me!', ephemeral=True)

        if ctx.author is None:
            await ctx.send('Somehow, the author of the command could not be determined; '
                           'please report this bug to electrode!', ephemeral=True)
            return

        if user_to_unmute.timed_out_until is None or user_to_unmute.timed_out_until <= datetime.now(UTC):
            await ctx.send('This user is not muted!', ephemeral=True)
            return

        await user_to_unmute.timeout(None, reason=f'By - {ctx.author.name}')

        embed = discord.Embed(description=f'Unmuted {user_to_unmute.mention}.', color=discord.Color.green())
        await ctx.send(embed=embed)

        embed = self._create_log_embed(user_affected=user_to_unmute,
                                       responsible_mod=ctx.author,
                                       reason=None,
                                       log_type='unmuted')
        await self._send_embed_to_log(ctx.guild, embed)

    class BanStatsView(View):
        current_begin_of_month: datetime

        def __init__(self, bot, ctx, current_date):
            super().__init__(timeout=None)
            self.bot = bot
            self.ctx = ctx
            self.current_begin_of_month = current_date.replace(day=1)

            # Add previous month button
            prev_button = Button(label="← Previous Month", style=discord.ButtonStyle.secondary, custom_id="prev_month")
            prev_button.callback = self.prev_month_callback
            self.add_item(prev_button)

            # Add next month button
            next_button = Button(label="Next Month →", style=discord.ButtonStyle.secondary, custom_id="next_month")
            next_button.callback = self.next_month_callback
            self.add_item(next_button)

        async def get_embed(self) -> discord.Embed:
            # Get the beginning of this month
            assert self.current_begin_of_month.day == 1

            # Get the end of this month, or the current day if the month is not over
            end_of_month = self.current_begin_of_month + relativedelta(months=1)

            if end_of_month > datetime.now(UTC):
                end_of_month = datetime.now(UTC)

            # Get the initial banstats
            ban_stats = await self._get_banstats_between_dates(
                guild=self.ctx.guild,
                before=end_of_month,
                after=self.current_begin_of_month
            )

            # Create the embed
            ban_stats_embed = self._banstats_to_embed(ban_stats)
            self._add_before_after_to_banstats_embed(ban_stats_embed, end_of_month, self.current_begin_of_month)

            return ban_stats_embed

        async def prev_month_callback(self, interaction: discord.Interaction) -> None:
            self.current_begin_of_month = self.current_begin_of_month - relativedelta(months=1)
            await self.update_stats(interaction)

        async def next_month_callback(self, interaction: discord.Interaction) -> None:
            new_date = self.current_begin_of_month + relativedelta(months=1)
            if new_date <= datetime.now(UTC):
                self.current_begin_of_month = new_date
                await self.update_stats(interaction)
            else:
                await interaction.response.send_message("Cannot view future months!", ephemeral=True)

        async def update_stats(self, interaction: discord.Interaction) -> None:
            # Get the beginning of this month
            assert self.current_begin_of_month.day == 1

            # Get the end of this month, or the current day if the month is not over
            end_of_month = self.current_begin_of_month + relativedelta(months=1)

            if end_of_month > datetime.now(UTC):
                end_of_month = datetime.now(UTC)

            assert interaction.guild is not None
            ban_stats = await self._get_banstats_between_dates(
                guild=interaction.guild,
                before=end_of_month,
                after=self.current_begin_of_month
            )

            ban_stats_embed = self._banstats_to_embed(ban_stats)
            self._add_before_after_to_banstats_embed(ban_stats_embed, end_of_month, self.current_begin_of_month)

            await interaction.response.edit_message(embed=ban_stats_embed, view=self)

        def _banstats_to_embed(self, banstats: dict) -> discord.Embed:
            embed = discord.Embed()
            embed.title = 'Ban stats'
            embed.colour = discord.Colour.green()

            if len(banstats.keys()) == 0:
                embed.description = 'No (known) bans in the time period'
            else:
                descriptions = []
                for mod in banstats.keys():
                    if mod == 'untrackable':
                        embed.add_field(name='Untrackable bans', value=banstats[mod], inline=False)
                        continue

                    assert type(banstats[mod]) is int
                    user = self.bot.get_user(mod)
                    user_name = user.name if user else f"Unknown User ({mod})"
                    descriptions.append(f'{user_name} - {banstats[mod]} ban{"s" if banstats[mod] > 1 else ""}')

                embed.description = '\n'.join(descriptions)

            return embed

        def _add_before_after_to_banstats_embed(self, embed: discord.Embed, before: datetime, after: datetime) -> None:
            date_format_string = '%d. %b %Y'
            embed.set_footer(
                text=f'Banstats between {after.strftime(date_format_string)} and {before.strftime(date_format_string)}')

        def _get_audit_log_ban_in_db(self, audit_log_entry: discord.AuditLogEntry,
                                     database_saved_bans: List[db.SavedBan]) -> db.SavedBan | None:
            assert audit_log_entry.target is not None
            assert audit_log_entry.user is not None
            assert audit_log_entry.created_at is not None

            debug_this = False
            if debug_this:
                print(
                    f'Trying to find ban in DB for {audit_log_entry.target.id} at {audit_log_entry.created_at} ({int(audit_log_entry.created_at.timestamp())}).')

            # Try to find a database ban here
            current_top_db_entry: db.SavedBan | None = None
            for db_ban_entry in database_saved_bans:
                if debug_this:
                    print(f'-> Entry: {db_ban_entry.banned_user_id} - {int(db_ban_entry.banned_time.timestamp())}, '
                          f'responsible mod: {db_ban_entry.responsible_mod_id}')
                if db_ban_entry.banned_user_id == audit_log_entry.target.id and abs(
                        (audit_log_entry.created_at - db_ban_entry.banned_time).total_seconds()) <= 20:
                    if current_top_db_entry is not None:
                        # If we have a potential DB entry already saved, replace it with this one if the time difference is closer
                        if abs((audit_log_entry.created_at - current_top_db_entry.banned_time).total_seconds()) > abs(
                                (db_ban_entry.banned_time - current_top_db_entry.banned_time).total_seconds()):
                            if debug_this:
                                print('--> Choosing this one as a replacement')
                            current_top_db_entry = db_ban_entry
                    else:
                        if debug_this:
                            print('--> Choosing this one as a first')
                        current_top_db_entry = db_ban_entry

            # If we have no DB entry for this ban, log this, else, remove the entry from the DB list.
            if current_top_db_entry is None:
                print(
                    f'DB-entry-less ban! Banned user is {audit_log_entry.target.id}, banned by {audit_log_entry.user.id} at {audit_log_entry.created_at} ({int(audit_log_entry.created_at.timestamp())}).')
            else:
                database_saved_bans.remove(current_top_db_entry)

            return current_top_db_entry

        async def _get_banstats_between_dates(self, guild: discord.Guild, before: datetime, after: datetime) -> dict[
            int | str, int]:
            # Get the list of bans from audit log between the times
            audit_log_ban_entries = [entry async for entry in
                                     guild.audit_logs(action=discord.AuditLogAction.ban, before=before, after=after)]

            # Get the list of saved database bans between the times
            database_saved_bans = db.get_bans_between(guild, before, after)

            # The actual banstats themselves
            ban_stats: dict[int | str, int] = {}

            # We now iterate the audit log bans
            for audit_log_entry in audit_log_ban_entries:
                assert audit_log_entry.target is not None
                assert audit_log_entry.user is not None
                assert audit_log_entry.created_at is not None

                # Look up the ban in the DB
                db_ban_entry = self._get_audit_log_ban_in_db(audit_log_entry, database_saved_bans)

                # If the ban is not in the DB, and it was made by us, then it is untrackable
                if db_ban_entry is None and audit_log_entry.user.id == self.bot.user.id:
                    if 'untrackable' not in ban_stats:
                        ban_stats['untrackable'] = 1
                    else:
                        ban_stats['untrackable'] += 1
                    continue
                # If the ban was made by us, and we found a DB entry for it, increment the banstats for the moderator
                elif db_ban_entry is not None and audit_log_entry.user.id == self.bot.user.id:
                    if db_ban_entry.responsible_mod_id not in ban_stats:
                        ban_stats[db_ban_entry.responsible_mod_id] = 1
                    else:
                        ban_stats[db_ban_entry.responsible_mod_id] += 1
                # If the ban is not in the DB, but it was not made by us, then it was made manually;
                # add it to the DB, and add it to the banstats
                else:
                    if db_ban_entry is None:
                        db.add_audit_log_ban(guild, audit_log_entry)

                    # Increment the banstats for the moderator
                    if audit_log_entry.user.id not in ban_stats:
                        ban_stats[audit_log_entry.user.id] = 1
                    else:
                        ban_stats[audit_log_entry.user.id] += 1

            # Log how many bans are in the DB and not in the audit log
            print(f'Bans in DB and not audit log: {len(database_saved_bans)}')

            # Iterate through what is left of the DB entries
            for db_ban_entry in database_saved_bans:
                if db_ban_entry.responsible_mod_id not in ban_stats:
                    ban_stats[db_ban_entry.responsible_mod_id] = 1
                else:
                    ban_stats[db_ban_entry.responsible_mod_id] += 1

            return ban_stats

    @commands.hybrid_command(name='banstats', description='Get the amount of bans in the last month.')
    async def banstats(self, ctx: commands.Context[commands.Bot]) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        current_time = datetime.now(UTC)
        view = self.BanStatsView(self.bot, ctx, current_time)
        await ctx.send(embed=await view.get_embed(), view=view)

    @commands.hybrid_command(name='purge', description='Purge messages from this channel.')
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(amount='The amount of messages to purge.')
    async def purge(self, ctx: commands.Context, amount: int = 10) -> None:
        if amount <= 0:
            await ctx.send('The amount of messages to purge must be positive.', ephemeral=True)
            return

        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        list_of_deleted = await ctx.channel.purge(limit=amount + 1, bulk=True)

        # Save the purge log.
        file = purge_logs_location / f'{ctx.guild.name.lower().replace(' ', '-')}-' \
                                     f'{ctx.channel.name.lower().replace(' ', '-')}-' \
                                     f'{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt'

        with open(file, 'a') as f:
            f.write(f'Purged {len(list_of_deleted)} messages in {ctx.channel.name} ({ctx.guild.name})\n')
            for message in list_of_deleted:
                f.write(f'\t{message.author.name} - {message.created_at} - id: ({message.id})\n')
                f.write(f'\t\t{message.content.replace('\n', '\n\t\t')}\n')
            f.flush()

        embed = discord.Embed(title='Purged messages', description=f'Deleted {len(list_of_deleted)} messages.')
        await ctx.send(embed=embed)

        # Log the purge
        log_channel = db.get_guild_log_channel(ctx.guild)
        if log_channel is not None:
            embed = discord.Embed(title='Purged messages', description=f'Deleted {len(list_of_deleted)} messages in'
                                                                       f'{ctx.channel.mention}.')
            if purge_logs_url_prepend is not None:
                embed.add_field(name='Log file', value=f'[Link]({purge_logs_url_prepend}{file.name})')
            await log_channel.send(embed=embed)

    @commands.hybrid_command(name='info', description='Get information about a user.')
    @app_commands.describe(user='The user to get information about.')
    async def info(self, ctx: commands.Context, user: discord.Member) -> None:
        if ctx.guild is None:
            await ctx.send('This command can only be used in a guild.', ephemeral=True)
            return

        if user.id == self.bot.user.id:
            await ctx.send('I am a bot!', ephemeral=True)

        embed = discord.Embed(title=f'Info for {user.name}',
                              description=f'{'AKA: {user.nick}, ' if user.nick is not None else ''}ID: {user.id}')
        embed.set_thumbnail(url=user.display_avatar.url)

        if type(user.status) is not str:
            embed.add_field(name='Overall Status', value=user.status, inline=False)
            embed.add_field(name='Desktop Status', value=user.desktop_status)
            embed.add_field(name='Mobile Status', value=user.mobile_status)
            embed.add_field(name='Web Status', value=user.web_status)

        embed.add_field(name='Created at', value=f'<t:{int(user.created_at.timestamp())}:f>', inline=False)
        embed.add_field(name='Joined at', value=f'<t:{int(user.joined_at.timestamp())}:f>', inline=False)

        embed.add_field(name='Seen on', value='\n'.join([guild.name for guild in user.mutual_guilds]), inline=False)

        await ctx.send(embed=embed)