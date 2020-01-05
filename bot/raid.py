import sys
import traceback

import discord
import asyncio
import random
import math
import gzip
import json
import time
import secrets
import re

import checks

from numpy import interp
from collections import Counter

from common import idPattern, send_message, print_error, \
                   pokeballUrl, TYPE_COLORS, DBL_BREAK, FIELD_BREAK, EMOJI, ICON_ATTACK, ICON_CLOSE
from discord.ext import commands

MAXRAIDS = 10


def make_readme(active_raids_id, raid_thanks_id):
    return [f'''
**Everyone, Read Me Carefully** 
- your raid has been posted to <#{active_raids_id}>, where trainers can join the **raid pool** by clicking {EMOJI["pokeball"]} or {EMOJI["masterball"]} 
- anyone in the raid pool can type in this channel
- i, mr. wooloo.farm bot, will try to make it as painless as possible for you!
- when there are more than 3 trainers or you're ready to start hosting, type `.raid round <4 digit code>` to start a new round!
- when the round is complete, just repeat the command to start the next one!
- every time you start a round, 3 trainers in the pool will be chosen at random to join you, with {EMOJI["masterball"]} having priority
   :one: i'll ping the 3 users whose turn it is, and show you their IGN, Switch Name and FC to compare against
   :two: it does not matter if a user fails to catch a pokemon, we still take turns one by one _until everyone has gone_
   :three: i'll continue to choose 3 trainers until **everyone in the pool has had a turn**
   :four: once everyone has gone, we'll shuffle the pool and start again!

**Keeping Things Nice**
- when participants are done raiidng, you are expected and required to leave the raid by **unclicking** the {EMOJI["pokeball"]} or {EMOJI["masterball"]} in <#{active_raids_id}> - **as of now, once you leave, you cannot rejoin**
- hosts are completely free to remove users for **any reason whatsoever, no questions asked**! this is their room and they do not have to host you.
   * if you'd like to temporarily remove a user from _this_ raid, use `.host remove @user`
   * if you'd like to block a user from _all_ of your raids, use `.host block @user`
   * you can check your block list with `.host block` and unblock a trainer with `.host unblock @user`
- reacting to a block is forbidden, if this happens, contact mods. **hosts do not have to explain why they blocked you.**
''',

f'''
**Recommendations**
- if a trainer is afk when it's time for them to join, we recommend you `remove` or `block` them. `.host replace` will find x new trainers to replace them and ping them accordingly.
- if someone is unnecessarily greedy, hostile, joins out of order, spammy or worse - just `block` them
- if a trainers "forgets" to use their masterball when they sign up as {EMOJI["masterball"]} _definitely_ block them

**Misc & Wrapping Up**
- a trainer who previously signed up as {EMOJI["pokeball"]} may switch to using a masterball **once** by going back to <#{active_raids_id}> and clicking the {EMOJI["masterball"]}
- when you are finished hosting, type `.host end`
   * this channel will close, and users will be directed to <#{raid_thanks_id}> to send a little :blue_heart: your way as thanks
   * **do not go afk!** _you cannot pause raids._ if you wait 30 minutes, it's likely many of the users in your pool will be away and the whole thing falls apart
   * you can, however, end the raid and create a new one when you're back! it'll work just as good :))
'''];


class HostedRaid(object):
    def __init__(self, bot, host):
        self.bot = bot
        self.host = host

        self.raid_name = None
        self.channel = None
        self.channel_name = None
        self.desc = None
        self.listing_message = None

        self.pbpool = None
        self.mbpool = None
        self.exited = None

        self.start_time = None
        self.code = None

        self.message = None
        self.ctx = None

        self.confirmed = False

    '''
    creation
    '''

    def destroy(self):
        self.bot.clear_wait_fors(self.host)

    async def send_confirm_prompt(self, ctx, raid_name, channel_name, desc=None):
        if self.confirmed or self.channel or self.message:
            return

        self.raid_name = raid_name
        self.channel_name = channel_name
        if not desc:
            msg = f'''<@{self.host.id}>\nThis will create a new raid host channel called `#{channel_name}`, are you sure you want to continue?
            
You may also set a welcome / introduction / description message such as: `.host new <name> "please leave my raids after catching or i will block"` or whatever else you\'d like your guests to know (stats, etc).'''
        else:
            self.desc = desc
            msg = f'''<@{self.host.id}>\nThis will create a new raid host channel called `#{channel_name}` with the description `{desc}`
            
Are you sure you want to continue?'''

        self.message = await ctx.send(msg)
        for reaction in [EMOJI['pokeball'], ICON_CLOSE]:
            await self.message.add_reaction(reaction.strip('<>'))

        self.bot.wfr[self.host.id] = self
        self.ctx = ctx

    async def handle_reaction(self, reaction, user):
        # print(f'Handled {reaction} for {user}')

        if not self.confirmed:
            emoji = str(reaction.emoji)
            if emoji == EMOJI['pokeball']:
                await self.confirm_and_create(reaction.message.channel)
            elif emoji == ICON_CLOSE:
                await self.bot.raid.cancel_before_confirm(self, reaction.message.channel)


    async def confirm_and_create(self, channel_ctx):

        self.bot.clear_wait_fors(self.host)

        if self.confirmed or self.channel:
            return

        if len(self.bot.raid.raids) >= MAXRAIDS:
            return await self.bot.raid.cancel_before_confirm(self, channel_ctx, f'Unfortunately, we already have the maximum number of **{MAXRAIDS}** raids being hosted. Please wait a bit and try again later.')

        # todo verify can host?

        self.message = None
        self.confirmed = True
        self.start_time = time.time()

        self.pbpool = []
        self.mbpool = []

        self.channel = await self.bot.raid.make_raid_channel(self, channel_ctx)

        await self.channel.send(f"{EMOJI['wooloo']} _Welcome to your raid room, <@{self.host.id}>!_")

        readme = make_readme(self.bot.raid.listing_channel.id, self.bot.raid.thanks_channel.id)
        msg = await self.channel.send(f"{FIELD_BREAK}{readme[0]}")
        await self.channel.send(f"{FIELD_BREAK}{readme[1]}")
        await msg.pin()

        await self.make_raid_post()

    async def make_raid_post(self):
        profile = await self.bot.trainers.get_wf_profile(None, self.host.id)
        games = []
        if '0' in profile['games'] and 'name' in profile['games']['0'] and profile['games']['0']['name']:
            games.append([f"{EMOJI['sword']} **IGN**", profile['games']['0']['name']])

        if '1' in profile['games'] and 'name' in profile['games']['1'] and profile['games']['1']['name']:
            games.append([f"{EMOJI['shield']} **IGN**", profile['games']['1']['name']])

        description = f'''🐉 _hosted by <@{self.host.id}> in <#{self.channel.id}>_'''
        if self.desc:
            description += f'\n\n_"{self.desc}"_'
        description += FIELD_BREAK

        instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool or {EMOJI["masterball"]} _only_ if you're going to use a masterball.

When you are done raiding, you **must** leave the raid by removing your {EMOJI["pokeball"]} reaction. Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''

        footer = ''
        thumbnail = f"https://static.wooloo.farm/games/swsh/species_lg/831{'_S' if 'shiny' in self.channel_name.lower() else ''}.png"
        color = random.choice(TYPE_COLORS)
        e = discord.Embed(title=self.raid_name, description=description, color=color) \
            .set_author(name=f'wooloo.farm', url='https://wooloo.farm/', icon_url=pokeballUrl) \
            .set_thumbnail(url=thumbnail).set_footer(text=footer) \
            .add_field(name='Instructions', value=instructions, inline=False) \
            .add_field(name='🗺️ FC', value=f"SW-{profile['friend_code']}", inline=True)

        for ign in games:
            e.add_field(name=ign[0], value=ign[1], inline=True)

        e.add_field(name='🎮 Switch Name', value=profile['switch_name'], inline=True)

        self.listing_message = await self.bot.raid.listing_channel.send('', embed=e)
        for reaction in [EMOJI['pokeball'], EMOJI['masterball']]:
            await self.listing_message.add_reaction(reaction.strip('<>'))


    '''
    join/leave
    '''

    async def add_user(self, uid):
        if uid == self.host.id:
            print('Host cannot join self')
            return




class Raid(commands.Cog):
    def __init__(self, bot):
        # self.db = db
        self.bot = bot
        self.cache = {}

        self.category = None
        self.guild = None
        self.listing_channel = None
        self.thanks_channel = None

        self.raids = {}

        if self.bot.is_ready():
            self.bot.loop.create_task(self.on_load())

    async def on_load(self):
        bound = self.bind_to_categories()
        if bound:
            await self.clear_channels_dirty()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.on_load()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, reaction):
        await self.reaction_action('add', reaction)

    async def reaction_action(self, action, reaction):
        if not self.listing_channel:
            return

        print(reaction)

        if reaction.user_id == self.bot.user.id:
            print('it bot')
            return

        if reaction.channel_id != self.listing_channel.id:
            print('not channel')
            return

        if str(reaction.emoji) not in [EMOJI['pokeball'], EMOJI['masterball']]:
            print('not emoji')
            return

        raid = None
        for uid, r in self.raids.items():
            if r.listing_message.id == reaction.message_id:
                raid = r

        if action == 'join':
            await raid.add_user(reaction.user_id)

    #todo move to admin module
    @commands.command()
    @checks.is_jacob()
    async def say(self, ctx, *, arg):
        await ctx.send(arg)

    @commands.group(invoke_without_command=True)
    async def raid(self, ctx, arg=None):
        message = await send_message(ctx, 'Top Level Raid')

    '''
    host
    '''

    # .host <name>
    # .host block
    # .host block <user>
    # .host unblock <user>
    # .host <round> <code>

    # @commands.has_role('raider')
    @commands.command()
    async def host(self, ctx, *, arg=None):

        if arg is None:
            await send_message(ctx, 'todo add help message', error=True)
            return False

        uid = ctx.author.id
        try:
            cmd, arg = arg.split(' ', 1)
        except ValueError:
            cmd = arg
            arg = None

        print(f'cmd: {cmd}')
        print(f'arg: {arg}')

        if cmd == 'block' or cmd == 'unblock':
            await self.toggle_block(cmd, arg)
            return

        if cmd == 'new':
            if len(self.raids) >= MAXRAIDS:
                return await send_message(ctx, f'Unfortunately, we already have the maximum number of **{MAXRAIDS}** raids being hosted.', error=True)

            if not arg:
                return await send_message(ctx, 'You must enter a channel name.', error=True)

            desc = None
            m = re.search(r'\"(.*)\"', arg, flags=re.DOTALL)
            if m:
                desc = m.group(1)
                arg = arg.replace(m.group(0), '')

            name = arg.strip()
            channel_name = f"🐉-{name.replace(' ', '-')}"

            if uid in self.raids:
                return await send_message(ctx, 'You are already configuring or hosting a raid.', error=True)

            can_host, err = await self.bot.trainers.can_host(ctx, uid)
            if not can_host:
                return await send_message(ctx, f'user cannot host, err: {err}', error=True)

            self.raids[uid] = HostedRaid(self.bot, ctx.author)
            await self.raids[uid].send_confirm_prompt(ctx, name, channel_name, desc)

    @host.error
    async def host_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send('oopsie poopsie')
        else:
            print_error(ctx, error)

    async def cancel_before_confirm(self, raid, channel, msg=''):
        del self.raids[raid.host.id]
        raid.destroy()
        await channel.send(f"<@{raid.host.id}> {msg}Your raid was cancelled. {EMOJI['flop']}")


    #     @commands.command()
#     async def tt(self, ctx):
#         await ctx.send('', embed=self.make_embed())
#
#     def make_embed(self):
#
#         description = f'''🐉 _hosted by <@232650437617123328> in <#662586677939798026>_
#
# _"please leave my raids after catching or i will have to block you from my raids"_{FIELD_BREAK}'''
#
#         instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool or {EMOJI["masterball"]} _only_ if you're going to use a masterball.
#
# When you are done raiding, you **must** leave the raid by removing your {EMOJI["pokeball"]} reaction. Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''
#
#         footer = ''
#         thumbnail = 'https://static.wooloo.farm/games/swsh/species_lg/831_S.png'
#         # thumbnail = 'https://static.wooloo.farm/games/swsh/species_lg/129_S.png'
#         color = random.choice(TYPE_COLORS)
#         e = discord.Embed(title='Shiny Magikarp', description=description, color=color) \
#             .set_author(name=f'wooloo.farm', url='https://wooloo.farm/', icon_url=pokeballUrl) \
#             .set_thumbnail(url=thumbnail).set_footer(text=footer) \
#             .add_field(name='Instructions', value=instructions, inline=False) \
#             .add_field(name='🗺️ FC', value='SW-2384-3743-2387', inline=True) \
#             .add_field(name='✨ IGN', value='jacob', inline=True) \
#             .add_field(name='🎮 Switch Name', value='jacob', inline=True) \
#             # .add_field(name='🐉 Channel', value='<#661492345434406913>', inline=True) \
#
#         return e


    '''
    raid admin
    '''

    # @checks.is_jacob()
    # @commands.command()
    # async def init(self, ctx):
    #     await ctx.invoke(self.bind, 661468408856051733)

    @checks.is_jacob()
    @raid.group()
    async def admin(self, ctx):
        await ctx.send('**[Raid Admin]**')
        if ctx.invoked_subcommand is None:
            await ctx.send('Invalid admin command')

    @checks.is_jacob()
    @admin.command()
    async def bind(self, ctx, category_id: int):
        try:
            self.category = self.bot.get_channel(category_id)
            self.guild = self.category.guild
        except AttributeError:
            await ctx.send(f'Could not bind to {category_id}')
        await ctx.send(f'Succesfully bound to **{self.category.name}** on server **{self.category.guild.name}**')

    # @admin.command()
    # async def testmake(self, ctx, count: int):
    #
    #     if self.category is None or self.guild is None:
    #         await send_message(ctx, f'No category bound! Try `.raid admin bind <category id>', error=True)
    #         return
    #
    #     users = ['elliot', 'rory', 'jacob', 'stinky']
    #     pkmn = ['gmax-hatterene', 'shiny-meowth', 'pikachu', 'charmander']
    #
    #     for i in range(count):
    #         name = f'{random.choice(pkmn)}-{random.choice(users)}'
    #         channel = await self.make_channel(name)
    #         self.channels.append(channel)
    #

    @checks.is_jacob()
    @commands.command()
    async def cl(self, ctx, arg=None):
        await self.clear_channels_dirty()

    async def clear_channels_dirty(self):
        if self.category:
            if self.listing_channel:
                await self.listing_channel.purge(limit=100)

            for channel in self.category.text_channels:
                if channel.name.startswith('🐉'):
                    await channel.delete()

    async def make_raid_channel(self, raid, channel_ctx):
        if self.category is None or self.guild is None:
            await channel_ctx.send(f"No category bound! jacob should write `.raid admin bind <category id>` {EMOJI['flop']}")
            return

        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, add_reactions=True),
            raid.host: discord.PermissionOverwrite(send_messages=True, add_reactions=True)
        }

        # todo ban list

        topic = 'please read pinned message before raiding'
        channel = await self.guild.create_text_channel(raid.channel_name, overwrites=overwrites, category=self.category, topic=topic)
        return channel

    def bind_to_categories(self):
        if not self.bot.is_ready():
            return False

        cid = 661468408856051733 #661425972158922772
        try:
            self.category = self.bot.get_channel(cid)
            self.guild = self.category.guild
            self.listing_channel = discord.utils.get(self.guild.text_channels, name='active-raids')
            self.thanks_channel = discord.utils.get(self.guild.text_channels, name='raid-thanks')
            print(f'Bound to {cid}', self.category, self.guild, self.listing_channel)

        except AttributeError:
            print(f'Could not bind to {cid}')
            return False

        return True


def setup(bot):
    raid = Raid(bot)
    bot.add_cog(raid)
    bot.raid = raid


