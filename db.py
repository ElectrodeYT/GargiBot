import sqlite3
import discord
from datetime import datetime, timezone

from pprint import pprint

sqlite_db = sqlite3.connect('gargibot.db')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS config(guild ID PRIMARY KEY, log_channel CHANNEL DEFAULT NULL, ban_image_url STRING DEFAULT NULL,'
                  ' kick_image_url STRING DEFAULT NULL, unban_image_url STRING DEFAULT NULL, active_user_stat_channel CHANNEL DEFAULT NULL, '
                  'total_users_stat_channel CHANNEL DEFAULT NULL)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS messages(message_id ID NOT NULL PRIMARY KEY, contents STRING, '
                  'author_id ID NOT NULL, created_at TIMESTAMP NOT NULL)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS ban_owners(guild ID, banned_user ID, responsible_mod ID, '
                  'banned_time EPOCH)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS tags(guild ID, tag_name STRING PRIMARY KEY, tag_content STRING)')
sqlite_db.commit()

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

def get_guild_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT log_channel FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None or res == 0:
        return None

    return guild.get_channel(res[0])

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


def insert_message_into_db(message: discord.Message):
    cursor = sqlite_db.cursor()
    cursor.execute('INSERT OR REPLACE INTO messages(message_id, contents, author_id, created_at) VALUES (?, ?, ?, ?)',
                   (message.id, message.content, message.author.id, message.created_at.timestamp()))
    cursor.close()
    sqlite_db.commit()

def delete_message_from_db(message_id: int):
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

def add_ban(guild: discord.Guild, responsible_mod: discord.User, banned_user: discord.User):
    cursor = sqlite_db.cursor()
    cursor.execute('INSERT INTO ban_owners(guild, banned_user, responsible_mod, banned_time) VALUES (?, ?, ?, unixepoch(\'now\'))',
                   (guild.id, banned_user.id, responsible_mod.id))
    cursor.close()
    sqlite_db.commit()

def add_audit_log_ban(guild: discord.Guild, audit_log_entry: discord.AuditLogEntry):
    print(f'Adding audit log ban for {audit_log_entry.target.name} ({audit_log_entry.target.id}),'
          f' by {audit_log_entry.user.name} ({audit_log_entry.user.id})'
          f' guild {guild.name} ({guild.id}), '
          f' ban time {audit_log_entry.created_at} ({int(audit_log_entry.created_at.timestamp())}) to database.')

    cursor = sqlite_db.cursor()
    cursor.execute('INSERT INTO ban_owners(guild, banned_user, responsible_mod, banned_time) VALUES (?, ?, ?, ?)',
                   (guild.id, audit_log_entry.target.id, audit_log_entry.user.id, int(audit_log_entry.created_at.timestamp())))
    cursor.close()
    sqlite_db.commit()

def get_ban_owner(guild: discord.Guild, banned_user: discord.User, approx_time: datetime) -> discord.User | None:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT responsible_mod, banned_time FROM ban_owners WHERE guild=? and banned_user=?',
                   (guild.id, banned_user.id))
    results = cursor.fetchall()

    # We now find the one with the closest approx ban time
    pprint(results)

    return None

def get_bans_between(guild: discord.Guild, before: datetime, after: datetime) -> [SavedBan]:
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
    if res is None or res[0] == '':
        return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
    return res[0]

def get_kick_image_url(guild: discord.Guild) -> str:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT kick_image_url FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()
    if res is None or res[0] == '':
        return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
    return res[0]

def get_unban_image_url(guild: discord.Guild) -> str:
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT unban_image_url FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()
    if res is None or res[0] == '':
        return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
    return res[0]

def set_image_url(guild: discord.Guild, image_url: str, type: str):
    if type not in ['ban', 'kick', 'unban']:
        raise ValueError('Invalid image type')

    cursor = sqlite_db.cursor()
    if image_url is not None:
        cursor.execute(f'UPDATE config SET {type}_image_url = ? WHERE guild = ?', (image_url, guild.id))
    else:
        cursor.execute(f'UPDATE config SET {type}_image_url = NULL WHERE guild = ?', (guild.id,))
    cursor.close()
    sqlite_db.commit()

def set_guild_tag(guild: discord.Guild, tag_name, tag_content: str):
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

def remove_guild_tag(guild: discord.Guild, tag_name: str):
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
