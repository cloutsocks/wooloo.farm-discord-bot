import discord
import random
import time
import re
import asyncio

import checks

from common import clamp, idPattern, send_message, print_error, resolve_mention, send_user_not_found, \
                   pokeballUrl, TYPE_COLORS, DBL_BREAK, FIELD_BREAK, EMOJI, ANNOUNCE_EMOJI, ICON_ATTACK, ICON_CLOSE
from discord.ext import commands

from trainers import ign_as_text, fc_as_text

MAXRAIDS = 10

RAID_EMOJI = '🍰'
LOCK_EMOJI = '🔒'


def make_readme(active_raids_id, raid_thanks_id):
    return [f'''
**Everyone, Read Me Carefully** 
- your raid has been posted to <#{active_raids_id}>, where trainers can join the **raid pool** by clicking {EMOJI["pokeball"]} or {EMOJI["masterball"]} 
- anyone in the raid pool can type in this channel
- i, mr. wooloo.farm bot, will try to make it as painless as possible for you!
- when there are more than 3 trainers or you're ready to start hosting, type `.round <4 digit code>` to start a new round!
- when the round is complete, just repeat the command to start the next one!
- you can also re-use the same code for subsequent rounds by just typing `.round`
- every time you start a round, 3 trainers in the pool will be chosen at random to join you, with {EMOJI["masterball"]} having priority
   :one: i'll ping the 3 users whose turn it is, and show you their IGN, Switch Name and FC to compare against
   :two: it does not matter if a user fails to catch a pokemon, we still take turns one by one _until everyone has gone_
   :three: i'll continue to choose 3 trainers until **everyone in the pool has had a turn**
   :four: once everyone has gone, we'll shuffle the pool and start again!

**Keeping Things Nice**
- when participants are finished raiding or want a break, you are expected and required to leave the raid by **unclicking** the {EMOJI["pokeball"]} or {EMOJI["masterball"]} in <#{active_raids_id}>
- **you can rejoin** at any time
- hosts are completely free to remove users for **any reason whatsoever, no questions asked**! this is their room and they do not have to host you.
   * if you'd like to temporarily remove a user from _this_ raid, use `.kick @user`
   * if you'd like to block a user from _all_ of your raids, use `.block @user`
   * you can check your block list with `.block` and unblock a trainer with `.unblock @user`
- reacting to a block is forbidden, if this happens, contact mods. **hosts do not have to explain why they blocked you.**
''',

f'''
**Recommendations**
- if a trainer is afk when it's time for them to join, we recommend you `.kick` or `.block` them.
- for a gentler option, `.skip` will find a new trainer to replace them and ping them accordingly, leaving the afk trainer in the pool
- if someone is unnecessarily greedy, hostile, joins out of order, spammy or worse - just `block` them
- if a trainers "forgets" to use their masterball when they sign up as {EMOJI["masterball"]} _definitely_ block them

**Misc & Wrapping Up**
- a trainer who previously signed up as {EMOJI["pokeball"]} may switch to using a masterball **once** by going back to <#{active_raids_id}> and clicking the {EMOJI["masterball"]}
- when you are finished hosting, type `.end`
   * this channel will close, and users will be directed to <#{raid_thanks_id}> to send a little :blue_heart: your way as thanks
   * **do not go afk!** _you cannot pause raids._ if you wait 30 minutes, it's likely many of the users in your pool will be away and the whole thing falls apart
   * you can, however, end the raid and create a new one when you're back! it'll work just as good :))
            
**Host Commands Recap**
- `.round <code>` or `.round` after a code is set
- `.block` / `.unblock` / `.kick` / `.skip` `@user` or `<1-3>` during a round
- `.end`

''']


def make_error_msg(err, uid):
    if err == 'WF_NO_ACCOUNT':
        msg = 'You do not have a linked profile on http://wooloo.farm/ ! In order to raid, you must link a discord account with your 🗺️ **friend code**, ✨ **in-game name**, and 🎮 **switch name**. This allows others to quickly add or verify you during a chaotic raid.'

    elif err.startswith('WF_NOT_SET'):
        key = err.split(': ')[1]
        msg = f'Your {key} is not set on http://wooloo.farm/profile/edit , please update it accordingly. In order to raid, you must link a discord account with your 🗺️ **friend code**, ✨ **in-game name**, and 🎮 **switch name**. This allows others to quickly add or verify you during a chaotic raid.'

    elif err.startswith('WF_NO_IGN'):
        msg = f'Your in-game name is not set on http://wooloo.farm/profile/edit , please update it accordingly. This is the trainer name that appears in-game. If you own both games, both can be stored.'

    elif err == 'ROLE_BANNED_FROM_RAIDING':
        msg = 'You are currently banned from raiding on the server. You will not be able to join or host any raids.'

    elif err == 'ROLE_BANNED_FROM_HOSTING':
        msg = 'You are currently banned from hosting raids on the server. You will be able to join raids, but you cannot host your own.'

    else:
        msg = f'An unknown error {err} is preventing that action for your account. Please contact jacob#2332 with this error message.'

    return f"<@{uid}> {msg} {EMOJI['flop']}"


class RaidPool(object):
    def __init__(self):
        self.queued_until_shuffle = []
        self.mb = []
        self.pb = []
        # self.mb = [340838512834117632, 340838512834117632]
        # self.pb = [340838512834117632, 340838512834117632, 340838512834117632, 340838512834117632, 340838512834117632, 340838512834117632]
        self.used_mb = []
        self.join_history = []
        self.kicked = []

    def size(self):
        return len(self.mb) + len(self.pb) + len(self.queued_until_shuffle)

    def as_text(self):
        return f'''queued: {self.queued_until_shuffle}
mb {self.mb}
pb {self.pb}
used_mb {self.used_mb}'''

    def get_group(self, n):
        group = []
        while len(group) < n and self.mb:
            group.append(('mb', self.mb.pop(0)))

        while len(group) < n and self.pb:
            group.append(('pb', self.pb.pop(0)))

        if len(group) == n:
            self.queued_until_shuffle += [t[1] for t in group]
            return group, False
        else:
            while len(group) < n and self.queued_until_shuffle:
                group.append(('pb', self.queued_until_shuffle.pop(0)))

            self.pb = self.queued_until_shuffle + [t[1] for t in group]
            self.queued_until_shuffle = []
            random.shuffle(self.pb)
            return group, True

    def status_as_text(self, shuffled):
        if shuffled:
            return f'♻️  Everyone in the pool has had an attempt, so it\'s been **reshuffled** with all the new raiders added! There are now **{self.size()}** trainers in the pool, **0** on standby.'

        pool_size = len(self.pb) + len(self.mb)

        return f'♻️  **{pool_size}** trainers left in pool until reshuffle, **{len(self.queued_until_shuffle)}** on standby, to be added next shuffle.'


class HostedRaid(object):
    def __init__(self, bot, host):
        self.bot = bot
        self.host = host

        self.raid_name = None
        self.channel = None
        self.channel_name = None
        self.desc = None
        self.listing_message = None

        self.round = 0
        self.max_joins = 30
        self.pool = None
        self.group = None

        self.start_time = None
        self.code = None

        self.message = None
        self.ctx = None

        self.confirmed = False
        self.closed = False

    '''
    creation
    '''

    def destroy(self):
        self.bot.clear_wait_fors(self.host)

    async def send_confirm_prompt(self, ctx, raid_name, channel_name, desc=None, max_joins=30):
        if self.confirmed or self.channel or self.message:
            return

        self.raid_name = raid_name
        self.channel_name = channel_name
        self.max_joins = clamp(max_joins, 3, 30)
        if not desc:
            msg = f'''<@{self.host.id}> This will create a new raid host channel called `#{channel_name}` allowing a maximum of **{self.max_joins}** raiders, are you sure you want to continue?
            
You may also set a welcome / introduction / description message such as: `.host new <name> "please leave my raids after catching or i will block"` or whatever else you\'d like your guests to know (stats, etc). Type `.host new help` for more setting options.'''
        else:
            self.desc = desc
            msg = f'''<@{self.host.id}> This will create a new raid host channel called `#{channel_name}` allowing a maximum of **{self.max_joins}** raiders with the description `{desc}`
            
Are you sure you want to continue? Type `.host new help` for more setting options.'''


        self.message = await ctx.send(msg)
        for reaction in [EMOJI['pokeball'], ICON_CLOSE]:
            await self.message.add_reaction(reaction.strip('<>'))

        self.bot.wfr[self.host.id] = self
        self.ctx = ctx

    async def handle_reaction(self, reaction, user):
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

        self.pool = RaidPool()
        self.group = []

        self.channel = await self.bot.raid.make_raid_channel(self, channel_ctx)

        await self.channel.send(f"{EMOJI['wooloo']} _Welcome to your raid room, <@{self.host.id}>!_")

        readme = make_readme(self.bot.raid.listing_channel.id, self.bot.raid.thanks_channel.id)
        msg = await self.channel.send(f"{FIELD_BREAK}{readme[0]}")
        await self.channel.send(f"{FIELD_BREAK}{readme[1]}")
        await msg.pin()

        await self.make_raid_post()

    async def make_raid_post(self):
        profile = await self.bot.trainers.get_wf_profile(self.host.id)
        games = []
        if '0' in profile['games'] and 'name' in profile['games']['0'] and profile['games']['0']['name']:
            games.append([f"{EMOJI['sword']} **IGN**", profile['games']['0']['name']])

        if '1' in profile['games'] and 'name' in profile['games']['1'] and profile['games']['1']['name']:
            games.append([f"{EMOJI['shield']} **IGN**", profile['games']['1']['name']])

        description = f'''{RAID_EMOJI} _hosted by <@{self.host.id}> in <#{self.channel.id}>_'''
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

    async def make_thanks_post(self):
        profile = await self.bot.trainers.get_wf_profile(self.host.id)
        games = []
        if '0' in profile['games'] and 'name' in profile['games']['0'] and profile['games']['0']['name']:
            games.append([f"{EMOJI['sword']} **IGN**", profile['games']['0']['name']])

        if '1' in profile['games'] and 'name' in profile['games']['1'] and profile['games']['1']['name']:
            games.append([f"{EMOJI['shield']} **IGN**", profile['games']['1']['name']])

        description = f'''✨ **Raid Host Complete!**

_This raid was hosted by <@{self.host.id}>_

To thank them, react with a 💙 ! If you managed to catch one, add in a {EMOJI['pokeball']} !'''
        if self.desc:
            description += f'\n\n_"{self.desc}"_'
        description += FIELD_BREAK

        footer = ''
        thumbnail = f"https://static.wooloo.farm/games/swsh/species_lg/831{'_S' if 'shiny' in self.channel_name.lower() else ''}.png"
        color = random.choice(TYPE_COLORS)
        e = discord.Embed(title=self.raid_name, description=description, color=color) \
            .set_thumbnail(url=thumbnail).set_footer(text=footer) \
            .add_field(name='🗺️ FC', value=f"SW-{profile['friend_code']}", inline=True)

        for ign in games:
            e.add_field(name=ign[0], value=ign[1], inline=True)

        e.add_field(name='🎮 Switch Name', value=profile['switch_name'], inline=True)

        thanks_message = await self.bot.raid.thanks_channel.send('', embed=e)
        for reaction in ['💙', EMOJI['pokeball']]:
            await thanks_message.add_reaction(reaction.strip('<>'))


    '''
    rounds
    '''

    async def round_command(self, ctx, arg):
        if self.closed or not self.channel:
            return

        # todo max rounds

        if ctx.channel != self.channel:
            return await send_message(ctx, f'Please initialize rounds in the actual raid channel.', error=True)

        code = None
        if arg:
            m = re.search(r'\d\d\d\d', arg)
            if m:
                code = m.group(0)
        elif self.code:
            code = self.code
        if not code:
            return await send_message(ctx, f'Please choose a valid 4-digit code in the form `.round 1234`. You can re-use this code for subsequent rounds by just typing `.round`', error=True)

        self.code = code
        await self.new_round(ctx)

    async def new_round(self, ctx):

        size = self.pool.size()
        if size < 3:
            return await send_message(ctx, f'There are currently **{size}** participants, but You need at least **3** to start a raid.', error=True)

        self.round += 1
        self.group, reshuffled = self.pool.get_group(3)

        pool_text = self.pool.status_as_text(reshuffled)
        announcer = random.choice(ANNOUNCE_EMOJI)
        title = f'{announcer} 📣 Round {self.round} Start!'
        description = f'''The code to join is **{self.code}**! Do **not** join unless you have been named below!{DBL_BREAK}If a trainer is AFK, the host may choose to `.kick` `.block` or `.skip` them, using `.<command> <1, 2 or 3>` or `. <action> @name`{DBL_BREAK}{pool_text}{FIELD_BREAK}'''
        e = discord.Embed(title=title, description=description)  # .set_footer(text='🐑 wooloo.farm')

        mention = f'<@{self.host.id}>'
        profile = await self.bot.trainers.get_wf_profile(self.host.id)
        profile_info = fc_as_text(profile)
        icon = '👑'
        raider_text = f'{icon} {mention}\n{profile_info}{FIELD_BREAK}'
        e.add_field(name='Host', value=raider_text, inline=False)

        mentions = []
        for i, raider in enumerate(self.group):
            join_type, raider_id = raider
            mention = f'<@{raider_id}>'
            mentions.append(mention)
            profile = await self.bot.trainers.get_wf_profile(raider_id, ctx)
            profile_info = fc_as_text(profile)
            icon = EMOJI['masterball'] if join_type == 'mb' else EMOJI['pokeball']
            raider_text = f'{icon} {mention}\n{profile_info}'

            if i < len(self.group) - 1:
                raider_text += FIELD_BREAK

            # numoji = [':one:', ':two:', ':three:'][i]
            numoji = ['1', '2', '3'][i]
            e.add_field(name=numoji, value=raider_text, inline=False)

        await ctx.send(' '.join(mentions), embed=e)


    '''
    managemnt
    '''

    async def skip(self, member, ctx):
        pass

    async def kick(self, member, ctx):

        await self.channel.set_permissions(member, read_messages=False)

        uid = member.id
        if uid in self.pool.pb:
            self.pool.pb.remove(uid)
        if uid in self.pool.mb:
            self.pool.mb.remove(uid)
        if uid in self.pool.queued_until_shuffle:
            self.pool.queued_until_shuffle.remove(uid)
        self.pool.kicked.append(uid)

        await member.send(f"You were kicked from this raid and cannot rejoin. You probably didn't read the rules or were unpleasant. Do better next time.")

        msg = f'<@{uid}> has been kicked from this raid. They will not be able to see this channel or rejoin.'
        if member.id in [t[1] for t in self.group]:
            msg += ' They were in the current raid group, so we recommend choosing someone at random to join. We will do this step for you soon.'
        return await ctx.send(msg)

    async def block(self, member, ctx):
        pass

    '''
    joins/leaves
    '''

    async def add_user(self, user, join_type, reaction):
        uid = user.id
        if uid == self.host.id:
            return

        member = self.bot.raid.guild.get_member(uid)
        can_raid, err = await self.bot.trainers.can_raid(member, self.host.id)
        if not can_raid:
            await reaction.message.remove_reaction(reaction, user)
            msg = make_error_msg(err, uid)
            if member:
                await member.send(msg)
            return

        # todo blocklist / removelist

        if uid in self.pool.kicked:
            return await member.send(f"You were kicked from this raid and cannot rejoin. You probably didn't read the rules or were unpleasant. Do better next time.")

        if self.pool.size() + 1 >= self.max_joins:
            return await member.send(f"Unfortunately, that raid is full! Try another one or wait a little bit and check back.")

        if self.closed:
            return

        if join_type == 'mb':
            if uid in self.pool.used_mb:
                return await member.send(f"You've already joined this raid as a masterball user (which gets priority!), so you cannot do so again. It does not matter if you \"missed\" and did not use your masterball. You may re-join as a regular user though, with {EMOJI['pokeball']}!")

            if uid in self.pool.mb:
                return

            if uid in self.pool.pb:
                join_type = 'mb+'

            if uid in self.pool.pb:
                self.pool.pb.remove(uid)
            if uid in self.pool.queued_until_shuffle:
                self.pool.queued_until_shuffle.remove(uid)

            self.pool.used_mb.append(uid)
            self.pool.mb.append(uid)
            await self.send_join_msg(member, join_type)
            await self.channel.set_permissions(member, send_messages=True)
            self.pool.join_history.append(uid)

        elif join_type == 'pb':
            if uid in self.pool.pb or uid in self.pool.mb or uid in self.pool.queued_until_shuffle:
                await reaction.message.remove_reaction(reaction, user)
                return

            self.pool.queued_until_shuffle.append(uid)
            await self.send_join_msg(member, join_type)
            await self.channel.set_permissions(member, send_messages=True)
            self.pool.join_history.append(uid)

    async def remove_user(self, user):
        uid = user.id
        if uid in self.pool.pb:
            self.pool.pb.remove(uid)
        if uid in self.pool.mb:
            self.pool.mb.remove(uid)
        if uid in self.pool.queued_until_shuffle:
            self.pool.queued_until_shuffle.remove(uid)

        member = self.bot.raid.guild.get_member(uid)
        await self.channel.set_permissions(member, send_messages=False)
        await member.send(f'You have left the `{self.raid_name}` raid, but you can rejoin at any time.')

    async def send_join_msg(self, member, join_type):

        profile = await self.bot.trainers.get_wf_profile(member.id)
        profile_info = fc_as_text(profile)

        if join_type == 'pb':
            if member.id not in self.pool.join_history:
                return await self.channel.send(f"{FIELD_BREAK}{EMOJI['join']} <@{member.id}> has joined the raid! Please read the **pinned message**.\n{profile_info}{FIELD_BREAK}")
            else:
                return await self.channel.send(f"{EMOJI['join']} <@{member.id}> has rejoined the raid!")

        elif join_type == 'mb':
            if member.id not in self.pool.join_history:
                return await self.channel.send(f"{EMOJI['masterball']} <@{member.id}> has joined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them. Please read the **pinned message**.\n{profile_info}{FIELD_BREAK}")
            else:
                return await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}")

        elif join_type == 'mb+':
            return await self.channel.send(f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}")

    async def end(self, immediately=False):
        self.closed = True
        await self.channel.trigger_typing()
        await self.channel.edit(name=f'{LOCK_EMOJI}{self.channel_name[1:]}')
        for target, overwrite in self.channel.overwrites.items():
            await self.channel.set_permissions(target, overwrite=None)

        await self.channel.set_permissions(self.bot.raid.guild.default_role, send_messages=False, add_reactions=False)
        await self.channel.set_permissions(self.bot.raid.guild.me, send_messages=True, add_reactions=True)

        if not immediately:
            if self.round >= 3 and not immediately:
                msg = f'''✨ **Raid Host Complete!**
        
Thank you for raiding, this channel is now closed!

To thank <@{self.host.id}> for their hard work with hosting, head to <#{self.bot.raid.thanks_channel.id}> and react with a 💙 !
If you managed to catch one, add in a {EMOJI['pokeball']} !

_This channel will automatically delete in a little while_ {EMOJI['flop']}'''

                '''
                this won't work until 3.5
                overwrites = {
                    self.bot.raid.guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
                    self.bot.raid.guild.me: discord.PermissionOverwrite(send_messages=True, add_reactions=True),
                }
                await self.channel.edit(name=f'{LOCK_EMOJI}{self.channel_name[1:]}', overwrites={})
                '''
                await self.make_thanks_post()
            else:
                msg = f'''✨ **Raid Host Complete!**
    
Thank you for raiding, this channel is now closed! We won't make a "thanks" post since it was such a short one (in case it was a mistake or so).

_This channel will automatically delete in a little while_ {EMOJI['flop']}'''
            await self.channel.send(msg)

        await self.listing_message.delete()

        if not immediately:
            await asyncio.sleep(60 * 10)
        await self.channel.delete()
        del self.bot.raid.raids[self.host.id]
        self.destroy()

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
    async def on_reaction_add(self, reaction, user):
        await self.reaction_action('add', reaction, user)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        await self.reaction_action('remove', reaction, user)

    async def reaction_action(self, action, reaction, user):
        if not self.listing_channel:
            return

        if user.id == self.bot.user.id:
            return

        if reaction.message.channel.id != self.listing_channel.id:
            return

        if str(reaction.emoji) not in [EMOJI['pokeball'], EMOJI['masterball']]:
            return

        raid = None
        for host_id, r in self.raids.items():
            if r.listing_message.id == reaction.message.id:
                raid = r

        if action == 'add':
            join_type = 'mb' if str(reaction.emoji) == EMOJI['masterball'] else 'pb'
            await raid.add_user(user, join_type, reaction)

        elif action == 'remove':
            await raid.remove_user(user)

    # todo move to admin module
    @commands.command()
    @checks.is_jacob()
    async def say(self, ctx, *, arg):
        await ctx.send(arg)

    # @commands.group(invoke_without_command=True)
    # async def raid(self, ctx, arg=None):
    #     pass
    #     # message = await send_message(ctx, 'Top Level Raid')

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

        if arg is None or 'help' in arg:
            # todo help message
            return send_message(ctx, 'todo add help message (you probably want `.host new name "description/instructions go here" max=20`, the instructions and max raiders are optional)')

        uid = ctx.author.id
        try:
            cmd, arg = arg.split(' ', 1)
        except ValueError:
            cmd = arg
            arg = None

        # .host block <options>
        # if cmd == 'block' or cmd == 'unblock':
        #     return await send_message(ctx, f'Blocks coming soon. Tag a raid mod for now.', error=True)
        #     # return await self.toggle_block(cmd, arg)

        # .host new <options>
        if cmd == 'new':
            if not arg or 'help' in arg:
                # todo help message
                return send_message(ctx, 'todo add help message (you probably want `.host new name "description/instructions go here" max=20`, the instructions and max raiders are optional)')

            if len(self.raids) >= MAXRAIDS:
                return await send_message(ctx, f'Unfortunately, we already have the maximum number of **{MAXRAIDS}** raids being hosted.', error=True)

            if uid in self.raids:
                return await send_message(ctx, 'You are already configuring or hosting a raid.', error=True)

            max_joins = 30
            m = re.search(r'max=(\d*)', arg)
            if m:
                try:
                    max_joins = int(m.group(1))
                except ValueError:
                    return await send_message(ctx, 'Invalid value for max raiders. Include `max=n` or leave it out for `max=30`', error=True)
                arg = arg.replace(m.group(0), '')

            desc = None
            m = re.search(r'\"(.*)\"', arg, flags=re.DOTALL)
            if m:
                desc = m.group(1)
                arg = arg.replace(m.group(0), '')

            name = arg.strip()
            channel_name = f"{RAID_EMOJI}-{name.replace(' ', '-')}"


            can_host, err = await self.bot.trainers.can_host(ctx.author, ctx)
            if not can_host:
                msg = make_error_msg(err, uid)
                return await send_message(ctx, msg, error=True)

            self.raids[uid] = HostedRaid(self.bot, ctx.author)
            await self.raids[uid].send_confirm_prompt(ctx, name, channel_name, desc, max_joins)

        # .host round <code>
        if cmd == 'round':
            if uid in self.raids:
                return await self.raids[uid].round_command(ctx, arg)

        if cmd == 'end' or cmd == 'close':
            if uid in self.raids:
                return await self.raids[uid].end()


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

    @commands.command()
    async def round(self, ctx, arg=None):
        uid = ctx.author.id
        if uid in self.raids:
            return await self.raids[uid].round_command(ctx, arg)

    @commands.command(aliases=['end'])
    async def close(self, ctx, arg=None):
        uid = ctx.author.id
        if uid in self.raids:
            return await self.raids[uid].end()

        user = self.bot.get_user(uid)

        if ctx.author.guild_permissions.administrator:
            for host_id, raid in self.raids.items():
                if raid.channel == ctx.channel:
                    print("admin close")
                    print("immediately" in arg)
                    return await raid.end('immediately' in arg)


    '''
    host moderation
    '''

    @commands.command()
    async def skip(self, ctx, *, arg=None):
        await self.host_moderation(ctx, 'skip', arg)

    @commands.command()
    async def kick(self, ctx, *, arg=None):
        await self.host_moderation(ctx, 'kick', arg)

    @commands.command()
    async def block(self, ctx, *, arg=None):
        await self.host_moderation(ctx, 'block', arg)

    async def host_moderation(self, ctx, action, arg):
        if not arg:
            return

        uid = ctx.author.id
        if not uid in self.raids:
            return

        member = resolve_mention(ctx.message.guild, arg, False)
        if not member:
            return await send_user_not_found(ctx, arg)

        if action == 'block' or 'action' == 'skip':
            await ctx.send(f'`.block` and `.skip` coming soon, but for now we will attempt to `.kick` the user.')
            action = 'kick'

        if action == 'kick':
            return await self.raids[uid].kick(member, ctx)


    @commands.command()
    async def tt(self, ctx):
        self.group = []
        self.round = random.randint(1, 20)
        self.code = 1234
        for i in range(3):
            self.group.append((random.choice(['pb', 'mb']), 340838512834117632))

        self.group = [
            ('mb', 340838512834117632),
            ('pb', 340838512834117632),
            ('pb', 340838512834117632),
        ]

        announcer = random.choice(ANNOUNCE_EMOJI)
        title = f'{announcer} 📣 Round {self.round} Start!'
        description = f'''The code to join is **{self.code}**! Do **not** join unless you have been named below!{DBL_BREAK}If a trainer is AFK, the host may choose to `.kick` `.block` or `.skip` them, using `.<command> <1, 2 or 3>` or `.<command> @name`{FIELD_BREAK}'''
        e = discord.Embed(title=title, description=description) #.set_footer(text='🐑 wooloo.farm')

        TEMP_HOST_ID = 232650437617123328
        mention = f'<@{TEMP_HOST_ID}>'
        profile = await self.bot.trainers.get_wf_profile(TEMP_HOST_ID)
        profile_info = fc_as_text(profile)
        icon = '👑'
        raider_text = f'{icon} {mention}\n{profile_info}{FIELD_BREAK}'
        e.add_field(name='Host', value=raider_text, inline=False)

        mentions = []
        for i, raider in enumerate(self.group):
            join_type, raider_id = raider
            mention = f'<@{raider_id}>'
            mentions.append(mention)
            profile = await self.bot.trainers.get_wf_profile(raider_id, ctx)
            profile_info = fc_as_text(profile)
            icon = EMOJI['masterball'] if join_type == 'mb' else EMOJI['pokeball']
            raider_text = f'{icon} {mention}\n{profile_info}'

            if i < len(self.group) - 1:
                raider_text += FIELD_BREAK

            # numoji = [':one:', ':two:', ':three:'][i]
            numoji = ['1', '2', '3'][i]
            e.add_field(name=numoji, value=raider_text, inline=False)

        await ctx.send(' '.join(mentions), embed=e)
    '''
    misc
    '''


    '''
    raid admin
    '''

    # @checks.is_jacob()
    # @commands.command()
    # async def init(self, ctx):
    #     await ctx.invoke(self.bind, 661468408856051733)

    # @checks.is_jacob()
    # @raid.group()
    # async def admin(self, ctx):
    #     await ctx.send('**[Raid Admin]**')
    #     if ctx.invoked_subcommand is None:
    #         await ctx.send('Invalid admin command')
    #
    # @checks.is_jacob()
    # @admin.command()
    # async def bind(self, ctx, category_id: int):
    #     try:
    #         self.category = self.bot.get_channel(category_id)
    #         self.guild = self.category.guild
    #     except AttributeError:
    #         await ctx.send(f'Could not bind to {category_id}')
    #     await ctx.send(f'Succesfully bound to **{self.category.name}** on server **{self.category.guild.name}**')

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
                if channel.name.startswith(RAID_EMOJI) or channel.name.startswith(LOCK_EMOJI):
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

        topic = 'please read the pinned message before raiding'
        channel = await self.guild.create_text_channel(raid.channel_name, overwrites=overwrites, category=self.category, topic=topic)
        return channel

    def bind_to_categories(self):
        if not self.bot.is_ready():
            return False

        # cid = 661468408856051733 # test
        cid = 661425972158922772 # live
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


