import discord


def get_formatted_user_string(user: discord.User | discord.Member) -> str:
    return f'{user.mention} ({user.name} - {user.id})'
