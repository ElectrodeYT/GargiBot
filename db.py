import sqlite3
import discord
import datetime

from pprint import pprint

config_db = sqlite3.connect('config.db')
config_db.execute('CREATE TABLE IF NOT EXISTS config(guild ID PRIMARY KEY, log_channel CHANNEL)')

def guild_exists_in_config(guild):
    cursor = config_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return False
    return True

def init_guild(guild):
    if guild_exists_in_config(guild):
        return

    cur = config_db.cursor()
    cur.execute('INSERT INTO config(guild, log_channel) VALUES (?, ?)', (guild.id, 0))
    cur.close()
    config_db.commit()

def get_guild_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    cursor = config_db.cursor()
    cursor.execute('SELECT log_channel FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None or res == 0:
        return None

    return guild.get_channel(res[0])


log_db = sqlite3.connect('log.db')
log_db.execute('CREATE TABLE IF NOT EXISTS messages(message_id ID NOT NULL PRIMARY KEY, contents STRING, '
               'author_id ID NOT NULL, created_at TIMESTAMP NOT NULL)')
log_db.commit()

class LoggedMessage:
    contents: str
    author_id: int
    created_at: datetime.datetime

def get_message_from_db(message_id: int) -> LoggedMessage | None:
    cursor = log_db.cursor()
    cursor.execute('SELECT contents, author_id, created_at FROM messages WHERE message_id = ?', (message_id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return None

    message = LoggedMessage()
    message.contents = res[0]
    message.author_id = res[1]
    message.created_at = datetime.datetime.fromtimestamp(res[2])
    return message


def insert_message_into_db(message: discord.Message):
    cursor = log_db.cursor()
    cursor.execute('INSERT OR REPLACE INTO messages(message_id, contents, author_id, created_at) VALUES (?, ?, ?, ?)',
                   (message.id, message.content, message.author.id, message.created_at.timestamp()))
    cursor.close()
    log_db.commit()

def delete_message_from_db(message_id: int):
    cursor = log_db.cursor()
    cursor.execute('DELETE FROM messages WHERE message_id = ?', (message_id,))
    cursor.close()
    log_db.commit()

moderation_db = sqlite3.connect('moderation.db')
moderation_db.execute('CREATE TABLE IF NOT EXISTS ban_owners(guild ID, banned_user ID, responsible_mod ID, '
                      'banned_time EPOCH)')
moderation_db.commit()

def add_ban(guild: discord.Guild, responsible_mod: discord.User, banned_user: discord.User):
    cursor = moderation_db.cursor()
    cursor.execute('INSERT INTO ban_owners(guild, banned_user, responsible_mod, banned_time) VALUES (?, ?, ?, unixepoch(\'now\'))',
                   (guild.id, banned_user.id, responsible_mod.id))
    cursor.close()
    moderation_db.commit()


def get_ban_owner(guild: discord.Guild, banned_user: discord.User, approx_time: datetime) -> discord.User | None:
    cursor = moderation_db.cursor()
    cursor.execute('SELECT responsible_mod, banned_time FROM ban_owners WHERE guild=? and banned_user=?',
                   (guild.id, banned_user.id))
    results = cursor.fetchall()

    # We now find the one with the closest approx ban time
    pprint(results)

    return None
