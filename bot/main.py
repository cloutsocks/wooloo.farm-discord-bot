import json
import os
import sys
import time
import traceback
import demoji

import discord
from discord.ext import commands

import checks

initial_extensions = (
    'common',
    'error',
    'trainers',
    'misc',
    'raid.cog',
)

demoji.download_codes()

def command_prefixes(bot, message):
    return ['.']


# main  https://discordapp.com/api/oauth2/authorize?client_id=660980949231599646&permissions=2146827601&scope=bot
# dev   https://discordapp.com/api/oauth2/authorize?client_id=668968686094123030&permissions=2146827601&scope=bot
# guest https://discordapp.com/api/oauth2/authorize?client_id=676241025613824000&permissions=2146827601&scope=bot

class WoolooBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=command_prefixes)

        # todo _cog suffix
        self.trainers = None
        self.raid_cog = None
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
bot.help_command = None

# @bot.check
# async def debug_restrict_jacob(ctx):
#     return ctx.message.author.id == 232650437617123328 or ctx.message.author.id == 340838512834117632


@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))
    # status = 'on wooloo.farm' if bot.config['guest_server'] else 'with other Wooloo'
    status = 'with other Wooloo'
    playing = discord.Game(name=status)
    await bot.change_presence(activity=playing)


@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return

    if user.id in bot.wfr and bot.wfr[user.id].wfr_message.id == reaction.message.id:
        await bot.wfr[user.id].handle_reaction(reaction, user)
        await reaction.message.remove_reaction(reaction, user)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    # if message.guild is None:
    #     return

    uid = message.author.id
    if uid in bot.wfm:
        waiter = bot.wfm[uid]
        if waiter['channel'] != message.channel:
            return
        try:
            if time.time() > waiter['expires']:
                del bot.wfm[uid]
                return
        except KeyError:
            pass

        await waiter['handler'].handle_message(message)


@bot.check
async def globally_block_dms(ctx):
    return ctx.guild is not None or ctx.author.id in bot.config['creator_ids'] or ctx.command.name == 'raffle'


with open(os.environ.get('WOOLOOBOT_CONFIG_PATH', '../config/discord_app.json')) as f:
    bot.config = json.load(f)
    for key in ['raids_cid', 'archive_cid', 'listing_channel', 'thanks_channel', 'log_channel', 'banned_from_raiding_role', 'banned_from_hosting_role']:
        bot.config[key] = int(bot.config[key])

    for key in ['announce_channels', 'raid_admin_roles', 'creator_ids', 'wooloo_staff_ids']:
        bot.config[key] = [int(val) for val in bot.config[key]]

if not bot.config.get('disable_hot_reload', False):
    @bot.command(name='reloadall', aliases=['reall', 'ra'])
    @checks.is_jacob()
    async def _reloadall(ctx, arg=None):
        """Reloads all modules."""

        bot.wfm = {}
        bot.wfr = {}
        try:
            for extension in initial_extensions:
                if extension == 'raid.cog':
                    bot.raid_cog.reload_deps()
                bot.unload_extension(extension)
                bot.load_extension(extension)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send('✅')

bot.run(bot.config['token'])
