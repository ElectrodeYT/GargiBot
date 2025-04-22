import sqlite3
import discord
from datetime import datetime, timezone

from pprint import pprint

sqlite_db = sqlite3.connect('gargibot.db')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS config(guild ID PRIMARY KEY, log_channel CHANNEL)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS messages(message_id ID NOT NULL PRIMARY KEY, contents STRING, '
                  'author_id ID NOT NULL, created_at TIMESTAMP NOT NULL)')
sqlite_db.execute('CREATE TABLE IF NOT EXISTS ban_owners(guild ID, banned_user ID, responsible_mod ID, '
                  'banned_time EPOCH)')
sqlite_db.commit()

def guild_exists_in_config(guild):
    cursor = sqlite_db.cursor()
    cursor.execute('SELECT COUNT(*) FROM config WHERE guild = ?', (guild.id,))
    res = cursor.fetchone()
    cursor.close()

    if res is None:
        return False
    return True

def init_guild(guild):
    if guild_exists_in_config(guild):
        return

    cur = sqlite_db.cursor()
    cur.execute('INSERT INTO config(guild, log_channel) VALUES (?, ?)', (guild.id, 0))
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

# TODO: this entire stuff
def get_ban_image_url(guild: discord.Guild) -> str:
    return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'

def get_kick_image_url(guild: discord.Guild) -> str:
    return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'

def get_unban_image_url(guild: discord.Guild) -> str:
    return 'https://raw.githubusercontent.com/ElectrodeYT/GargiBot/refs/heads/master/gargibot.gif'
