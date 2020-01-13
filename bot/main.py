import json
import os
import asyncio
import random
import secrets
import discord
import logging
import traceback
import sys
import sqlite3
import time
import error

import checks

from common import idPattern, send_message
from discord.ext import commands

initial_extensions = (
    'common',
    'error',
    'trainers',
    'misc',
    'raid',
)


def command_prefixes(bot, message):
    return ['.']


# https://discordapp.com/api/oauth2/authorize?client_id=660980949231599646&permissions=2146827601&scope=bot
class WoolooBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=command_prefixes)

        # self.trainerdb = sqlite3.connect('data/trainers.db')

        self.trainers = None
        self.raid = None
        self.misc = None

        self.wfr = {}
        self.wfm = {}

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
            except Exception as e:
                print(f'Failed to load extension {extension}.', file=sys.stderr)
                traceback.print_exc()

    def clear_wait_fors(self, uid):
        self.wfr.pop(uid, None)
        self.wfm.pop(uid, None)

bot = WoolooBot()

# @bot.check
# async def debug_restrict_jacob(ctx):
#     return ctx.message.author.id == 232650437617123328 or ctx.message.author.id == 340838512834117632

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))
    playing = discord.Game(name='with other Wooloo')
    await bot.change_presence(activity=playing)

    # for cog in bot.cogs:
    #     print(cog)

@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return

    if user.id in bot.wfr and bot.wfr[user.id].message.id == reaction.message.id:
        await bot.wfr[user.id].handle_reaction(reaction, user)
        await reaction.message.remove_reaction(reaction, user)


@bot.event
async def on_message(message):
    if message.author == bot.user or message.guild is None:
        return

    await bot.process_commands(message)
    uid = message.author.id
    if uid in bot.wfm:
        data = bot.wfm[uid]
        if data['channel'] != message.channel:
            return
        try:
            if time.time() > data['expires']:
                del bot.wfm[uid]
                return
        except KeyError:
            pass

        await data['handler'].handle_message(message)


@bot.command(name='reloadall', aliases=['reall', 'ra'])
@checks.is_jacob()
async def _reloadall(ctx, arg=None):
    """Reloads all modules."""

    bot.wfm = {}
    bot.wfr = {}
    try:
        for extension in initial_extensions:
            bot.unload_extension(extension)
            bot.load_extension(extension)
    except Exception as e:
        await ctx.send(f'```py\n{traceback.format_exc()}\n```')
    else:
        await ctx.send('✅')


with open('../config/discord_app.json') as f:
    config = json.load(f)

bot.run(config['token'])