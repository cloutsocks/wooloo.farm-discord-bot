import asyncio
import json
import random
import re
import time

import discord

import texts

from common import clamp, send_message, pokeballUrl, TYPE_COLORS, DBL_BREAK, FIELD_BREAK, EMOJI, \
                   ICON_CLOSE, BLUE_HEART, YELLOW_HEART, GREEN_HEART, SPY_EMOJI, enquote
from trainers import ign_as_text, fc_as_text

from collections import namedtuple
from .pool import Pool
from .config import RAID_EMOJI, LOCKED_EMOJI, CLOSED_EMOJI, \
                    BALANCED, FFA, QUEUE

RaidRecord = namedtuple('RaidRecord',
                        'host_id, guild_id, raid_name, mode, private, allow_mb, channel_id, emoji, desc, listing_msg_id, last_round_msg_id, round, max_joins, pool, ups, start_time, time_saved, code, locked, closed')


def show_member_for_log(member):
    return f"<@{member.id}> ({member.name}#{member.discriminator}, ID: {member.id}, Nickname: {member.nick})"


class Raid(object):
    def __init__(self, bot, cog, guild, host_id):
        self.bot = bot
        self.cog = cog
        self.host_id = host_id
        self.guild = guild

        self.raid_name = None
        self.mode = BALANCED
        self.private = False
        self.allow_mb = False
        self.channel = None
        self.emoji = RAID_EMOJI
        self.desc = None
        self.listing_message = None
        self.last_round_message = None
        self.pins = []
        self.echos = {}

        self.round = 0
        self.max_joins = 30
        self.pool = None
        self.ups = []

        self.start_time = None
        self.time_saved = None
        self.code = None

        self.wfr_message = None

        self.locked = False
        self.confirmed = False
        self.closed = False

        self.join_increment = 0

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
                              allow_mb=self.allow_mb,
                              channel_id=self.channel.id if self.channel is not None else None,
                              emoji=self.emoji,
                              desc=self.desc,
                              listing_msg_id=self.listing_message.id if self.listing_message is not None else None,
                              last_round_msg_id=self.last_round_message.id if self.last_round_message is not None else None,
                              round=self.round,
                              max_joins=self.max_joins,
                              pool=json.dumps(self.pool.__dict__) if self.pool is not None else None,
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
            self.allow_mb = r.allow_mb
            self.desc = r.desc

            self.round = r.round
            self.max_joins = r.max_joins
            self.pool = Pool()
            if r.pool:
                self.pool.__dict__ = json.loads(r.pool)
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

    def clear_wait_fors(self):
        self.bot.clear_wait_fors(self.host_id)

    def make_prompt_text(self):

        option_parts = []
        option_parts.append('**' + {
            BALANCED: 'balanced',
            FFA: 'FFA',
            QUEUE: 'queue',
        }[self.mode] + '**')

        if self.private:
            option_parts.append('**private** (hidden code)')
        if self.locked:
            option_parts.append('🔒 **locked**')

        options = '' if not option_parts else f'''{', '.join(option_parts)} '''

        raid_name = self.raid_name
        if self.mode == FFA and 'ffa' not in self.raid_name.lower():
            raid_name = f'''ffa {self.raid_name}'''

        channel_name = self.bot.raid_cog.make_channel_name(raid_name, self.emoji or RAID_EMOJI)

        parts = [
            f'''<@{self.host_id}>\nThis will create a new {options}raid host channel called `#{channel_name}` allowing a maximum of **{self.max_joins}** raiders''',
            f' with the description _{enquote(self.desc)}_' if self.desc else '.', f'''\n\n{texts.CREATE_HELP}\n\n'''
        ]

        modes = {
            YELLOW_HEART: '**Balanced** (recommended, coming soon) — a mix between queue and ffa that is the best of both worlds',
            GREEN_HEART: '**FFA** — no bot organized queue! anyone with the `.code` can join; a bit more hectic and not everyone gets to go',
            BLUE_HEART: '**Queue** — a strict queue where raiders are called 3 at a time, but slows down when user don\'t make it in (can be cumbersome)',
        }

        options = {
            LOCKED_EMOJI: 'to lock the raid until you unlock with `.lock`',
            SPY_EMOJI: 'to hide the code from lurkers',
            EMOJI['pokeball']: 'to start the raid',
            EMOJI['masterball']: 'to start the raid & allow masterball users to join with priority',
            ICON_CLOSE: 'to cancel'
        }

        reactions = list(modes.keys()) + list(options.keys())

        parts.append('_Select a Raid Mode_\n')
        for emoji, text in modes.items():
            parts.append(f'''{emoji} {text}\n''')

        parts.append('\n_Options_\n')
        for emoji, text in options.items():
            if emoji == EMOJI['masterball'] and self.mode == FFA:
                continue

            parts.append(f'''{emoji} {text}\n''')

        parts.append('\u200b')
        return ''.join(parts), reactions

    async def send_confirm_prompt(self, ctx, options):
        async with self.lock:
            if self.confirmed or self.channel or self.wfr_message:
                return

            self.raid_name = options['raid_name']
            self.mode = options['mode']
            self.max_joins = clamp(options['max_joins'], 3, 30 if options['mode'] == QUEUE else 50)
            self.private = False
            self.locked = False
            self.desc = options.get('desc', None)
            self.emoji = options.get('emoji', None)

            # move to confirm and create
            # if self.mode == FFA and 'ffa' not in self.raid_name.lower():
            #     self.raid_name = f'''ffa {self.raid_name}'''

            msg, reactions = self.make_prompt_text()

            self.wfr_message = await ctx.send(msg)
            for reaction in reactions:
                await self.wfr_message.add_reaction(reaction.strip('<>'))

            self.bot.wfr[self.host_id] = self

    async def update_confirm_prompt(self):
        msg, reactions = self.make_prompt_text()
        await self.wfr_message.edit(content=msg)

    async def handle_reaction(self, reaction, user):
        if not self.confirmed:
            emoji = str(reaction.emoji)
            if emoji == EMOJI['pokeball'] or emoji == '✅':
                await self.confirm_and_create(reaction.message.channel)
            elif emoji == EMOJI['masterball'] and self.mode != FFA:
                self.allow_mb = True
                await self.confirm_and_create(reaction.message.channel)
            elif emoji == ICON_CLOSE:
                await self.cog.cancel_before_confirm(self, reaction.message.channel)

            # modes
            elif emoji == YELLOW_HEART:
                if self.mode != BALANCED:
                    await reaction.message.channel.send(f'<@{user.id}> _Balanced mode is coming soon! Fixes most problems with queue and FFA, and a lot simpler too._', delete_after=10)
            elif emoji == GREEN_HEART:
                if self.mode != FFA:
                    self.mode = FFA
                    await self.update_confirm_prompt()
            elif emoji == BLUE_HEART:
                if self.mode != QUEUE:
                    if 'ffa' in self.raid_name:
                        await reaction.message.channel.send(
                            f'''<@{user.id}> _You can't put 'ffa' in the title if it's not an ffa. You may remake it with a new name.''',
                            delete_after=10)
                    else:
                        self.mode = QUEUE
                        await self.update_confirm_prompt()

            # options
            elif emoji == LOCKED_EMOJI:
                self.locked = not self.locked
                await self.update_confirm_prompt()
            elif emoji == SPY_EMOJI:
                self.private = not self.private
                await self.update_confirm_prompt()

    async def confirm_and_create(self, channel_ctx):
        self.bot.clear_wait_fors(self.host_id)

        async with self.lock:
            if self.confirmed or self.channel:
                return

            if len(self.cog.raids) >= self.cog.max_raids:
                return await self.cog.cancel_before_confirm(self, channel_ctx,
                                                             f'Unfortunately, we already have the maximum number of **{self.cog.max_raids}** raids being hosted. Please wait a bit and try again later.')

            if self.mode == FFA and 'ffa' not in self.raid_name.lower():
                self.raid_name = f'''ffa {self.raid_name}'''

            await self.cog.log_channel.send(f"<@{self.host_id}> (ID: {self.host_id}) has created a new raid: {self.raid_name}.")

            self.wfr_message = None
            self.confirmed = True
            self.start_time = time.time()

            self.pool = Pool()

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

        description = f'''{self.emoji or RAID_EMOJI} _hosted by <@{self.host_id}> in <#{self.channel.id}>_'''
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
        elif not self.allow_mb:
            reactions = [EMOJI['pokeball']]
            instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool! {EMOJI["masterball"]} are **disabled** for this raid.

When you are done raiding, you **must** leave the raid by removing your {EMOJI["pokeball"]} reaction or by typing `.leave`. Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''
        # queue, masterballs
        else:
            reactions = [EMOJI['pokeball'], EMOJI['masterball']]
            instructions = f'''Click {EMOJI["pokeball"]} to join the raid pool or {EMOJI["masterball"]} _only_ if you're going to use a masterball (at which point you'll be removed from the queue).

When you are done raiding, you **must** leave the raid by removing your {EMOJI["pokeball"]} reaction or by typing `.leave`. Please read the **pinned instructions** in the channel carefully or you'll be removed!{FIELD_BREAK}'''

        footer = ''
        thumbnail = f"https://static.wooloo.farm/games/swsh/species_lg/831{'_S' if 'shiny' in self.channel.name.lower() else ''}.png"
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

{'To thank them, react with a 💙 ! ' if self.bot.config['add_thanks_heart'] else ''}If you managed to catch one, add in a {EMOJI['pokeball']} !'''
        if self.desc:
            description += f'\n\n_{enquote(self.desc)}_'
        description += FIELD_BREAK

        footer = ''
        thumbnail = f"https://static.wooloo.farm/games/swsh/species_lg/831{'_S' if 'shiny' in self.channel.name.lower() else ''}.png"
        color = random.choice(TYPE_COLORS)
        e = discord.Embed(title=self.raid_name, description=description, color=color) \
            .set_thumbnail(url=thumbnail).set_footer(text=footer) \
            .add_field(name='🗺️ FC', value=f"SW-{profile['friend_code']}", inline=True)

        for ign in games:
            e.add_field(name=ign[0], value=ign[1], inline=True)

        e.add_field(name='🎮 Switch Name', value=profile['switch_name'], inline=True)

        thanks_message = await self.cog.thanks_channel.send('', embed=e)
        reactions = [EMOJI['pokeball']]
        if self.bot.config['add_thanks_heart']:
            reactions.insert(0, '💙')

        for reaction in reactions:
            await thanks_message.add_reaction(reaction.strip('<>'))

    def make_queue_embed(self, mentions=True, cmd=''):

        sections = []
        lines = []

        if self.mode != FFA:
            if self.pool.group:
                group_text = ' '.join([f'''<@{t['uid']}>''' if mentions else self.member_name(t['uid']) for t in self.pool.group])
                sections.append(f'**Current Group**\n{group_text}')

            next_up = self.pool.get_next(5 if self.mode == BALANCED else 3, advance=False)
            group_text = ' '.join([f'''<@{t['uid']}>''' if mentions else self.member_name(t['uid']) for t in next_up])
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

    async def new_balanced_round(self, ctx):
        for raider in self.pool.group:
            if raider['uid'] not in self.pool.group_miss:
                self.pool.group.remove(raider)
                if raider['join_type'] == 'pb':
                    self.pool.q.append(raider['uid'])

        # call get next based on remaining slots

        skipped = self.pool.group[to_remove]
        del self.pool.group[to_remove]


    async def new_strict_round(self, ctx):
        reinsert = [t['uid'] for t in self.pool.group if t['join_type'] == 'pb']

        if self.pool.size() == len(reinsert) == 0:
            return await send_message(ctx, f'''There's no one in the queue :(''', error=True)

        self.round += 1
        self.pool.q.extend(reinsert)
        self.pool.group = self.pool.get_next(3, advance=True)

        announcer = EMOJI[random.choice(['wuwu', 'flop', 'wooloo_fast', 'cooloo', 'stinkey', 'ballguy', 'jacob', 'jacobsdog', 'elliot', 'lily', 'honk'])]
        title = f'{announcer} 📣 Round {self.round} Start!'

        if self.private:
            code_text = f'''The code is hidden by the host! I've DM'd it to the group, but you can also type `.code` to see it (but please don't share it).'''
        else:
            code_text = f'The code to join is **{self.code}**!'

        if len(self.ups) == 0:
            up_text = f'''The host hasn't told me what the current Pokémon is! They can use `.up pokémon` to tell me!'''
        else:
            up_text = f'''Who's that Pokémon? It's **{self.ups[-1]}**!'''

        description = f'''{up_text}{DBL_BREAK}{code_text} Do **not** join unless you have been named below!{DBL_BREAK}If a trainer is AFK, the host may choose to:
`.skip @user` to skip and replace someone in the current round
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
        for i, raider in enumerate(self.pool.group):
            if self.private:
                user = self.bot.get_user(raider['uid'])
                if user:
                    await user.send(f'''**{self.code}** is the private code for `{self.raid_name}` - it's your turn! But keep in mind you may be skipped, so check on the channel as well.''')

            mention = f'''<@{raider['uid']}>'''
            mentions.append(mention)
            profile = await self.bot.trainers.get_wf_profile(raider['uid'], ctx)
            profile_info = fc_as_text(profile)
            icon = EMOJI['masterball'] if raider['join_type'] == 'mb' else EMOJI['pokeball']
            raider_text = f'{icon} {mention}\n{profile_info}{FIELD_BREAK}'

            # if i < len(self.pool.group) - 1:
            #     raider_text += FIELD_BREAK

            e.add_field(name=str(i + 1), value=raider_text, inline=False)

        next_up = self.pool.get_next(3, advance=False)
        group_text = '🕑 ' + ' '.join([f'''<@{t['uid']}>''' for t in next_up])
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
                await self.channel.set_permissions(member, read_messages=True if self.bot.config["test_mode"] else None, send_messages=True, add_reactions=True)

                if uid not in self.pool.join_history:
                    self.pool.join_history.append(uid)

                await self.update_channel_emoji()

            elif join_type == 'pb':
                if uid in self.pool.q or uid in self.pool.mb:
                    await self.bot.misc.remove_raw_reaction(payload, user)
                    return

                self.pool.q.append(uid)

                await self.send_join_msg(member, join_type)
                await self.channel.set_permissions(member, read_messages=True if self.bot.config["test_mode"] else None, send_messages=True, add_reactions=True)

                if uid not in self.pool.join_history:
                    self.pool.join_history.append(uid)

                await self.update_channel_emoji()

    async def user_leave(self, user, remove_reaction=False):

        async with self.lock:
            if self.closed:
                return
            uid = user.id
            removed = self.pool.remove(uid)
            if not removed and uid not in self.pool.group:
                return

        member = self.guild.get_member(uid)
        if not member:
            return
        await self.channel.set_permissions(member, overwrite=None)
        await self.channel.send(f"{EMOJI['leave']} <@{member.id}> has left the raid.")
        if self.mode != FFA:
            await self.skip(member, supress_no_skip=True)
        await self.skip(member)


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

        # repeated action workaround discord
        await self.channel.set_permissions(member, overwrite=None)


    async def miss(self, user, ctx):
        async with self.lock:
            if self.closed:
                return False

            if self.mode != BALANCED:
                await send_message(ctx, '`.miss` only works in balanced mode', error=True)
                return False

            uid = user.id
            uids = [t['uid'] for t in self.pool.group]
            if not uid in uids:
                await send_message(ctx, '''You're not in the curent group... you shouldn't have attempted to join.''', error=True)
                return False

            self.pool.add_miss(uid)
        await ctx.send(f'''❌ **Miss!** _<@{user.id} was unable to make it in!_\ntodo current group status''')
        # todo current miss status
        return True


    async def send_join_msg(self, member, join_type):

        profile = await self.bot.trainers.get_wf_profile(member.id)
        profile_info = fc_as_text(profile)

        ad_message = ''

        if self.bot.config['guest_server']:
            pls_read = f'''\nPlease read **pinned messages**.'''

            self.join_increment += 1
            if self.join_increment >= 4:
                self.join_increment = 0
                ad_message = f'\n_This botte was developed by **jacob#2332** and **rory#3380** of <https://wooloo.farm/>\nFor botte suggestions, please visit <https://discord.gg\wooloo> _{FIELD_BREAK}'
        else:
            pls_read = f'''\nPlease read <#665681669860098073> and the **pinned messages** or you will probably end up **banned** without knowing why. _We will not be undoing bans if you didn't read them._'''

        if join_type == 'pb':
            if member.id not in self.pool.join_history:
                await self.cog.log_channel.send(f"{show_member_for_log(member)} has joined raid {self.raid_name}.\n{profile_info}")
                await self.channel.send(
                    f"{FIELD_BREAK}{EMOJI['join']} <@{member.id}> has joined the raid! {pls_read}\n{profile_info}{FIELD_BREAK}{ad_message}")
            else:
                await self.channel.send(f"{EMOJI['join']} <@{member.id}> has rejoined the raid!{FIELD_BREAK}{ad_message}")

        elif join_type == 'mb':
            if member.id not in self.pool.join_history:
                await self.cog.log_channel.send(f"{show_member_for_log(member)} has joined raid {self.raid_name} **with a master ball**.\n{profile_info}")
                await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has joined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to block them. {pls_read}\n{profile_info}{FIELD_BREAK}{ad_message}")
            else:
                await self.channel.send(
                    f"{EMOJI['masterball']} <@{member.id}> has rejoined the raid with a **master ball**! They have high priority, so if they do not actually use a master ball, please feel free to remove or block them.{FIELD_BREAK}{ad_message}")

    '''
    management
    '''

    async def skip(self, member, supress_no_skip=False):

        async with self.lock:
            uids = [t['uid'] for t in self.pool.group]
            print('----')
            print(uids)
            print(member.id)
            try:
                to_remove = uids.index(member.id)
                print('to remove', to_remove)
            except ValueError:
                if not supress_no_skip:
                    await self.channel.send(f'There\'s no need to skip {str(member)} as they aren\'t in the current round. Type `.q` to see it.')
                return

            if not self.pool.get_next(advance=False):
                # todo fix for leave
                await self.channel.send(f'{str(member)} **cannot be skipped** right now as there is nobody to take their place.')
                return

            skipped = self.pool.group[to_remove]
            del self.pool.group[to_remove]
            replacement = self.pool.get_next(advance=True)
            self.pool.group += replacement

            if skipped['uid'] not in self.pool.kicked:
                # If a Master Ball user was skipped, put them into the regular queue.
                self.pool.q.append(skipped['uid'])

            if self.private:
                user = self.bot.get_user(replacement[0]['uid'])
                if user:
                    await user.send( f'''**{self.code}** is the private code for `{self.raid_name}` - it's your turn (as a replacement)! But keep in mind you may be skipped, so check on the channel as well.''')

        msg = f'''<@{skipped['uid']}> has been skipped and **should not join.** <@{replacement[0]['uid']}> will take <@{skipped['uid']}>'s place in this round.'''

        return await self.channel.send(msg)

    async def kick(self, member, ctx):

        async with self.lock:
            uid = member.id
            if uid not in ctx.bot.config['wooloo_staff_ids']:
                await self.channel.set_permissions(member, read_messages=False)

            self.pool.remove(uid)
            self.pool.kicked.append(uid)

        if uid in self.pool.join_history:
            await member.send(
                f"Oh no! You were removed from the raid `{self.raid_name}` and cannot rejoin. {EMOJI['flop']}")
        await ctx.send(
            f"<@{uid}> has been removed from this raid. They will not be able to see this channel or rejoin. {EMOJI['flop']}")

        await self.cog.log_channel.send(
            f'<@{self.host_id}> (ID: {self.host_id}) (or an admin) **kicked** {show_member_for_log(member)} in {str(self.channel)} (`{self.channel.name}`)')
        await self.skip(member)

    async def block(self, member, ctx):
        pass

    async def end(self, ctx, immediately=False):
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
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=False if ctx.bot.config["test_mode"] else None, add_reactions=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True if ctx.bot.config["test_mode"] else None, add_reactions=True),
        }

        for role in self.cog.admin_roles:
            overwrites[role] = discord.PermissionOverwrite(send_messages=True, read_messages=True if ctx.bot.config["test_mode"] else None, add_reactions=True)

        await self.channel.edit(name=f'{CLOSED_EMOJI}{self.channel.name[1:]}', overwrites=overwrites)

        if not immediately:
            if not immediately and (self.round >= 3 or self.mode == FFA):

                thanks_msg = self.bot.config['thanks_msg'].format(thanks_channel=f'<#{self.cog.thanks_channel.id}>', emoji=EMOJI)

                msg = f'''✨ **Raid Host Complete!**

Thank you for raiding, this channel is now closed!

To thank <@{self.host_id}> for their hard work with hosting, {thanks_msg}

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
        self.clear_wait_fors()

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

        if self.locked:
            emoji = LOCKED_EMOJI
        else:
            pool_size = self.pool.size()
            if pool_size >= self.max_joins:
                emoji = LOCKED_EMOJI
            else:
                emoji = self.emoji or RAID_EMOJI

        updated_name = f'{emoji}{self.channel.name[1:]}'
        if self.channel.name != updated_name:
            await self.channel.edit(name=updated_name)
