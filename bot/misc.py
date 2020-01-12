import aiohttp
import discord
import random
import math
import gzip
import json
import time
import secrets

from common import idPattern, send_message, resolve_mention, send_user_not_found, \
    EMOJI, TYPE_COLORS, DBL_BREAK, INFO_BLUE
from discord.ext import commands


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def remove_raw_reaction(self, payload, user=None):
        if not user:
            user = self.bot.get_user(payload.user_id)
            if not user:
                return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, user)

    @commands.has_permissions(administrator=True)
    @commands.command()
    async def raffle(self, ctx, n:int, msg_id:int, channel_id:int = 663479080192049172):
        channel = self.bot.get_channel(channel_id)
        msg = await channel.fetch_message(msg_id)
        reaction = sorted(msg.reactions)[0]
        users = await reaction.users().flatten()
        winners = []
        while users and len(winners) < n:
            winner = random.choice(users)
            users.remove(winner)
            winners.append(winner)

        names = ', '.join([str(winner) for winner in winners])
        mentions = ' '.join([str(winner.mention) for winner in winners])

        await ctx.author.send(f'{reaction.emoji} {n} winner(s) for {reaction.count} submissions:\n{names}\n\n```{mentions}```')


def setup(bot):
    misc = Misc(bot)
    bot.add_cog(misc)
    bot.misc = misc
