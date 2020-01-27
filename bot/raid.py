import json
import logging
import sqlite3
import discord
import random
import time
import re
import asyncio

import checks

from common import clamp, idPattern, send_message, print_error, resolve_mention, send_user_not_found, \
    pokeballUrl, TYPE_COLORS, DBL_BREAK, FIELD_BREAK, EMOJI, ANNOUNCE_EMOJI, ICON_ATTACK, ICON_CLOSE, enquote
from discord.ext import tasks, commands
from collections import namedtuple

from trainers import ign_as_text, fc_as_text

MAXRAIDS = 10

RAID_EMOJI = '🍰'
LOCKED_EMOJI = '🔒'
CLOSED_EMOJI = '💤'

DEFAULT, LOCKED, CLOSED = 1, 2, 3

CREATE_HELP = '''_Creating a Raid_
`.host <channel name>`
**+** _optional:_ `.host <channel name> "description goes here"` to set requirements (e.g. "leave after catching") or details (stats, etc)
**+** _optional:_ `.host <channel name> max=20` to limit raiders
**+** _optional:_ add `ffa` to `<channel name>` to disable managed queues
**+** _optional:_ add `no mb` to disable priority masterball raiders
**+** _optional:_ add `private` to hide the code from lurkers
**+** _optional:_ add `locked` lock the raid until you unlock with `.lock`'''

HOST_COMMANDS = '''`.host help` to show these commands
`.fc <@user>` to display FC / IGN / Switch Name
`.queue` / `.q` to show the current queue in the channel for everyone to see
`.round <4 digit code>` to start a new round (you can _optionally_ re-use the code thereafter with `.round`)
`.skip @user` to skip and replace someone in the current round
`.remove @user` to remove (and skip) a user from this raid (they cannot rejoin!)
`.block @user` to remove (and skip) a user from **all** of your raids
`.group <msg>` to ping everyone in the current round's group with a message
`.end` to end the raid, i'll DM you a list of users to help you clean your friend list
`.pin` to pin your last message
`.unpin <#>` to unpin a message
`.max <#>` to adjust max participants
`.lock` to temporarily prevent new raiders from joining (without stopping the raid)
`.private` to toggle a private raid (hidden codes from lurkers)
`.qfc` show the current queue WITH fc / switch name
[**NEW**]
`.poll <poll message> votes=🐄,🐈,🐖,🦌` to make a poll with reactions
'''

RAID_NOT_FOUND = '''You can only do this in an active raid channel. If this _was_ a raid channel, it has been disconnected from the bot, but the host can remake it from scratch. We're exploring possible options to handle this more gracefully.'''

def make_readme(desc, active_raids_id):
    notice = f"\n\nThe host expects everyone to know the following: _{enquote(desc)}_" if desc else ""

    # todo message limit
    return [f'''{EMOJI["wooloo"]} **Everyone, Read This Carefully** {EMOJI["wooloo"]}

I help manage raids! Everyone gets a turn in the order they joined, with {EMOJI["masterball"]} getting priority. Even if you don't catch it, it still counts as a turn. But don't worry! Once we cycle through everyone, we start the queue over.{notice}
''',

            f'''
**For Participants**
_Commands_
`.queue` / `.q` to have the current queue DM'd to you
`.caught` to indicate you've caught the Pokémon
`.code` to view the code (if set)
`.leave` to leave the raid

{EMOJI['check']} **1**)  if you don't follow instructions, you might get kicked or blocked by the host
{EMOJI['check']} **2**)  enter this raid by visiting <#{active_raids_id}>
{EMOJI['check']} **3**)  do not join until instructed to do so by the bot
{EMOJI['check']} **4**)  don't ask the host to join, for their friend code, or what the raid code is—**i'll tell you all of that when it's your turn** {EMOJI["flop"]}
{EMOJI['check']} **5**)  when you're done raiding, you **have** to leave the raid by **unclicking** the {EMOJI["pokeball"]} or {EMOJI["masterball"]} in <#{active_raids_id}> or by typing `.leave`
{EMOJI['check']} **6**)  you must also **remove the host from your friend's list**, even if you intend to raid with them again later!
{EMOJI['check']} **7**)  **you can rejoin** at any time (unless you've used a {EMOJI["masterball"]})
{EMOJI['check']} **8**)  hosts are completely free to remove users for **any reason whatsoever, no questions asked**! this is their room and they do not have to host you.
{EMOJI['check']} **9**)  don't react to a kick or block! **hosts do not have to explain why they blocked you.** if this happens, please contact mods.
{EMOJI['check']} **10**)  if you joined with a {EMOJI["pokeball"]}, you can switch to a masterball **once** by going back to <#{active_raids_id}> and clicking the {EMOJI["masterball"]} (but you better use one or you'll get blocked!)
{EMOJI['check']} **11**)  when you've caught the Pokémon, please write `.caught`!
{EMOJI['check']} **12**)  please `.pet`. me
''',

            f'''
**For Hosts**
_Commands_
{HOST_COMMANDS}

{EMOJI['check']} **1**)  you can `.remove` / `.block` someone for **any reason**, no questions asked! don't hesitate
{EMOJI['check']} **2**)  if someone is unnecessarily greedy, hostile, joins out of order, spammy or worse - just `block` them
{EMOJI['check']} **3**)  if a trainers "forgets" to use their masterball when they sign up as {EMOJI["masterball"]} _definitely_ block them
{EMOJI['check']} **4**)  **do not go afk when hosting!** _you cannot pause raids._ if you wait 30 minutes, it's likely many of the users in your pool will be away and the whole thing falls apart
{EMOJI['check']} **5**)  you can, however, `.end` the raid and create a new one when you're back! it'll work just as good :))
{EMOJI['check']} **6**)  `.skip` `.remove` or `.block` anyone who is afk during their turn (removed and blocked users **cannot rejoin**)
''']


def make_readme_ffa(desc, active_raids_id):
    notice = f"\n\nThe host expects everyone to know the following: {enquote(desc)}" if desc else ""

    # todo message limit
    return [f'''{EMOJI["wooloo"]} **Everyone, Read This Carefully** {EMOJI["wooloo"]}

This is a **free-for-all** raid! There is no queue, but follow the instructions of the host.{notice}
''',

            f'''
**For Participants**
_Commands_
`.queue` / `.q` to have the current queue DM'd to you
`.caught` to indicate you've caught the Pokémon
`.code` to view the code (if set)
`.leave` to leave the raid

{EMOJI['check']} **1**)  if you don't follow instructions, you might get kicked or blocked by the host
{EMOJI['check']} **2**)  enter this raid by visiting <#{active_raids_id}>
{EMOJI['check']} **3**)  when you're done raiding, you **have** to leave the raid by **unclicking** the {EMOJI["pokeball"]} or {EMOJI["masterball"]} in <#{active_raids_id}> or by typing `.leave`
{EMOJI['check']} **4**)  you must also **remove the host from your friend's list**, even if you intend to raid with them again later!
{EMOJI['check']} **5**)  hosts are completely free to remove users for **any reason whatsoever, no questions asked**! this is their room and they do not have to host you.
{EMOJI['check']} **6**)  don't react to a kick or block! **hosts do not have to explain why they blocked you.** if this happens, please contact mods.
{EMOJI['check']} **7**)  when you've caught the Pokémon, please write `.caught`!
{EMOJI['check']} **8**)  please `.pet`. me
''',

            f'''
**For Hosts**
_Commands_
{HOST_COMMANDS}

{EMOJI['check']} **1**)  you can `.remove` / `.block` someone for **any reason**, no questions asked! don't hesitate
{EMOJI['check']} **2**)  if someone is unnecessarily greedy, hostile, joins out of order, spammy or worse - just `.block` them
{EMOJI['check']} **3**)  **do not go afk when hosting!** _you cannot pause raids._
{EMOJI['check']} **4**)  you can, however, `.end` the raid and create a new one when you're back! it'll work just as good :))
''']


def make_error_msg(err, uid):
    if err == 'WF_NO_ACCOUNT':
        msg = 'You do not have a linked profile on http://wooloo.farm/ ! In order to raid, you must link a **public** (not marked private) discord account with your 🗺️ **friend code**, ✨ **in-game name**, and 🎮 **switch name**. This allows others to quickly add or verify you during a chaotic raid.'

    elif err.startswith('WF_NOT_SET'):
        key = err.split(': ')[1]
        msg = f'Your {key} is not set on http://wooloo.farm/profile/edit , please update it accordingly. In order to raid, you must link a **public** (not marked private) discord account with your 🗺️ **friend code**, ✨ **in-game name**, and 🎮 **switch name**. This allows others to quickly add or verify you during a chaotic raid.'

    elif err.startswith('WF_NO_IGN'):
        msg = f'Your in-game name is not set on http://wooloo.farm/profile/edit , please update it accordingly. This is the trainer name that appears in-game. If you own both games, both can be stored.'

    elif err == 'ROLE_BANNED_FROM_RAIDING':
        msg = 'You are currently banned from raiding on the server. You will not be able to join or host any raids.'

    elif err == 'ROLE_BANNED_FROM_HOSTING':
        msg = 'You are currently banned from hosting raids on the server. You will be able to join raids, but you cannot host your own.'

    else:
        msg = f'An unknown error {err} is preventing that action for your account. Please contact jacob#2332 with this error message.'

    return f"<@{uid}> {msg} {EMOJI['flop']}"


def show_member_for_log(member):
    return f"<@{member.id}> ({member.name}#{member.discriminator}, ID: {member.id}, Nickname: {member.nick})"

class RaidPool(object):
    def __init__(self):
        self.i = 0
        self.q = []
        self.mb = []
        self.used_mb = []
        self.join_history = []
        self.kicked = []

    def size(self):
        return len(self.mb) + len(self.q)

    def remove(self, uid):
        if uid not in self.join_history:
            return False

        removed = False
        if uid in self.mb:
            self.mb.remove(uid)
            removed = True

        try:
            index = self.q.index(uid)
            if index < self.i:
                self.i -= 1
            self.q.remove(uid)
            removed = True

        except ValueError:
            pass

        return removed

    def as_text(self):
        return f'''mb {self.mb}
pb {self.q}
used_mb {self.used_mb}'''

    def get_next(self, n=1, advance=False):

        mb_out = self.mb[:n]
        out = [('mb', uid) for uid in mb_out]

        if advance:
            self.mb = self.mb[n:]

        wraparound = False
        end = self.i + n - len(out)
        out += [('pb', uid) for uid in self.q[self.i:end]]
        if len(out) < n:
            wraparound = True
            end = remaining = n - len(out)
            out += [('pb', uid) for uid in self.q[0:remaining]]

        if advance:
            self.i = end
            # self.q += mb_out

        return out, wraparound


RaidRecord = namedtuple('RaidRecord',
                        'host_id, guild_id, raid_name, ffa, private, no_mb, channel_id, channel_name, desc, listing_msg_id, last_round_msg_id, round, max_joins, pool, raid_group, start_time, time_saved, code, locked, closed')


class HostedRaid(object):
    def __init__(self, bot, raid, guild, host_id):
        self.bot = bot
        self.raid = raid
        self.host_id = host_id
        self.guild = guild

        self.raid_name = None
        self.ffa = False
        self.private = False
        self.no_mb = False
        self.channel = None
        self.channel_name = None
        self.desc = None
        self.listing_message = None
        self.last_round_message = None
        self.pins = []

        self.round = 0
        self.max_joins = 30
        self.pool = None
        self.group = []

        self.start_time = None
        self.time_saved = None
        self.code = None

        self.wfr_message = None

        self.locked = False
        self.confirmed = False
        self.closed = False

        self.channel_emoji = RAID_EMOJI

        self.lock = asyncio.Lock()

    def __repr__(self):
        if self.time_saved:
            save_txt = f'saved {self.time_saved - time.time()} seconds ago'
        else:
            save_txt = 'not saved'
        return f'host:{self.host_id} {self.raid_name} - {save_txt}'

    '''
    serialize
    '''

    async def as_record(self):

        async with self.lock:
            should_serialize = self.wfr_message is None and self.confirmed and self.channel

            return RaidRecord(host_id=self.host_id,
                              guild_id=self.guild.id,
                              raid_name=self.raid_name,
                              ffa=self.ffa,
                              private=self.private,
                              no_mb=self.no_mb,
                              channel_id=self.channel.id if self.channel is not None else None,
                              channel_name=self.channel_name,
                              desc=self.desc,
                              listing_msg_id=self.listing_message.id if self.listing_message is not None else None,
                              last_round_msg_id=self.last_round_message.id if self.last_round_message is not None else None,
                              round=self.round,
                              max_joins=self.max_joins,
                              pool=json.dumps(self.pool.__dict__) if self.pool is not None else None,
                              raid_group=json.dumps(self.group) if self.group is not None else None,
                              start_time=self.start_time,
                              time_saved=int(time.time()),
                              code=self.code,
                              locked=self.locked,
                              closed=self.closed), should_serialize

    async def load_from_record(self, r):

        async with self.lock:
            err_prefix = f'[ABORT] Could not create raid {r.raid_name}'
            self.channel = self.bot.get_channel(r.channel_id)
            if not self.channel:
                err = f'{err_prefix}: channel {r.channel_id} not found'
                return False, err

            if not r.closed:
                try:
                    self.listing_message = await self.raid.listing_channel.fetch_message(r.listing_msg_id)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                    err = f'{err_prefix}: could not fetch listing message {r.listing_msg_id}. Error: {type(e).__name__}, {e}'
                    return False, err

                try:
                    if r.last_round_msg_id:
                        self.last_round_message = await self.channel.fetch_message(r.last_round_msg_id)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                    err = f'{err_prefix}: could not fetch last round message {r.last_round_msg_id}. Error: {type(e).__name__}, {e}'
                    return False, err


            # todo tony method
            self.pins = []

            self.host_id = r.host_id
            self.raid_name = r.raid_name
            self.ffa = r.ffa
            self.private = r.private
            self.no_mb = r.no_mb
            self.channel_name = r.channel_name
            self.desc = r.desc

            self.round = r.round
            self.max_joins = r.max_joins
            self.pool = RaidPool()
            if r.pool:
                self.pool.__dict__ = json.loads(r.pool)
            self.group = json.loads(r.raid_group) if r.raid_group else []

            self.start_time = r.start_time
            self.time_saved = r.time_saved
            self.code = r.code
            self.locked = r.locked
            self.confirmed = True
            self.closed = r.closed

        return True, None

    '''
    creation
    '''

    def destroy(self):
        self.bot.clear_wait_fors(self.host_id)

    async def send_confirm_prompt(self, ctx, raid_name, channel_name, desc=None, max_joins=30, private=False, no_mb=False, locked=False):

        async with self.lock:
            if self.confirmed or self.channel or self.wfr_message:
                return

            self.raid_name = raid_name
            self.channel_name = channel_name
            self.ffa = 'ffa' in self.channel_name.lower()
            self.max_joins = clamp(max_joins, 3, 50 if self.ffa else 30)
            self.private = private
            self.no_mb = no_mb
            self.locked = locked
            options = []
            if self.ffa:
                options.append('**FFA**')
            if self.private:
                options.append('**private** (hidden code)')
            if self.no_mb:
                options.append('**no masterball**')
            if self.locked:
                options.append('🔒 **locked**')

            if options:
                options = (', '.join(options)) + ' '
            else:
                options = ''

            if not desc:
                msg = f'''<@{self.host_id}> This will create a new {options}raid host channel called `#{channel_name}` allowing a maximum of **{self.max_joins}** raiders, are you sure you want to continue?

    {CREATE_HELP}'''
            else:
                self.desc = desc
                msg = f'''<@{self.host_id}> This will create a new {options}raid host channel called `#{channel_name}` allowing a maximum of **{self.max_joins}** raiders with the description _{enquote(self.desc)}_

    Are you sure you want to continue?

    {CREATE_HELP}'''

            self.wfr_message = await ctx.send(msg)
            for reaction in ['✅', ICON_CLOSE]:
                await self.wfr_message.add_reaction(reaction.strip('<>'))

            self.bot.wfr[self.host_id] = self

    async def handle_reaction(self, reaction, user):
        if not self.confirmed:
            emoji = str(reaction.emoji)
            if emoji == EMOJI['pokeball'] or emoji == '✅':
                await self.confirm_and_create(reaction.message.channel)
            elif emoji == ICON_CLOSE:
                await self.raid.cancel_before_confirm(self, reaction.message.channel)

    async def confirm_and_create(self, channel_ctx):
        self.bot.clear_wait_fors(self.host_id)

        async with self.lock:
            if self.confirmed or self.channel:
                return

            if len(self.raid.raids) >= MAXRAIDS:
                return await self.raid.cancel_before_confirm(self, channel_ctx,
                                                             f'Unfortunately, we already have the maximum number of **{MAXRAIDS}** raids being hosted. Please wait a bit and try again later.')

            # todo verify can host?
            await self.raid.log_channel.send(f"<@{self.host_id}> (ID: {self.host_id}) has created a new raid: {self.raid_name}.")

            self.wfr_message = None
            self.confirmed = True
            self.start_time = time.time()

            self.pool = RaidPool()
            self.group = []

            self.channel = await self.raid.make_raid_channel(self, channel_ctx)

            await self.channel.send(f"✨ _Welcome to your raid room, <@{self.host_id}>!_")

            readme = make_readme_ffa(self.desc, self.raid.listing_channel.id) if self.ffa \
                else make_readme(self.desc, self.raid.listing_channel.id)

            rm_intro = await self.channel.send(f"{FIELD_BREAK}{readme[0]}")
            rm_raider = await self.channel.send(f"{FIELD_BREAK}{readme[1]}")
            rm_host = await self.channel.send(f"{FIELD_BREAK}{readme[2]}")

            await rm_host.pin()
            await rm_raider.pin()
            await rm_intro.pin()

            mention = f'<@{self.host_id}>'
            profile = await self.bot.trainers.get_wf_profile(self.host_id)
            profile_info = fc_as_text(profile)
            raider_text = f'👑 {mention}\n{profile_info}{FIELD_BREAK}'
            e = discord.Embed(title='Host Details', description=raider_text)  # .set_footer(text='🐑 wooloo.farm')
            host_details = await self.channel.send('', embed=e)
            await host_details.pin()

            await self.make_listing_message()

        print('[Raid Confirmation]', self.raid.raids)
        self.bot.loop.create_task(self.raid.save_raids_to_db())

    '''
    self.lock must be held before calling - via confirm_and_create()
    '''
    async def make_listing_message(self):
        profile = await self.bot.trainers.get_wf_profile(self.host_id)
        games = []
        if '0' in profile['games'] and 'name' in profile['games']['0'] and profile['games']['0']['name']:
            games.append([f"{EMOJI['sword']} **IGN**", profile['games']['0']['name']])

        if '1' in profile['games'] and 'name' in profile['games']['1'] and profile['games']['1']['name']:
            games.append([f"{EMOJI['shield']} **IGN**", profile['games']['1']['name']])

        description = f'''{RAID_EMOJI} _hosted by <@{self.host_id}> in <#{self.channel.id}>_'''
        if self.desc:
            description += f'\n\n_{enquote(self.desc)}_'

        description += f'\n\n[Max **{self.max_joins}** raiders to start, but may change! Check for a {LOCKED_EMOJI}]'
        description += FIELD_BREAK

        # ffa mode
        if self.ffa:
            reactions = [EMOJI['pokeball']]
            instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool! This is an **FFA** raid (there is no bot-managed queue).

Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''
        # queue, no masterballs
        elif self.no_mb:
            reactions = [EMOJI['pokeball']]
            instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool! {EMOJI["masterball"]} are **disabled** for this raid.

When you are done raiding, you **must** leave the raid by removing your {EMOJI["pokeball"]} reaction or by typing `.leave`. Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''
        # queue, masterballs
        else:
            reactions = [EMOJI['pokeball'], EMOJI['masterball']]
            instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool or {EMOJI["masterball"]} _only_ if you're going to use a masterball (at which point you'll be removed from the queue).

            When you are done raiding, you **must** leave the raid by removing your {EMOJI["pokeball"]} reaction or by typing `.leave`. Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''

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

        # note: previously wrapped with self.lock:
        self.listing_message = await self.raid.listing_channel.send('', embed=e)

        for reaction in reactions:
            await self.listing_message.add_reaction(reaction.strip('<>'))

    async def make_thanks_post(self):
        profile = await self.bot.trainers.get_wf_profile(self.host_id)
        games = []
        if '0' in profile['games'] and 'name' in profile['games']['0'] and profile['games']['0']['name']:
            games.append([f"{EMOJI['sword']} **IGN**", profile['games']['0']['name']])

        if '1' in profile['games'] and 'name' in profile['games']['1'] and profile['games']['1']['name']:
            games.append([f"{EMOJI['shield']} **IGN**", profile['games']['1']['name']])

        description = f'''✨ **Raid Host Complete!**

_This raid was hosted by <@{self.host_id}>_

To thank them, react with a 💙 ! If you managed to catch one, add in a {EMOJI['pokeball']} !'''
        if self.desc:
            description += f'\n\n_{enquote(self.desc)}_'
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

        thanks_message = await self.raid.thanks_channel.send('', embed=e)
        for reaction in ['💙', EMOJI['pokeball']]:
            await thanks_message.add_reaction(reaction.strip('<>'))

    def make_queue_embed(self, mentions=True, cmd=''):

        sections = []
        lines = []

        if not self.ffa:
            if self.group:
                group_text = ' '.join([f'<@{t[1]}>' if mentions else self.member_name(t[1]) for t in self.group])
                sections.append(f'**Current Round**\n{group_text}')

            next_up, wraparound = self.pool.get_next(3, advance=False)
            group_text = ' '.join([f'<@{t[1]}>' if mentions else self.member_name(t[1]) for t in next_up])
            sections.append(f'**Next Round**\n{group_text}')

            lines = [f"{EMOJI['masterball']} " + (f"<@{uid}>" if mentions else self.member_name(uid)) for uid in
                     self.pool.mb]
        for i, uid in enumerate(self.pool.q):
            if not self.ffa and i == self.pool.i:
                lines.append(f"{EMOJI['join']} _we are here_")
            lines.append(f"`{i + 1: >2}` " + (f"<@{uid}>" if mentions else self.member_name(uid)))

        title = 'Active Raiders' if self.ffa else 'Queue'
        lines = '\n'.join(lines)
        sections.append(f'**{title}**\n{lines}')
        description = f'\n{FIELD_BREAK}'.join(sections)

        if len(description) > 2000:
            description = description[0:1997] + '...'

        # if cmd == 'q' or cmd == 'queue':
        #     description += f'\n{FIELD_BREAK}_Use `.qtext` if names load improperly_'

        footer = ''
        if cmd == 'queue':
            footer = '.q for short'
        elif cmd == 'qtext':
            footer = '.qt for short'

        e = discord.Embed(title='', description=description).set_footer(text=footer)
        return e

    '''
    rounds
    '''

    async def round_command(self, ctx, arg):

        async with self.lock:
            if self.closed or not self.channel:
                return

            # todo max rounds

            if ctx.channel != self.channel:
                return await send_message(ctx, f'Please initialize rounds in the actual raid channel.', error=True)

            if self.ffa:
                return await send_message(ctx, f'Rounds are disabled in FFA raids. The host runs it as they please.',
                                          error=True)

            code = None
            if arg:
                m = re.search(r'\d\d\d\d', arg)
                if m:
                    code = m.group(0)
            elif self.code:
                code = self.code
            if not code:
                return await send_message(ctx, f'Please choose a valid 4-digit code in the form `.round 1234`. You can re-use this code for subsequent rounds by just typing `.round`', error=True)

            if arg and self.private:
                await ctx.message.delete()

            self.code = code
            await self.new_round(ctx)

    async def new_round(self, ctx):

        size = self.pool.size()
        if size < 3:
            return await send_message(ctx, f'There are currently **{size}** participants, but You need at least **3** to start a raid.', error=True)

        self.round += 1
        self.group, wraparound = self.pool.get_next(3, advance=True)

        queue_text = ''
        if wraparound:
            queue_text = f"{DBL_BREAK}:recycle: Everyone in the `.queue` has now had a turn! We'll be starting from the beginning again."

        announcer = random.choice(ANNOUNCE_EMOJI)
        title = f'{announcer} 📣 Round {self.round} Start!'

        if self.private:
            code_text = f'''The code is hidden by the host! I've DM'd it to the group, but you can also type `.code` to see it (but please don't share it).'''
        else:
            code_text = f'The code to join is **{self.code}**!'

        description = f'''{code_text} Do **not** join unless you have been named below!{DBL_BREAK}If a trainer is AFK, the host may choose to:
`.skip @user` to skip and replace someone in the current round
`.remove @user` to remove (and skip) a user from this raid (they **cannot** rejoin!)
`.block @user` to remove (and skip) a user from **all** of your raids{queue_text}{FIELD_BREAK}'''
        e = discord.Embed(title=title, description=description)  # .set_footer(text='🐑 wooloo.farm')

        mention = f'<@{self.host_id}>'
        profile = await self.bot.trainers.get_wf_profile(self.host_id)
        profile_info = fc_as_text(profile)
        icon = '👑'
        raider_text = f'{icon} {mention}\n{profile_info}{FIELD_BREAK}'
        e.add_field(name='Host', value=raider_text, inline=False)

        mentions = []
        for i, raider in enumerate(self.group):
            join_type, raider_id = raider
            if self.private:
                user = self.bot.get_user(raider_id)
                if user:
                    await user.send(f'''**{self.code}** is the private code for `{self.raid_name}` - it's your turn! But keep in mind you may be skipped, so check on the channel as well.''')

            mention = f'<@{raider_id}>'
            mentions.append(mention)
            profile = await self.bot.trainers.get_wf_profile(raider_id, ctx)
            profile_info = fc_as_text(profile)
            icon = EMOJI['masterball'] if join_type == 'mb' else EMOJI['pokeball']
            raider_text = f'{icon} {mention}\n{profile_info}{FIELD_BREAK}'

            # if i < len(self.group) - 1:
            #     raider_text += FIELD_BREAK

            e.add_field(name=str(i + 1), value=raider_text, inline=False)

        next_up, wraparound = self.pool.get_next(3, advance=False)
        group_text = '🕑 ' + ' '.join([f'<@{t[1]}>' for t in next_up])
        e.add_field(name='Next Round', value=group_text, inline=False)

        try:
            await self.last_round_message.unpin()
        except Exception:
            pass

        self.last_round_message = await ctx.send(' '.join(mentions), embed=e)
        await self.last_round_message.pin()


    '''
    joins/leaves
    '''

    async def user_join(self, user, join_type, payload):

        async with self.lock:
            uid = user.id
            if uid == self.host_id:
                return

            member = self.guild.get_member(uid)
            if not member:
                return

            can_raid, err = await self.bot.trainers.can_raid(member, self.host_id)
            if not can_raid:
                msg = make_error_msg(err, uid)
                await member.send(msg)
                await self.bot.misc.remove_raw_reaction(payload, user)
                return

            # todo blocklist

            if self.closed:
                return

            if uid in self.pool.kicked:
                return await member.send(f"Oh no! You were kicked from this raid and cannot rejoin. {EMOJI['flop']}")

            if self.locked:
                await self.bot.misc.remove_raw_reaction(payload, user)
                return await member.send(f"This raid is **locked** and not accepting new joins, but the host may choose to unlock it. {EMOJI['flop']}")

            if self.pool.size() >= self.max_joins:
                await self.bot.misc.remove_raw_reaction(payload, user)
                return await member.send(
                    f"Unfortunately, that raid is full! Try another one or wait a little bit and check back.")

            if uid in self.pool.used_mb:
                await self.bot.misc.remove_raw_reaction(payload, user)
                return await member.send(
                    f"You've already joined this raid as a masterball user (which had priority), so you're out of the raid now. It does not matter if you \"missed\" and did not use your masterball.")

            if join_type == 'mb':
                # if uid in self.pool.used_mb:
                #     return await member.send(f"You've already joined this raid as a masterball user (which gets priority!), so you cannot do so again. It does not matter if you \"missed\" and did not use your masterball. You may re-join as a regular user though, with {EMOJI['pokeball']}!")

                if uid in self.pool.mb:
                    return

                # if uid in self.pool.q:
                #     join_type = 'mb+'

                self.pool.remove(uid)
                self.pool.used_mb.append(uid)
                self.pool.mb.append(uid)

                await self.send_join_msg(member, join_type)
                await self.channel.set_permissions(member, send_messages=True, add_reactions=True)

                if uid not in self.pool.join_history:
                    self.pool.join_history.append(uid)

                if self.channel_emoji != LOCKED_EMOJI and self.pool.size() >= self.max_joins:
                    self.channel_emoji = LOCKED_EMOJI
                    await self.channel.edit(name=f'{LOCKED_EMOJI}{self.channel_name[1:]}')

            elif join_type == 'pb':
                if uid in self.pool.q or uid in self.pool.mb:
                    await self.bot.misc.remove_raw_reaction(payload, user)
                    return

                self.pool.q.append(uid)

                await self.send_join_msg(member, join_type)
                await self.channel.set_permissions(member, send_messages=True, add_reactions=True)

                if uid not in self.pool.join_history:
                    self.pool.join_history.append(uid)

                if self.channel_emoji != LOCKED_EMOJI and self.pool.size() >= self.max_joins:
                    self.channel_emoji = LOCKED_EMOJI
                    await self.channel.edit(name=f'{LOCKED_EMOJI}{self.channel_name[1:]}')



    async def user_leave(self, user, remove_reaction=False):

        async with self.lock:
            if self.closed:
                return
            uid = user.id
            removed = self.pool.remove(uid)
            if not removed:
                return
            member = self.guild.get_member(uid)
            if not member:
                return
            await self.channel.set_permissions(member, overwrite=None)
            text = ', but you can rejoin at any time.' if uid not in self.pool.used_mb else '. You won\'t be able to rejoin, as you used a masterball.'

            profile = await self.bot.trainers.get_wf_profile(self.host_id)
            profile_info = fc_as_text(profile)
            raider_text = f'👑 <@{self.host_id}>\n{profile_info}{FIELD_BREAK}'
            e = discord.Embed(title='Host Details', description=raider_text)
            await member.send(
                f'You have left the `{self.raid_name}` raid{text} You **have** to remove the host from your friend list now, even if you plan to continue raiding with them later. Otherwise, you may be blocked or banned from raiding altogether.',
                embed=e)

            if remove_reaction:
                try:
                    await self.listing_message.remove_reaction(EMOJI['pokeball'], user)
                    await self.listing_message.remove_reaction(EMOJI['masterball'], user)
                except Exception as e:
                    pass

            if self.channel_emoji == LOCKED_EMOJI and self.pool.size() < self.max_joins:
                self.channel_emoji = RAID_EMOJI
                await self.channel.edit(name=f'{RAID_EMOJI}{self.channel_name[1:]}')

    async def send_join_msg(self, member, join_type):

        profile = await self.bot.trainers.get_wf_profile(member.id)
        profile_info = fc_as_text(profile)

        pls_read = f'''\nPlease read <#665681669860098073> and the **pinned messages** or you will probably end up **banned** without knowing why. _We will not be undoing bans if you didn't read them._'''

        if join_type == 'pb':
            if member.id not in self.pool.join_history:
                await self.raid.log_channel.send(f"{show_member_for_log(member)} has joined raid {self.raid_name}.\n{profile_info}")
                await self.channel.send(
                    f"{FIELD_BREAK}{EMOJI['join']} <@{member.id}> has joined the raid! {pls_read}\n{profile_info}{FIELD_BREAK}")
            else:
                await self.channel.send(f"{EMOJI['join']} <@{member.id}> has rejoined the raid!")

        elif join_type == 'mb':
            if member.id not in self.pool.join_history:
                await self.raid.log_channel.send(f"{show_member_for_log(member)} has joined raid {self.raid_name} **with a master ball**.\n{profile_info}")
                await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has joined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to block them. {pls_read}\n{profile_info}{FIELD_BREAK}")
            else:
                await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}")

        # elif join_type == 'mb+':
        #     return await self.channel.send(f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}")


    '''
    managemnt
    '''

    async def skip(self, member, ctx):

        async with self.lock:
            uids = [t[1] for t in self.group]
            try:
                to_remove = uids.index(member.id)
            except ValueError:
                return await ctx.send(
                    f'There\'s no need to skip {str(member)} as they aren\'t in the current round. Type `.q` to see it.')

            removed = self.group[to_remove]
            del self.group[to_remove]
            replacement, wraparound = self.pool.get_next(advance=True)
            self.group += replacement

            if self.private:
                user = self.bot.get_user(replacement[0][1])
                if user:
                    await user.send( f'''**{self.code}** is the private code for `{self.raid_name}` - it's your turn (as a replacement)! But keep in mind you may be skipped, so check on the channel as well.''')

        msg = f"<@{removed[1]}> has been skipped and **should not join.** <@{replacement[0][1]}> will take <@{removed[1]}>'s place in this round."
        if wraparound:
            msg += " :recycle: Everyone in the `.queue` has now had a turn! We'll be starting from the beginning again."

        return await ctx.send(msg)

    async def kick(self, member, ctx):

        async with self.lock:
            await self.channel.set_permissions(member, read_messages=False)
            uid = member.id

            self.pool.remove(uid)
            self.pool.kicked.append(uid)

        if uid in self.pool.join_history:
            await member.send(
                f"Oh no! You were removed from the raid `{self.raid_name}` and cannot rejoin. {EMOJI['flop']}")
        await ctx.send(
            f"<@{uid}> has been removed from this raid. They will not be able to see this channel or rejoin. {EMOJI['flop']}")

        await self.raid.log_channel.send(
            f'<@{self.host_id}> (ID: {self.host_id}) (or an admin) **kicked** {show_member_for_log(member)} in `{self.channel_name}`')
        await self.skip(member, ctx)

    async def block(self, member, ctx):
        pass

    async def end(self, immediately=False):
        async with self.lock:
            was_closed = self.closed
            self.closed = True

        if was_closed:
            if immediately:
                await self.archive()
            return

        await self.channel.trigger_typing()
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, add_reactions=True),
        }
        self.channel_emoji = CLOSED_EMOJI
        await self.channel.edit(name=f'{CLOSED_EMOJI}{self.channel_name[1:]}', overwrites=overwrites)

        if not immediately:
            if not immediately and (self.round >= 3 or self.ffa):
                msg = f'''✨ **Raid Host Complete!**

Thank you for raiding, this channel is now closed!

To thank <@{self.host_id}> for their hard work with hosting, head to <#{self.raid.thanks_channel.id}> and react with a 💙 !
If you managed to catch one, add in a {EMOJI['pokeball']} !

_This channel will automatically delete in a little while_ {EMOJI['flop']}'''

                await self.make_thanks_post()
            else:
                msg = f'''✨ **Raid Host Complete!**

Thank you for raiding, this channel is now closed! We won't make a "thanks" post since it was such a short one (in case it was a mistake or so).

_This channel will automatically delete in a little while_ {EMOJI['flop']}'''
            await self.channel.send(msg)

        await self.listing_message.delete()
        await self.send_host_cleanup_message()
        await self.raid.save_raids_to_db()
        if not immediately:
            await asyncio.sleep(60 * 10)
        await self.archive()

    async def archive(self):
        print(f'[Raid Archive] Archiving {self}')

        async with self.lock:
            deleted = self.raid.raids.pop(self.host_id, None)
            if deleted:
                self.destroy()
                await self.channel.edit(sync_permissions=True, category=self.raid.archive, position=0)
                await self.raid.save_raids_to_db()
                # workaround for discord sync unreliable
                await asyncio.sleep(10)
                await self.channel.edit(sync_permissions=True)

    async def send_host_cleanup_message(self):
        lines = []
        for i, uid in enumerate(self.pool.join_history):
            profile = await self.bot.trainers.get_wf_profile(uid)

            fc = f"SW-{profile['friend_code']}"
            switch = profile['switch_name']
            text = f'''🗺️ FC: `{fc}` / {EMOJI['discord']}  **{self.member_name(uid)}** / 🎮 Switch Name: **{switch}** / {ign_as_text(profile, ' / ')}'''
            lines.append(f"`{i + 1: >2}` {text}\n")

        # lines = '\n'.join(lines)
        messages = []
        msg = f'Thank you for hosting!! They _should_ have removed you themselves, but if not here\'s a list of participants to help you clean up your friend list:\n\n'
        for line in lines:
            if len(msg) + len(line) < 2000:
                msg += line
            else:
                messages.append(msg)
                msg = line

        messages.append(msg)

        # i = 0
        # messages = []
        # while i < 3 and text:
        #     messages.append(text[:2000])
        #     text = text[2000:]
        #     i += 1

        host = self.bot.get_user(self.host_id)
        if host:
            for msg in messages:
                await host.send(msg)

    def member_name(self, uid):
        return str(self.guild.get_member(uid))


class Raid(commands.Cog):
    def __init__(self, bot):
        # self.db = db
        self.bot = bot
        self.cache = {}
        self.db = sqlite3.connect('raid.db')

        self.category = None
        self.archive = None
        self.guild = None
        self.listing_channel = None
        self.thanks_channel = None
        self.log_channel = None
        self.breakroom = None
        self.creating_enabled = True
        self.loaded = False

        self.raids = {}

        # debug
        self.task_n = 0

        if self.bot.is_ready():
            self.bot.loop.create_task(self.on_load())

    def cog_unload(self):
        print('[Unload] Raid Cog Teardown')
        self.bot.loop.create_task(self.save_raids_to_db())

    async def on_load(self):
        self.loaded = False

        bound = self.bind_to_categories()
        # if bound:
        #     await self.clear_channels_dirty()

        print('[DB] Init')
        self.make_db()
        await self.load_raids_from_db()
        self.save_interval.start()
        self.loaded = True

    def make_db(self):
        c = self.db.cursor()
        c.execute('''create table if not exists raids (
            host_id integer not null,
            guild_id integer not null,
            raid_name text not null,
            ffa integer not null,
            private integer not null,
            no_mb integer not null,
            channel_id integer not null,
            channel_name text not null,
            desc text,
            listing_msg_id integer not null,
            last_round_msg_id integer,
            round integer not null,
            max_joins integer not null,
            pool text,
            raid_group text,
            start_time integer not null,
            time_saved integer,
            code text,
            locked integer not null,
            closed integer not null,
            primary key(host_id)
        )''')
        c.execute('''create table if not exists raid_history (
            host_id integer not null,
            guild_id integer not null,
            raid_name text not null,
            ffa integer not null,
            private integer not null,
            no_mb integer not null,
            channel_id integer not null,
            channel_name text not null,
            desc text,
            listing_msg_id integer not null,
            last_round_msg_id integer,
            round integer not null,
            max_joins integer not null,
            pool text,
            raid_group text,
            start_time integer not null,
            time_saved integer,
            code text,
            locked integer not null,
            closed integer not null
        )''')
        self.db.commit()
        c.close()

    async def load_raids_from_db(self):
        # print(f'[DB] Attempting to load raids...')
        if self.raids:
            print('[DB ERROR] `self.raids` already exists, should be empty')

        t = time.time()
        c = self.db.cursor()
        c.execute('select host_id, guild_id, raid_name, ffa, private, no_mb, channel_id, channel_name, desc, listing_msg_id, last_round_msg_id, round, max_joins, pool, raid_group, start_time, time_saved, code, locked, closed from raids')
        for r in map(RaidRecord._make, c.fetchall()):
            raid = HostedRaid(self.bot, self, self.guild, r.host_id)
            loaded, err = await raid.load_from_record(r)
            print('raid:', raid)
            print(await raid.as_record())
            if not loaded:
                print(f'Did not succesfully load {r.raid_name}, error: {err}')
                if raid.channel and not raid.closed:
                    await raid.channel.send(f'❌ During a bot restart, this raid failed to load and will have to be remade. This is likely a Discord issue, but let <@232650437617123328> know. The following error occured:\n\n```{err}```')
            else:
                self.raids[raid.host_id] = raid
                print(f'Succesfully loaded {r.raid_name}')
                if raid.closed:
                    await raid.archive()
                    print('...and immediately archived it!')
                else:
                    t = int(time.time())
                    delta = t - raid.time_saved
                    if delta < 60:
                        ago = f'{delta} second(s)'
                    else:
                        ago = f'{delta//60} minute(s)'

                    await raid.channel.send(f'🔄 Bot Reloaded! Restored raid data from ~{ago} ago.')

        c.close()
        print(f'[DB] Loaded {len(self.raids)} raids from database. Took {time.time() - t:.3f} seconds')

    async def save_raids_to_db(self):
        # print(f'[DB] Attempting to save raids...')
        # t = time.time()
        print('[DB] Starting saving raids to DB.')
        to_serialize = [await raid.as_record() for raid in self.raids.values()]
        c = self.db.cursor()
        c.execute('delete from raids')
        for record, should_serialize in to_serialize:
            if should_serialize:
                print(f'[DB] Saving record {record} to database')
                try:
                    c.execute('insert into raids values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', record)
                except sqlite3.Error as e:
                    print(f'[SQL Insert Error] Could not insert raid {record.raid_name}! Error: {type(e).__name__}, {e}')
            else:
                print(f'[DB] Skipped saving record {record}')

        self.db.commit()
        c.close()
        print('[DB] Save complete.')

    @commands.Cog.listener()
    async def on_ready(self):
        await self.on_load()

    @tasks.loop(minutes=3.0)
    async def save_interval(self):
        print('[Task] Periodic Save')
        await self.save_raids_to_db()

    # @commands.Cog.listener()
    # async def on_reaction_add(self, reaction, user):
    #     await self.reaction_action('add', reaction, user)
    #
    # @commands.Cog.listener()
    # async def on_reaction_remove(self, reaction, user):
    #     await self.reaction_action('remove', reaction, user)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if self.loaded:
            await self.reaction_action('add', payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if self.loaded:
            await self.reaction_action('remove', payload)

    async def reaction_action(self, action, payload):

        if not self.listing_channel:
            return

        if payload.user_id == self.bot.user.id:
            return

        if payload.channel_id != self.listing_channel.id:
            return

        user = self.bot.get_user(payload.user_id)
        if not user:
            return

        if str(payload.emoji) not in [EMOJI['pokeball'], EMOJI['masterball']]:
            await self.bot.misc.remove_raw_reaction(payload, user)
            return

        target_raid = None
        for host_id, raid in self.raids.items():
            if raid and raid.listing_message and raid.listing_message.id == payload.message_id:
                target_raid = raid
                break

        if not target_raid:
            return

        if target_raid.no_mb and str(payload.emoji) == EMOJI['masterball']:
            return

        if action == 'add':
            join_type = 'mb' if str(payload.emoji) == EMOJI['masterball'] else 'pb'
            return await target_raid.user_join(user, join_type, payload)

        if action == 'remove':
            return await target_raid.user_leave(user)

    # @commands.group(invoke_without_command=True)
    # async def raid(self, ctx, arg=None):
    #     pass
    #     # message = await send_message(ctx, 'Top Level Raid')

    '''
    host
    '''

    # @commands.has_role('raider')
    @commands.command()
    async def host(self, ctx, *, arg=None):

        if not self.creating_enabled and ctx.author.id != 232650437617123328:
            return await send_message(ctx,
                                      'Creating new raids is temporarily paused (probably pending a bot update, check the bot status channel).',
                                      error=True)

        if arg is None or 'help' in arg:
            msg = f'''{CREATE_HELP}

_Managing a Raid_
{HOST_COMMANDS}
'''
            return await send_message(ctx, msg)

        if len(self.raids) >= MAXRAIDS:
            return await send_message(ctx,
                                      f'Unfortunately, we already have the maximum number of **{MAXRAIDS}** raids being hosted.',
                                      error=True)

        uid = ctx.author.id
        if uid in self.raids:
            return await send_message(ctx, 'You are already configuring or hosting a raid.', error=True)

        max_joins = 30
        m = re.search(r'max=(\d*)', arg)
        if m:
            try:
                max_joins = int(m.group(1))
            except ValueError:
                return await send_message(ctx,
                                          'Invalid value for max raiders. Include `max=n` or leave it out for `max=30`',
                                          error=True)
            arg = arg.replace(m.group(0), '')

        desc = None
        m = re.search(r'[\"“‟”’❝❞＂‘‛❛❜](.*)[\"“‟”’❝❞＂‘‛❛❜]', arg, flags=re.DOTALL)
        if m:
            desc = m.group(1)
            arg = arg.replace(m.group(0), '')

        private = False
        if 'private' in arg:
            private = True
            arg = arg.replace('private', '')

        no_mb = False
        if 'no mb' in arg:
            no_mb = True
            arg = arg.replace('no mb', '')

        locked = False
        if 'locked' in arg:
            locked = True
            arg = arg.replace('locked', '')

        name = arg.strip()
        channel_name = f"{RAID_EMOJI}-{name.replace(' ', '-')}"[:100]
        channel_name = re.sub('[<>]', '', channel_name)

        can_host, err = await self.bot.trainers.can_host(ctx.author, ctx)
        if not can_host:
            msg = make_error_msg(err, uid)
            return await send_message(ctx, msg, error=True)

        self.raids[uid] = HostedRaid(self.bot, self, self.guild, ctx.author.id)
        print('[Raid Creation]', self.raids)
        await self.raids[uid].send_confirm_prompt(ctx, name, channel_name, desc, max_joins, private, no_mb, locked)

    @host.error
    async def host_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send('oopsie poopsie')
        else:
            print_error(ctx, error)

    async def cancel_before_confirm(self, raid, channel, msg=''):
        print(f'[Raid Cancel] {self} was cancelled before it was confirmed.')
        del self.raids[raid.host_id]
        raid.destroy()
        await channel.send(f"<@{raid.host_id}> {msg}Your raid was cancelled. {EMOJI['flop']}")

    @commands.command()
    async def round(self, ctx, arg=None):
        uid = ctx.author.id
        if uid in self.raids:
            return await self.raids[uid].round_command(ctx, arg)

        return await send_message(ctx, RAID_NOT_FOUND, error=True)

    @commands.command(aliases=['end'])
    async def close(self, ctx, arg=''):
        uid = ctx.author.id
        admin = ctx.author.guild_permissions.administrator
        if uid in self.raids:
            if self.raids[uid].channel == ctx.channel:
                return await self.raids[uid].end(admin and ('immediately' in arg or 'now' in arg))

        if admin:
            for host_id, raid in self.raids.items():
                if raid and raid.channel == ctx.channel:
                    return await raid.end('immediately' in arg or 'now' in arg)

        return await send_message(ctx, RAID_NOT_FOUND, error=True)

    '''
    host moderation
    '''

    @commands.command(name='group')
    async def group_message(self, ctx, *, arg=None):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        if not arg:
            return await send_message(ctx, f'Type a message that you\'d like to relay to the current round\'s group.',
                                      error=True)

        raid = self.raids[uid]
        if not raid.group:
            return await send_message(ctx, 'No active group! Type `.round` to start one.', error=True)

        mentions = []
        for i, raider in enumerate(raid.group):
            join_type, raider_id = raider
            mention = f'<@{raider_id}>'
            mentions.append(mention)

        msg = f"{' '.join(mentions)} 📣 Message from host:\n{enquote(arg)}"
        await ctx.send(msg)

    @commands.command()
    async def skip(self, ctx, *, arg=None):
        await self.host_moderation(ctx, 'skip', arg)

    @commands.command(aliases=['remove'])
    async def kick(self, ctx, *, arg=None):
        await self.host_moderation(ctx, 'remove', arg)

    @commands.command()
    async def block(self, ctx, *, arg=None):
        await self.host_moderation(ctx, 'block', arg)

    async def host_moderation(self, ctx, action, arg):
        if not arg:
            return

        target_raid = None
        for host_id, raid in self.raids.items():
            if raid and raid.channel == ctx.channel:
                is_host = ctx.author.id == host_id
                admin = ctx.author.guild_permissions.administrator

                if not admin and not is_host:
                    return await send_message(ctx, 'Host or admin only. Use `.q` instead.', error=True)
                target_raid = raid
                break

        if not target_raid:
            return await send_message(ctx, RAID_NOT_FOUND, error=True)

        match = idPattern.search(arg)
        if not match:
            return await send_message(ctx, f'Please tag the member you\'d like to {action}', error=True)

        mention_id = int(match.group(1))
        member = ctx.message.guild.get_member(mention_id)
        if not member:
            return await send_message(ctx, f'Could not remove user! Please tag the mods to manually intervene.',
                                      error=True)

        if member == self.bot.user:
            return

        if action == 'skip':
            return await target_raid.skip(member, ctx)

        if action == 'remove':
            return await target_raid.kick(member, ctx)

        if action == 'block':
            await ctx.send(f'`.block` is not yet implemented, but for now we will attempt to `.remove` the user.')
            return await target_raid.kick(member, ctx)

    @commands.command()
    async def max(self, ctx, *, arg=''):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        raid = self.raids[uid]
        if raid.channel != ctx.channel:
            return await send_message(ctx, f'You may only adjust this in your active raid channel.', error=True)

        if not arg:
            return await send_message(ctx, f'Please enter a number, i.e. `.max 18`', error=True)

        try:
            n = int(arg)
        except ValueError:
            return await send_message(ctx, f'Please enter a number, i.e. `.max 18`', error=True)

        n = clamp(n, 3, 50 if raid.ffa else 30)
        size = raid.pool.size()
        if n < size:
            return await send_message(ctx, f'You cannot go lower than the current pool size ({size}).', error=True)

        if raid.max_joins == n:
            return await send_message(ctx, f'That\'s... already the max.', error=True)

        # todo lock
        verb = 'increased' if raid.max_joins < n else 'decreased'
        raid.max_joins = n
        await ctx.send(f'Max participants {verb} to **{n}**.')

        if raid.channel_emoji != LOCKED_EMOJI and raid.pool.size() >= raid.max_joins:
            raid.channel_emoji = LOCKED_EMOJI
            await raid.channel.edit(name=f'{LOCKED_EMOJI}{raid.channel_name[1:]}')

        elif raid.channel_emoji == LOCKED_EMOJI and raid.pool.size() < raid.max_joins:
            raid.channel_emoji = RAID_EMOJI
            await raid.channel.edit(name=f'{RAID_EMOJI}{raid.channel_name[1:]}')

    @commands.command()
    async def lock(self, ctx):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        raid = self.raids[uid]
        if raid.channel != ctx.channel:
            return await send_message(ctx, f'You may only do this in your active raid channel.', error=True)

        raid.locked = not raid.locked

        if raid.locked:
            msg = 'Raid is now **locked**, the raid will continue but no new raiders will be able to join until you type `.lock` again.'
        else:
            msg = 'Raid is now **unlocked**, new raiders can join again (if there is room).'

        icon = LOCKED_EMOJI if raid.locked else RAID_EMOJI
        raid.channel_emoji = icon
        await raid.channel.edit(name=f'{icon}{raid.channel_name[1:]}')
        await ctx.send(msg)

    @commands.command()
    async def private(self, ctx):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        raid = self.raids[uid]
        if raid.channel != ctx.channel:
            return await send_message(ctx, f'You may only do this in your active raid channel.', error=True)

        raid.private = not raid.private

        if raid.private:
            raid.code = None
            msg = 'Raid is now **private**, which means the `.code` will be hidden. I\'ve removed the old one, so please set a secret one in the form `.code 1234`. If you\'ve pinned it, you might want to `.unpin` it. Type `.private` again to toggle.'
        else:
            msg = f'''Raid is no longer private, which means the code is public again (it's **{raid.code}**). Type `.private` again to toggle.'''

        await ctx.send(msg)

    '''
    pins
    '''

    @commands.command()
    async def pin(self, ctx):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        raid = self.raids[uid]
        if raid.channel != ctx.channel:
            return await send_message(ctx, f'You may only pin channels in your active raid channel.', error=True)

        if len(raid.pins) >= 10:
            return await send_message(ctx,
                                      f'For now, you can only `.pin` a total of 10 times (even after `.unpin`ning them). This will be adjusted in the future.',
                                      error=True)

        last_msg = await ctx.channel.history().find(lambda m: m.id != ctx.message.id and m.author == ctx.author)
        if not last_msg:
            return await send_message(ctx, f'No message found by you in recent history (~50 messages).', error=True)

        raid.pins.append(last_msg)
        await last_msg.pin()

        n = len(raid.pins)
        await ctx.send(f'Message #**{n}** pinned! To remove it, type `.unpin {n}`.')

    @commands.command()
    async def unpin(self, ctx, *, arg=''):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        raid = self.raids[uid]
        if raid.channel != ctx.channel:
            return await send_message(ctx, f'You may only unpin channels in your active raid channel.', error=True)

        if not arg:
            return await send_message(ctx, f'Invalid pin! You must include the number, e.g. `.unpin 3` ', error=True)

        try:
            n = int(arg) - 1
            if not (0 <= n < len(raid.pins)):
                raise ValueError
        except ValueError:
            return await send_message(ctx, f'Invalid pin! You must include the number, e.g. `.unpin 3` ', error=True)

        pinned_msg = raid.pins[n]
        if not pinned_msg:
            return await send_message(ctx, f'That message no longer exists and could not be unpinned.', error=True)

        await pinned_msg.unpin()
        raid.pins[n] = None

        await ctx.send(f'Message #**{n + 1}** unpinned! This cannot presently be undone.')

    '''
    misc
    '''

    async def view_queue(self, ctx, text=False):
        uid = ctx.author.id
        if uid in self.raids:
            if self.raids[uid].channel == ctx.channel:
                e = self.raids[uid].make_queue_embed(mentions=not text, cmd=ctx.invoked_with)
                return await ctx.send('', embed=e)

        for host_id, raid in self.raids.items():
            if raid.channel == ctx.channel:
                admin = ctx.author.guild_permissions.administrator
                if admin:
                    e = raid.make_queue_embed(mentions=not text, cmd=ctx.invoked_with)
                    return await ctx.send('', embed=e)
                await ctx.message.add_reaction('✅')
                e = raid.make_queue_embed(mentions=False, cmd=ctx.invoked_with)
                return await ctx.author.send(raid.raid_name, embed=e)\

        return await send_message(ctx, RAID_NOT_FOUND, error=True)

    @commands.command(aliases=['q'])
    async def queue(self, ctx, arg=''):
        return await self.view_queue(ctx, False)

    @commands.command(name='qtext', aliases=['qt'])
    async def queue_text(self, ctx, arg=''):
        return await self.view_queue(ctx, True)

    @commands.command(name='qfc', aliases=['queuefc'])
    async def queue_fc(self, ctx, arg=''):
        for host_id, raid in self.raids.items():
            if raid and raid.channel == ctx.channel:
                is_host = ctx.author.id == host_id
                admin = ctx.author.guild_permissions.administrator

                if not admin and not is_host:
                    return await send_message(ctx, 'Host or admin only. Use `.q` instead.', error=True)

                lines = []
                for i, uid in enumerate(raid.pool.q):
                    profile = await self.bot.trainers.get_wf_profile(uid)

                    fc = f"SW-{profile['friend_code']}"
                    switch = profile['switch_name']
                    text = f'''🗺️ FC: `{fc}` / {EMOJI['discord']}  **{raid.member_name(uid)}** / 🎮 Switch Name: **{switch}** / {ign_as_text(profile, ' / ')}'''
                    lines.append(f"`{i + 1: >2}` {text}\n")

                messages = []
                msg = f'**Active Raider Profiles**\n\n'
                for line in lines:
                    if len(msg) + len(line) < 2000:
                        msg += line
                    else:
                        messages.append(msg)
                        msg = line

                messages.append(msg)
                for msg in messages:
                    await ctx.send(msg)

                return

        return await send_message(ctx, RAID_NOT_FOUND, error=True)

    @commands.command(aliases=['catch'])
    async def caught(self, ctx, arg=None):
        description = f' 🎊 ✨ 🍰   {ctx.author.mention} has **caught** the Pokémon!   🍰 ✨ 🎊 '
        color = random.choice(TYPE_COLORS)
        e = discord.Embed(description=description, color=color) \
            .set_author(name=f'Caught!', icon_url=pokeballUrl)

        caught_msg = await ctx.send('', embed=e)
        for reaction in [':lovehonk:656861100762988567', EMOJI['pokeball']]:
            await caught_msg.add_reaction(reaction.strip('<>'))

    @commands.command()
    async def code(self, ctx, arg=None):
        for host_id, raid in self.raids.items():
            if raid and raid.channel == ctx.channel:
                is_host = ctx.author.id == host_id

                if not arg or not is_host:
                    if not raid.code:
                        if is_host:
                            return await send_message(ctx, '''You haven't set a code yet. Please choose a valid 4-digit code in the form `.code 1234`''', error=True)
                        else:
                            return await send_message(ctx, 'The code hasn\'t been set by the host.', error=True)

                    if not is_host:
                        msg = f'The code for `{raid.raid_name}` is currently **{raid.code}**. The host may change this later on, keep an eye out.'
                        if raid.private:
                            msg += ' Since this is a private raid, please do not share the code openly (to hide it from lurkers).'
                        # await ctx.message.add_reaction('✅')
                        await ctx.message.delete()
                        return await ctx.author.send(msg)

                error = False
                code = None
                if arg:
                    m = re.search(r'\d\d\d\d', arg)
                    if m:
                        code = m.group(0)
                    else:
                        error = True

                if not code:
                    msg = ''
                    if raid.code:
                        msg = f'The code is currently set to **{raid.code}**, but you can change it with `.code 1234` using any valid 4-digit number.'
                    else:
                        msg = f'''You haven't set a code yet. Please choose a valid 4-digit code in the form `.code 1234`'''

                    if raid.private:
                        await ctx.message.add_reaction(ICON_CLOSE if error else '✅')
                        return await ctx.author.send(msg)

                    return await send_message(ctx, msg, error=True)

                raid.code = code
                if raid.private:
                    await ctx.message.delete()
                    msg = '''The code has been **updated**. Participants will have to get the new one by typing `.code` when it's their turn. I'll also send a DM if there's a queue. Since this is a private raid, please do not share the code openly (to hide it from lurkers).'''
                else:
                    msg = f'''The code has been updated to **{raid.code}**.'''

                return await ctx.send(msg)

        return await send_message(ctx, RAID_NOT_FOUND, error=True)

    @commands.command()
    async def leave(self, ctx, arg=None):
        for host_id, raid in self.raids.items():
            if raid and raid.channel == ctx.channel:
                user = self.bot.get_user(ctx.author.id)
                if not user:
                    print(f'[ERROR] Could not `get_user` for `.leave` with id {ctx.author.id}')
                    return
                await ctx.message.add_reaction('✅')
                return await raid.user_leave(user, True)

        return await send_message(ctx, RAID_NOT_FOUND, error=True)

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
    @commands.command(name='clearall', aliases=['ca'])
    async def clear_all(self, ctx, arg=None):
        await self.clear_channels_dirty()

    @checks.is_jacob()
    @commands.command()
    async def pause(self, ctx, arg=None):
        self.creating_enabled = not self.creating_enabled
        await ctx.send(f'`creating_enabled = {self.creating_enabled}`')

    @checks.is_jacob()
    @commands.command(name='dbsave')
    async def db_save(self, ctx, arg=None):
        await self.save_raids_to_db()
        await ctx.send(f'Finished.')

    @checks.is_jacob()
    @commands.command(name='dbload')
    async def db_load(self, ctx):
        await self.load_raids_from_db()
        await ctx.send(f'Finished.')

    @commands.has_permissions(administrator=True)
    @commands.command()
    async def announce(self, ctx, *, arg):

        if not self.category:
            return

        emoji = []
        if 'votes=' in arg:
            arg, votes = arg.split('votes=')
            emoji = votes.split(',')

        url = None
        m = re.search(r'http[\w\-._~:/?#[\]@!$&\'()*+,;=]+', arg, flags=re.DOTALL)
        if m:
            url = m.group(0)
            if 'png' in url or 'gif' in url or 'jpg' in url or 'jpeg' in url:
                arg = arg.replace(url, '')
            else:
                url = None
        color = random.choice(TYPE_COLORS)
        e = discord.Embed(title='Bot Announcement!', description=f'''{EMOJI['honk']} {arg}''', color=color)
        if url:
            e.set_image(url=url)
        for channel in self.category.text_channels:
            if channel.name.startswith(RAID_EMOJI) or channel.name.startswith(LOCKED_EMOJI):
                msg = await channel.send('', embed=e)
                for reaction in emoji:
                    await msg.add_reaction(reaction.strip('<> '))
        if self.breakroom:
            msg = await self.breakroom.send('', embed=e)
            for reaction in emoji:
                await msg.add_reaction(reaction.strip('<> '))
        await ctx.send('Sent!')

    @commands.has_permissions(administrator=True)
    @commands.command()
    async def raidsay(self, ctx, *, arg):

        if not self.category:
            return

        msg = arg
        for channel in self.category.text_channels:
            if channel.name.startswith(RAID_EMOJI) or channel.name.startswith(LOCKED_EMOJI):
                await channel.send(msg)
        if self.breakroom:
            await self.breakroom.send(msg)
        await ctx.send('Sent!')

    @commands.has_permissions(administrator=True)
    @commands.command(aliases=['cl'])
    async def clear(self, ctx):
        if self.archive:
            for channel in self.archive.text_channels:
                if channel.name.startswith(RAID_EMOJI) or channel.name.startswith(LOCKED_EMOJI) or channel.name.startswith(CLOSED_EMOJI):
                    await channel.delete()

    async def clear_channels_dirty(self):
        if self.category:
            if self.listing_channel:
                await self.listing_channel.purge(limit=100, check=lambda m: m.author == self.bot.user)

            for channel in self.category.text_channels:
                if channel.name.startswith(RAID_EMOJI) or channel.name.startswith(LOCKED_EMOJI) or channel.name.startswith(CLOSED_EMOJI):
                    await channel.edit(sync_permissions=True, category=self.archive, position=0)

    async def make_raid_channel(self, raid, channel_ctx):
        if self.category is None or self.guild is None:
            await channel_ctx.send(
                f"No category bound! jacob should write `.raid admin bind <category id>` {EMOJI['flop']}")
            return

        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, add_reactions=True),
            self.guild.get_member(raid.host_id): discord.PermissionOverwrite(send_messages=True, add_reactions=True)
        }

        # todo ban list

        topic = 'please read the pinned messages before raiding'

        channel_name = raid.channel_name
        if raid.locked:
            raid.channel_emoji = LOCKED_EMOJI
            channel_name = f'{LOCKED_EMOJI}{channel_name[1:]}'

        channel = await self.guild.create_text_channel(channel_name, overwrites=overwrites, category=self.category,
                                                       topic=topic)
        return channel

    def bind_to_categories(self):
        if not self.bot.is_ready():
            return False

        # raids_cid = 661468408856051733 # test
        # archive_cid = 666527061673771030 # test

        raids_cid = 661425972158922772  # live
        archive_cid = 652579764837679145  # live

        try:
            self.category = self.bot.get_channel(raids_cid)
            self.archive = self.bot.get_channel(archive_cid)
            self.guild = self.category.guild
            self.listing_channel = discord.utils.get(self.guild.text_channels, name='active-raids')
            self.thanks_channel = discord.utils.get(self.guild.text_channels, name='raid-thanks')
            self.log_channel = discord.utils.get(self.guild.text_channels, name='raid-log')
            self.breakroom = self.bot.get_channel(652367800912052244)
            print(f'Bound to {raids_cid}', self.category, self.guild, self.listing_channel)

        except AttributeError:
            print(f'Could not bind to {raids_cid}')
            return False

        return True


def setup(bot):
    raid = Raid(bot)
    bot.add_cog(raid)
    bot.raid = raid
