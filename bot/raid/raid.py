import asyncio
import json
import random
import re
import time

import discord

import texts

from common import clamp, send_message, pokeballUrl, TYPE_COLORS, DBL_BREAK, FIELD_BREAK, EMOJI, \
    ANNOUNCE_EMOJI, ICON_CLOSE, enquote
from trainers import ign_as_text, fc_as_text

from collections import namedtuple
from .pool import Pool
from .config import RAID_EMOJI, LOCKED_EMOJI, CLOSED_EMOJI, \
                    FLEXIBLE, FFA, QUEUE, \
                    MAX_RAIDS


RaidRecord = namedtuple('RaidRecord',
                        'host_id, guild_id, raid_name, mode, private, no_mb, channel_id, channel_name, desc, listing_msg_id, last_round_msg_id, round, max_joins, pool, raid_group, ups, start_time, time_saved, code, locked, closed')


def show_member_for_log(member):
    return f"<@{member.id}> ({member.name}#{member.discriminator}, ID: {member.id}, Nickname: {member.nick})"

class Raid(object):
    def __init__(self, bot, cog, guild, host_id):
        self.bot = bot
        self.cog = cog
        self.host_id = host_id
        self.guild = guild

        self.raid_name = None
        self.mode = FLEXIBLE
        self.private = False
        self.no_mb = False
        self.channel = None
        self.channel_name = None
        self.desc = None
        self.listing_message = None
        self.last_round_message = None
        self.pins = []
        self.echos = {}

        self.round = 0
        self.max_joins = 30
        self.pool = None
        self.group = []
        self.ups = []

        self.start_time = None
        self.time_saved = None
        self.code = None

        self.wfr_message = None

        self.locked = False
        self.confirmed = False
        self.closed = False

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
            can_save = self.wfr_message is None and self.confirmed and self.channel

            return RaidRecord(host_id=self.host_id,
                              guild_id=self.guild.id,
                              raid_name=self.raid_name,
                              mode=self.mode,
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
                              ups=json.dumps(self.ups),
                              start_time=self.start_time,
                              time_saved=int(time.time()),
                              code=self.code,
                              locked=self.locked,
                              closed=self.closed), can_save

    async def load_from_record(self, r):

        async with self.lock:
            err_prefix = f'[ABORT] Could not create raid {r.raid_name}'
            self.channel = self.bot.get_channel(r.channel_id)
            if not self.channel:
                err = f'{err_prefix}: channel {r.channel_id} not found'
                return False, err

            if not r.closed:
                try:
                    self.listing_message = await self.cog.listing_channel.fetch_message(r.listing_msg_id)
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
            self.mode = r.mode
            self.private = r.private
            self.no_mb = r.no_mb
            self.channel_name = r.channel_name
            self.desc = r.desc

            self.round = r.round
            self.max_joins = r.max_joins
            self.pool = Pool()
            if r.pool:
                self.pool.__dict__ = json.loads(r.pool)
            self.group = json.loads(r.raid_group) if r.raid_group else []
            self.ups = json.loads(r.ups)

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

    async def send_confirm_prompt(self, ctx, raid_name, channel_name, mode, desc, max_joins, private, no_mb, locked):
        async with self.lock:
            if self.confirmed or self.channel or self.wfr_message:
                return

            self.raid_name = raid_name
            self.channel_name = channel_name
            self.mode = mode
            self.max_joins = clamp(max_joins, 3, 30 if mode == QUEUE else 50)
            self.private = private
            self.no_mb = no_mb
            self.locked = locked
            options = ['**' + {
                FLEXIBLE: 'flexible',
                FFA: 'FFA',
                QUEUE: 'queue',
            }[self.mode] + '**']

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

{texts.CREATE_HELP}'''
            else:
                self.desc = desc
                msg = f'''<@{self.host_id}> This will create a new {options}raid host channel called `#{channel_name}` allowing a maximum of **{self.max_joins}** raiders with the description _{enquote(self.desc)}_

Are you sure you want to continue?

{texts.CREATE_HELP}'''

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
                await self.cog.cancel_before_confirm(self, reaction.message.channel)

    async def confirm_and_create(self, channel_ctx):
        self.bot.clear_wait_fors(self.host_id)

        async with self.lock:
            if self.confirmed or self.channel:
                return

            if len(self.cog.raids) >= MAX_RAIDS:
                return await self.cog.cancel_before_confirm(self, channel_ctx,
                                                             f'Unfortunately, we already have the maximum number of **{MAX_RAIDS}** raids being hosted. Please wait a bit and try again later.')

            # todo verify can host?
            await self.cog.log_channel.send(f"<@{self.host_id}> (ID: {self.host_id}) has created a new raid: {self.raid_name}.")

            self.wfr_message = None
            self.confirmed = True
            self.start_time = time.time()

            self.pool = Pool()
            self.group = []

            self.channel = await self.cog.make_raid_channel(self, channel_ctx)

            await self.channel.send(f"✨ _Welcome to your raid room, <@{self.host_id}>!_")

            readme = texts.make_readme(self.mode, self.desc, self.cog.listing_channel.id)

            rm_intro = await self.channel.send(f"{FIELD_BREAK}{readme[0]}"[:2000])
            rm_raider = await self.channel.send(f"{FIELD_BREAK}{readme[1]}"[:2000])
            rm_host = await self.channel.send(f"{FIELD_BREAK}{readme[2]}"[:2000])

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

        print('[Raid Confirmation]', self.cog.raids)
        self.bot.loop.create_task(self.cog.save_raids_to_db())

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
        if self.mode == FFA:
            reactions = [EMOJI['pokeball']]
            instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool! This is an **FFA** raid (there is no botte-managed queue).

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
        self.listing_message = await self.cog.listing_channel.send('', embed=e)

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

        thanks_message = await self.cog.thanks_channel.send('', embed=e)
        for reaction in ['💙', EMOJI['pokeball']]:
            await thanks_message.add_reaction(reaction.strip('<>'))

    def make_queue_embed(self, mentions=True, cmd=''):

        sections = []
        lines = []

        if self.mode != FFA:
            if self.group:
                group_text = ' '.join([f'<@{t[1]}>' if mentions else self.member_name(t[1]) for t in self.group])
                sections.append(f'**Current Group**\n{group_text}')

            next_up = self.pool.get_next(5 if self.mode == FLEXIBLE else 3, advance=False)
            group_text = ' '.join([f'<@{t[1]}>' if mentions else self.member_name(t[1]) for t in next_up])
            sections.append(f'**Next Call**\n{group_text}')

            lines = [f"{EMOJI['masterball']} " + (f"<@{uid}>" if mentions else self.member_name(uid)) for uid in
                     self.pool.mb]
        for i, uid in enumerate(self.pool.q):
            lines.append(f"`{i + 1: >2}` " + (f"<@{uid}>" if mentions else self.member_name(uid)))



        title = 'Active Raiders' if self.mode == FFA else 'Queue'
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

    async def up_command(self, ctx, arg):
        if arg is None:
            await send_message(ctx, 'Please specify a Pokémon!', error=True)
            return
        async with self.lock:
            self.ups.append(arg)
        e = discord.Embed(description=f'The current Pokémon is: **{arg}**!')
        await ctx.send(embed=e)

    async def round_command(self, ctx, arg):

        async with self.lock:
            if self.closed or not self.channel:
                return

            # todo max rounds

            if ctx.channel != self.channel:
                return await send_message(ctx, f'Please initialize rounds in the actual raid channel.', error=True)

            if self.mode == FFA:
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
            await self.new_strict_round(ctx)

    async def new_strict_round(self, ctx):

        size = self.pool.size()
        if size < 3:
            return await send_message(ctx, f'There are currently **{size}** participants, but You need at least **3** to start a raid.', error=True)

        self.round += 1
        self.pool.q.extend(uid for (join_type, uid) in self.group if join_type == 'pb')
        self.group = self.pool.get_next(3, advance=True)

        announcer = random.choice(ANNOUNCE_EMOJI)
        title = f'{announcer} 📣 Round {self.round} Start!'

        if self.private:
            code_text = f'''The code is hidden by the host! I've DM'd it to the group, but you can also type `.code` to see it (but please don't share it).'''
        else:
            code_text = f'The code to join is **{self.code}**!'

        if len(self.ups) == 0:
            up_text = f'''The host hasn't told me what the current Pokémon is! They can use `.up pokémon` to tell me!'''
        else:
            up_text = f'''Who's that Pokémon? It's **{self.ups[-1]}**!'''

        description = f'''{up_text}{DBL_BREAK}{code_text} Do **not** join unless you have been named below!{DBL_BREAK}If a trainer is AFK, the host may choose to:`.skip @user` to skip and replace someone in the current round
`.remove @user` to remove (and skip) a user from this raid (they **cannot** rejoin!)
`.block @user` to remove (and skip) a user from **all** of your raids{FIELD_BREAK}'''
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

        next_up = self.pool.get_next(3, advance=False)
        group_text = '🕑 ' + ' '.join([f'<@{t[1]}>' for t in next_up])
        e.add_field(name='Next Round', value=group_text, inline=False)

        try:
            await self.last_round_message.unpin()
        except Exception:
            pass

        self.last_round_message = await ctx.send(' '.join(mentions), embed=e)
        await self.last_round_message.pin()

    async def new_standard_round(self, ctx):
        pass

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
                msg = texts.make_error_msg(err, uid)
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

                await self.update_channel_emoji()

            elif join_type == 'pb':
                if uid in self.pool.q or uid in self.pool.mb:
                    await self.bot.misc.remove_raw_reaction(payload, user)
                    return

                self.pool.q.append(uid)

                await self.send_join_msg(member, join_type)
                await self.channel.set_permissions(member, send_messages=True, add_reactions=True)

                if uid not in self.pool.join_history:
                    self.pool.join_history.append(uid)

                await self.update_channel_emoji()

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

            await self.update_channel_emoji()

    async def send_join_msg(self, member, join_type):

        profile = await self.bot.trainers.get_wf_profile(member.id)
        profile_info = fc_as_text(profile)

        pls_read = f'''\nPlease read <#665681669860098073> and the **pinned messages** or you will probably end up **banned** without knowing why. _We will not be undoing bans if you didn't read them._'''

        if join_type == 'pb':
            if member.id not in self.pool.join_history:
                await self.cog.log_channel.send(f"{show_member_for_log(member)} has joined raid {self.raid_name}.\n{profile_info}")
                await self.channel.send(
                    f"{FIELD_BREAK}{EMOJI['join']} <@{member.id}> has joined the raid! {pls_read}\n{profile_info}{FIELD_BREAK}")
            else:
                await self.channel.send(f"{EMOJI['join']} <@{member.id}> has rejoined the raid!")

        elif join_type == 'mb':
            if member.id not in self.pool.join_history:
                await self.cog.log_channel.send(f"{show_member_for_log(member)} has joined raid {self.raid_name} **with a master ball**.\n{profile_info}")
                await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has joined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to block them. {pls_read}\n{profile_info}{FIELD_BREAK}")
            else:
                await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}")

        # elif join_type == 'mb+':
        #     return await self.channel.send(f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}")

    '''
    management
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
            replacement = self.pool.get_next(advance=True)
            self.group += replacement

            if self.private:
                user = self.bot.get_user(replacement[0][1])
                if user:
                    await user.send( f'''**{self.code}** is the private code for `{self.raid_name}` - it's your turn (as a replacement)! But keep in mind you may be skipped, so check on the channel as well.''')

        msg = f"<@{removed[1]}> has been skipped and **should not join.** <@{replacement[0][1]}> will take <@{removed[1]}>'s place in this round."

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

        await self.cog.log_channel.send(
            f'<@{self.host_id}> (ID: {self.host_id}) (or an admin) **kicked** {show_member_for_log(member)} in `{self.channel_name}`')
        await self.skip(member, ctx)

    async def block(self, member, ctx):
        pass

    async def end(self, immediately=False):
        async with self.lock:
            was_closed = self.closed
            self.closed = True

        ups = '\n'.join(self.ups)
        await self.cog.log_channel.send(f"<@{self.host_id}> (ID: {self.host_id}) (or an admin) **ended** the raid: {self.raid_name}.{DBL_BREAK}**Declared Pokémon:**\n{ups}")

        if was_closed:
            if immediately:
                await self.archive()
            return

        await self.channel.trigger_typing()
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, add_reactions=True),
        }
        await self.channel.edit(name=f'{CLOSED_EMOJI}{self.channel_name[1:]}', overwrites=overwrites)

        if not immediately:
            if not immediately and (self.round >= 3 or self.mode == FFA):
                msg = f'''✨ **Raid Host Complete!**

Thank you for raiding, this channel is now closed!

To thank <@{self.host_id}> for their hard work with hosting, head to <#{self.cog.thanks_channel.id}> and react with a 💙 !
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
        await self.cog.save_raids_to_db()
        if not immediately:
            await asyncio.sleep(60 * 10)
        await self.archive()

    async def archive(self):
        print(f'[Raid Archive] Archiving {self}')

        current = self.cog.raids.get(self.host_id, None)
        if current is not self:
            return None

        del self.cog.raids[self.host_id]
        self.destroy()

        await self.cog.save_raids_to_db()
        await self.channel.edit(sync_permissions=True, category=self.cog.archive, position=0)
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

    '''
    misc
    '''

    async def update_channel_emoji(self):
        if self.closed:
            return

        emoji = self.channel_name[0]
        if self.locked:
            if emoji != LOCKED_EMOJI:
                await self.channel.edit(name=f'{LOCKED_EMOJI}{self.channel_name[1:]}')

        else:
            pool_size = self.pool.size()
            if pool_size >= self.max_joins:
                if emoji != LOCKED_EMOJI:
                    await self.channel.edit(name=f'{LOCKED_EMOJI}{self.channel_name[1:]}')
            elif emoji != RAID_EMOJI:
                await self.channel.edit(name=f'{RAID_EMOJI}{self.channel_name[1:]}')
