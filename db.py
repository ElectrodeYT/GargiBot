import sqlite3
import os
from typing import List

import discord
from datetime import datetime, timezone

from pprint import pprint

def column_exists(table_name: str, column_name: str) -> bool:
    cursor = sqlite_db.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    cursor.close()
    return any(column[1] == column_name for column in columns)


def add_column(table_name: str, column_name: str, column_type: str, default_value: str | None = None) -> None:
    cursor = sqlite_db.cursor()
    if default_value is not None:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} {default_value}")
    else:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    cursor.close()
    sqlite_db.commit()

# We do this to make it easier to add new columns to the config table later on.
CONFIG_COLUMNS = {
    'guild': ('ID', 'PRIMARY KEY'),
    'log_channel': ('CHANNEL', 'DEFAULT NULL'),
    'ban_image_url': ('STRING', 'DEFAULT NULL'),
    'kick_image_url': ('STRING', 'DEFAULT NULL'),
    'unban_image_url': ('STRING', 'DEFAULT NULL'),
    'active_user_stat_channel': ('CHANNEL', 'DEFAULT NULL'),
    'total_users_stat_channel': ('CHANNEL', 'DEFAULT NULL'),
    'ban_footer': ('STRING', 'DEFAULT NULL'),
    'kick_footer': ('STRING', 'DEFAULT NULL')
}


def ensure_config_columns():
    for column_name, (column_type, default) in CONFIG_COLUMNS.items():
        if not column_exists('config', column_name):
            add_column('config', column_name, column_type, default)


sqlite_db = sqlite3.connect(os.environ.get('DB_FILENAME', 'gargibot.db'))
sqlite_db.execute('CREATE TABLE IF NOT EXISTS config(guild ID PRIMARY KEY)')
ensure_config_columns()
sqlite_db.execute('CREATE TABLE IF NOT EXISTS messages(message_id ID NOT NULL PRIMARY KEY, contents STRING, '
                  'author_id ID NOT NULL, created_at TIMESTAMP NOT NULL)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS ban_owners(guild ID, banned_user ID, responsible_mod ID, '
                  'banned_time EPOCH)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS tags(guild ID, tag_name STRING PRIMARY KEY, tag_content STRING)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS user_activity(guild ID, user_id ID, days_since_epoch ID, first_active_time EPOCH, last_active_time EPOCH, '
                  'PRIMARY KEY(guild, user_id, days_since_epoch))')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS total_user_count(guild ID, days_since_epoch ID, total_users INT, '
                  'PRIMARY KEY(guild, days_since_epoch))')
sqlite_db.commit()

last_sqlite_db_commit_for_user_activity = None
last_sqlite_db_commit_for_total_user_count = None

def guild_exists_in_config(guild):
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None or res[0] == 0:
        return False
    return True

def init_guild(guild):
    if guild_exists_in_config(guild):
        return

    cur = sqlite_db.cursor()
    cur.execute('INSERT INTO config(guild) VALUES (?)', (guild.id,))
    cur.close()
    sqlite_db.commit()

def get_guild_log_channel(guild: discord.Guild) -> discord.TextChannel | discord.VoiceChannel | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT log_channel FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None or res == 0:
        return None

    channel = guild.get_channel(res[0])
    assert channel is None or isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel)
    return channel

def get_guild_active_user_stat_channel(guild: discord.Guild) -> discord.TextChannel | discord.VoiceChannel | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT active_user_stat_channel FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None or res == 0:
        return None

    channel = guild.get_channel(res[0])
    assert channel is None or isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel)
    return channel

def get_guild_total_users_stat_channel(guild: discord.Guild) -> discord.TextChannel | discord.VoiceChannel | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT total_users_stat_channel FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None or res == 0:
        return None

    channel = guild.get_channel(res[0])
    assert channel is None or isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel)
    return channel

def update_user_activity(guild: discord.Guild, user: discord.User | discord.Member) -> None:
    global last_sqlite_db_commit_for_user_activity
    if last_sqlite_db_commit_for_user_activity is None:
        last_sqlite_db_commit_for_user_activity = datetime.now(timezone.utc)

    # Store the current time we use for this for the 1 in a million chance that the day rolls over during the function
    current_time = datetime.now(timezone.utc)
    days_since_epoch = (current_time - datetime(1970, 1, 1, tzinfo=timezone.utc)).days

    cursor = sqlite_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_activity WHERE guild = ? AND user_id = ? AND days_since_epoch = ?',
                   (guild.id, user.id, days_since_epoch))
    exists = cursor.fetchone()[0] > 0

    if exists:
        cursor.execute(
            'UPDATE user_activity SET last_active_time = ? WHERE guild = ? AND user_id = ? AND days_since_epoch = ?',
            (int(current_time.timestamp()), guild.id, user.id, days_since_epoch))
    else:
        cursor.execute(
            'INSERT INTO user_activity(guild, user_id, days_since_epoch, first_active_time, last_active_time) VALUES (?, ?, ?, ?, ?)',
            (guild.id, user.id, days_since_epoch, int(current_time.timestamp()), int(current_time.timestamp())))

    cursor.close()

    # We don't issue sqlite db commits for this too often, since this function will fire _very_ often
    assert last_sqlite_db_commit_for_user_activity is not None
    if (current_time - last_sqlite_db_commit_for_user_activity).total_seconds() > 10:
        last_sqlite_db_commit_for_user_activity = current_time
        sqlite_db.commit()

def get_this_day_active_user_count(guild: discord.Guild) -> int:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_activity WHERE guild = ? AND days_since_epoch = ?',
                   (guild.id, (datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).days))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return 0
    return res[0]

def get_last_day_active_user_count(guild: discord.Guild) -> int:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_activity WHERE guild = ? AND days_since_epoch = ?',
                   (guild.id, (datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).days - 1))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return 0
    return res[0]

def update_total_user_count(guild: discord.Guild) -> None:
    global last_sqlite_db_commit_for_total_user_count
    if last_sqlite_db_commit_for_total_user_count is None:
        last_sqlite_db_commit_for_total_user_count = datetime.now(timezone.utc)

    cursor = sqlite_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM total_user_count WHERE guild = ? AND days_since_epoch = ?',
                   (guild.id, (datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).days))
    exists = cursor.fetchone()[0] > 0

    if exists:
        cursor.execute(
            'UPDATE total_user_count SET total_users = ? WHERE guild = ? AND days_since_epoch = ?',
            (guild.member_count, guild.id,
             (datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).days)
        )
    else:
        cursor.execute(
            'INSERT INTO total_user_count(guild, days_since_epoch, total_users) VALUES (?, ?, ?)',
            (guild.id, (datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).days,
             guild.member_count)
        )

    cursor.close()
    # We don't issue sqlite db commits for this too often, since this function will fire _very_ often
    assert last_sqlite_db_commit_for_total_user_count is not None
    if (datetime.now(timezone.utc) - last_sqlite_db_commit_for_total_user_count).total_seconds() > 10:
        last_sqlite_db_commit_for_total_user_count = datetime.now(timezone.utc)
        sqlite_db.commit()

def get_last_day_total_user_count(guild: discord.Guild) -> int | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT total_users FROM total_user_count WHERE guild = ? AND days_since_epoch = ?',
                   (guild.id, (datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).days - 1))
    res = cursor.fetchone()
    cursor.close()
    if res is None:
        return None
    return res[0]

class LoggedMessage:
    contents: str
    author_id: int
    created_at: datetime

def get_message_from_db(message_id: int) -> LoggedMessage | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT contents, author_id, created_at FROM messages WHERE message_id = ?', (message_id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return None

    message = LoggedMessage()
    message.contents = res[0]
    message.author_id = res[1]
    message.created_at = datetime.fromtimestamp(res[2])
    return message


def insert_message_into_db(message: discord.Message) -> None:
    cursor = sqlite_db.cursor()
    cursor.execute('INSERT OR REPLACE INTO messages(message_id, contents, author_id, created_at) VALUES (?, ?, ?, ?)',
                   (message.id, message.content, message.author.id, message.created_at.timestamp()))
    cursor.close()
    sqlite_db.commit()

def delete_message_from_db(message_id: int) -> None:
    cursor = sqlite_db.cursor()
    cursor.execute('DELETE FROM messages WHERE message_id = ?', (message_id,))
    cursor.close()
    sqlite_db.commit()

class SavedBan:
    responsible_mod_id: int
    banned_user_id: int
    banned_time: datetime

    def __repr__(self):
        return (f'SavedBan(responsible_mod_id={self.responsible_mod_id}, '
                f'banned_user_id={self.banned_user_id}, '
                f'banned_time={int(self.banned_time.timestamp())})')

def add_ban(guild: discord.Guild, responsible_mod: discord.User | discord.Member,
            banned_user: discord.User | discord.Member) -> None:
    cursor = sqlite_db.cursor()
    cursor.execute('INSERT INTO ban_owners(guild, banned_user, responsible_mod, banned_time) VALUES (?, ?, ?, unixepoch(\'now\'))',
                   (guild.id, banned_user.id, responsible_mod.id))
    cursor.close()
    sqlite_db.commit()

def add_audit_log_ban(guild: discord.Guild, audit_log_entry: discord.AuditLogEntry) -> None:
    assert isinstance(audit_log_entry, discord.AuditLogEntry)
    assert type(audit_log_entry.target) == discord.User or type(audit_log_entry.target) == discord.Member
    assert type(audit_log_entry.user) == discord.User or type(audit_log_entry.user) == discord.Member
    print(f'Adding audit log ban for {audit_log_entry.target.name} ({audit_log_entry.target.id}),'
          f' by {audit_log_entry.user.name} ({audit_log_entry.user.id})'
          f' guild {guild.name} ({guild.id}), '
          f' ban time {audit_log_entry.created_at} ({int(audit_log_entry.created_at.timestamp())}) to database.')

    cursor = sqlite_db.cursor()
    cursor.execute('INSERT INTO ban_owners(guild, banned_user, responsible_mod, banned_time) VALUES (?, ?, ?, ?)',
                   (guild.id, audit_log_entry.target.id, audit_log_entry.user.id, int(audit_log_entry.created_at.timestamp())))
    cursor.close()
    sqlite_db.commit()

def get_bans_between(guild: discord.Guild, before: datetime, after: datetime) -> List[SavedBan]:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT banned_user, responsible_mod, banned_time FROM ban_owners WHERE guild=? AND banned_time BETWEEN ? and ?',
                   (guild.id, int(after.timestamp()), int(before.timestamp())))
    db_results = cursor.fetchall()

    # Reformat the results from the database
    results = []
    for db_result in db_results:
        ban_log_entry = SavedBan()
        ban_log_entry.banned_user_id = db_result[0]
        ban_log_entry.responsible_mod_id = db_result[1]
        ban_log_entry.banned_time = datetime.fromtimestamp(db_result[2], tz=timezone.utc)
        results.append(ban_log_entry)

    return results

def get_ban_image_url(guild: discord.Guild) -> str:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT ban_image_url FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()
    if res is None or res[0] == '' or res[0] is None:
        return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
    return res[0]

def get_kick_image_url(guild: discord.Guild) -> str:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT kick_image_url FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()
    if res is None or res[0] == '' or res[0] is None:
        return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
    return res[0]

def get_unban_image_url(guild: discord.Guild) -> str:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT unban_image_url FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()
    if res is None or res[0] == '' or res[0] is None:
        return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
    return res[0]

def set_image_url(guild: discord.Guild, image_url: str | None, type: str) -> None:
    if type not in ['ban', 'kick', 'unban']:
        raise ValueError('Invalid image type')

    cursor = sqlite_db.cursor()
    if image_url is not None:
        cursor.execute(f'UPDATE config SET {type}_image_url = ? WHERE guild = ?', (image_url, guild.id))
    else:
        cursor.execute(f'UPDATE config SET {type}_image_url = NULL WHERE guild = ?', (guild.id,))
    cursor.close()
    sqlite_db.commit()

def set_guild_tag(guild: discord.Guild, tag_name: str, tag_content: str) -> None:
    cursor = sqlite_db.cursor()
    cursor.execute('INSERT OR REPLACE INTO tags(guild, tag_name, tag_content) VALUES (?, ?, ?)',
                   (guild.id, tag_name, tag_content))
    cursor.close()
    sqlite_db.commit()

def get_guild_tag(guild: discord.Guild, tag_name: str) -> str | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT tag_content FROM tags WHERE guild=? AND tag_name=?', (guild.id, tag_name))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return None
    return res[0]

def remove_guild_tag(guild: discord.Guild, tag_name: str) -> None:
    cursor = sqlite_db.cursor()
    cursor.execute('DELETE FROM tags WHERE guild=? AND tag_name=?', (guild.id, tag_name))
    cursor.close()
    sqlite_db.commit()

def get_all_guild_tags(guild: discord.Guild) -> dict[str, str]:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT tag_name, tag_content FROM tags WHERE guild=?', (guild.id,))
    res = cursor.fetchall()
    cursor.close()

    tags = {}
    for tag_name, tag_content in res:
        tags[tag_name] = tag_content
    return tags


def get_footer(guild: discord.Guild, type: str) -> str | None:
    """Get the customized footer text for ban/kick embeds in the specified guild.

    Args:
        guild: The Discord guild to get the footer for
        type: The type of footer to get - either 'ban' or 'kick'

    Returns:
        str | None: The footer text if set, None if no footer is configured

    Raises:
        ValueError: If type is not 'ban' or 'kick'
    """
    if type not in ['ban', 'kick']:
        raise ValueError("Footer type must be either 'ban' or 'kick'")

    cursor = sqlite_db.cursor()
    cursor.execute(f'SELECT {type}_footer FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return None
    return res[0]


def set_footer(guild: discord.Guild, footer_text: str | None, type: str) -> None:
    """Set the footer text for the specified type (ban or kick) for the given guild.

    Args:
        guild: The Discord guild to set the footer for
        footer_text: The text to set as the footer. If None, removes the footer
        type: Either 'ban' or 'kick'

    Raises:
        ValueError: If type is not 'ban' or 'kick'
    """
    if type not in ['ban', 'kick']:
        raise ValueError("Footer type must be either 'ban' or 'kick'")

    cursor = sqlite_db.cursor()
    if footer_text is not None:
        cursor.execute(f'UPDATE config SET {type}_footer = ? WHERE guild = ?',
                       (footer_text, guild.id))
    else:
        cursor.execute(f'UPDATE config SET {type}_footer = NULL WHERE guild = ?',
                       (guild.id,))
    cursor.close()
    sqlite_db.commit()
