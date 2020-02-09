import os
import random
import re
import sqlite3
import time

import discord
from discord.ext import tasks, commands

import checks
import texts
from common import clamp, idPattern, send_message, print_error, escuchameUrl, pokeballUrl, TYPE_COLORS, DBL_BREAK, EMOJI, ICON_CLOSE, enquote
from trainers import ign_as_text, fc_as_text

from .config import RAID_EMOJI, LOCKED_EMOJI, CLOSED_EMOJI, \
                    DEFAULT, LOCKED, CLOSED, \
                    FLEXIBLE, FFA, QUEUE, \
                    MAX_RAIDS

from .raid import Raid, RaidRecord


class Cog(commands.Cog):
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
            mode integer not null default 1,
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
            ups text,
            start_time integer not null,
            time_saved integer,
            code text,
            locked integer not null,
            closed integer not null,
            primary key(host_id)
        )''')
        self.db.commit()
        c.close()

    def remake_db(self):
        self.db.close()
        try:
            os.remove('data.db')
        except:
            pass
        self.db = sqlite3.connect('raid.db')
        self.make_db()

    async def load_raids_from_db(self):
        # print(f'[DB] Attempting to load raids...')
        if self.raids:
            print('[DB ERROR] `self.raids` already exists, should be empty')

        t = time.time()
        c = self.db.cursor()
        c.execute('select host_id, guild_id, raid_name, mode, private, no_mb, channel_id, channel_name, desc, listing_msg_id, last_round_msg_id, round, max_joins, pool, raid_group, ups, start_time, time_saved, code, locked, closed from raids')
        for r in map(RaidRecord._make, c.fetchall()):
            raid = Raid(self.bot, self, self.guild, r.host_id)
            loaded, err = await raid.load_from_record(r)
            print('raid:', raid)
            print(await raid.as_record())
            if not loaded:
                print(f'Did not succesfully load {r.raid_name}, error: {err}')
                if raid.channel and not raid.closed:
                    await raid.channel.send(f'❌ During a botte restart, this raid failed to load and will have to be remade. This is likely a Discord issue, but let <@232650437617123328> know. The following error occured:\n\n```{err}```')
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

                    await raid.channel.send(f'🔄 Botte Reloaded! Restored raid data from ~{ago} ago.')

        c.close()
        print(f'[DB] Loaded {len(self.raids)} raids from database. Took {time.time() - t:.3f} seconds')

    async def save_raids_to_db(self):
        # print(f'[DB] Attempting to save raids...')
        # t = time.time()
        print('[DB] Starting saving raids to DB.')
        c = self.db.cursor()
        c.execute('delete from raids')
        for raid in self.raids.values():
            try:
                record, can_save = await raid.as_record()
            except Exception as e:
                print(f'[Raid Serialize] Could not serialize raid {raid.name}; this will be lost! Error: {type(e).__name__}, {e}')
                continue

            if not can_save:
                print(f'[DB] Skipped saving record {record}')
                continue

            print(f'[DB] Saving record {record} to database')
            try:
                c.execute('insert into raids values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', record)
            except sqlite3.Error as e:
                print(f'[SQL Insert Error] Could not insert raid {record.raid_name}! Error: {type(e).__name__}, {e}')

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
            return await send_message(ctx, 'Creating new raids is temporarily paused (probably pending a botte update, check the botte status channel).', error=True)

        if arg is None or 'help' in arg:
            msg = f'''{texts.CREATE_HELP}

_Managing a Raid_
{texts.HOST_COMMANDS}
'''
            return await send_message(ctx, msg)

        if len(self.raids) >= MAX_RAIDS:
            return await send_message(ctx,
                                      f'Unfortunately, we already have the maximum number of **{MAX_RAIDS}** raids being hosted.',
                                      error=True)

        uid = ctx.author.id
        if uid in self.raids:
            return await send_message(ctx, 'You are already configuring or hosting a raid.', error=True)

        mode = FLEXIBLE
        try:
            mode_arg, arg = arg.split(' ', 1)
            try:
                mode = {
                    'flexible': FLEXIBLE,
                    'ffa': FFA,
                    'queue': QUEUE,
                }[mode_arg.lower()]
            except KeyError:
                pass
        except ValueError:
            pass

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
        if 'ffa' in name.lower():
            mode = FFA
        elif mode == FFA:
            name = f'ffa {name}'

        channel_name = f"{RAID_EMOJI}-{name.replace(' ', '-')}"[:100]
        channel_name = re.sub('[<>]', '', channel_name)

        can_host, err = await self.bot.trainers.can_host(ctx.author, ctx)
        if not can_host:
            msg = texts.make_error_msg(err, uid)
            return await send_message(ctx, msg, error=True)

        self.raids[uid] = Raid(self.bot, self, self.guild, ctx.author.id)
        print('[Raid Creation]', self.raids)
        # todo refactor long param list into options dict or namedtuple
        await self.raids[uid].send_confirm_prompt(ctx, name, channel_name, mode, desc, max_joins, private, no_mb, locked)

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

        return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

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

        return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

    @commands.command()
    async def up(self, ctx, *, arg=None):
        uid = ctx.author.id
        if uid in self.raids:
            return await self.raids[uid].up_command(ctx, arg)

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
            return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

        match = idPattern.search(arg)
        if not match:
            return await send_message(ctx, f'Please tag the member you\'d like to {action}', error=True)

        mention_id = int(match.group(1))
        member = ctx.message.guild.get_member(mention_id)
        if not member:
            return await send_message(ctx, f'Could not remove user! Please tag the mods to manually intervene.',
                                      error=True)

        if member == self.bot.user or member.id == target_raid.host_id:
            return await send_message(ctx, '', error=True, image_url=escuchameUrl)

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

        n = clamp(n, 3, 30 if raid.mode == QUEUE else 50)
        size = raid.pool.size()
        if n < size:
            return await send_message(ctx, f'You cannot go lower than the current pool size ({size}).', error=True)

        if raid.max_joins == n:
            return await send_message(ctx, f'That\'s... already the max.', error=True)

        verb = 'increased' if raid.max_joins < n else 'decreased'
        raid.max_joins = n
        await raid.update_channel_emoji()
        await ctx.send(f'Max participants {verb} to **{n}**.')

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

        await raid.update_channel_emoji()
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

    @commands.command()
    async def echo(self, ctx, *, arg=''):
        uid = ctx.author.id
        if uid not in self.raids:
            return

        raid = self.raids[uid]
        if raid.channel != ctx.channel:
            return await send_message(ctx, f'You may only `.echo` in your active raid channel.', error=True)

        echo_help = f'_Usage_\n`.echo <tag> <message goes here>` to set an echo\n`.echo <tag>` to have me repeat it\nTo update an `.echo`, just set it again.'

        if not arg:
            msg = echo_help
            if len(raid.echos):
                tags = ' '.join([f'`{t}' for t in raid.echos.keys()])
                msg = f'{msg}{DBL_BREAK}Current Tags: {tags}'
            return await send_message(ctx, msg, error=True)

        msg = None
        try:
            tag, msg = arg.split(' ', 1)
        except ValueError:
            tag = arg

        if not msg:
            if tag in raid.echos:
                return await ctx.send(f'**Echo from the Host**\n{raid.echos[tag]}')
            return await send_message(ctx, f'Echo not found for tag `{tag}`.{DBL_BREAK}{echo_help}', error=True)

        if len(raid.echos) > 5:
            return await send_message(ctx, f'You cannot have more than 5 echos at a time, currently. If you want more,let jacob know.', error=True)

        raid.echos[tag] = msg[:1000]
        return await ctx.send(f'**Raid echo set for tag `{tag}`**\nUse `.echo {tag}` to have me repeat it.{DBL_BREAK}{raid.echos[tag]}')

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

        return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

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

        return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

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

        return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

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

        return await send_message(ctx, texts.RAID_NOT_FOUND, error=True)

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
    @commands.command(name='dangerclearall', aliases=['dangerca'])
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

    @checks.is_jacob()
    @commands.command(name='dangerremakedb')
    async def db_remake(self, ctx):
        self.remake_db()
        await ctx.send(f'Finished. If there are active raids, they will need to be cleaned.')

    @checks.is_bot_admin()
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
        e = discord.Embed(title='Botte Announcement!', description=f'''{EMOJI['honk']} {arg}''', color=color)
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

    @checks.is_bot_admin()
    @commands.command()
    async def raidsay(self, ctx, *, arg):

        if not self.category:
            return

        msg = arg
        for channel in self.category.text_channels:
            if channel.name[0] in [RAID_EMOJI, LOCKED_EMOJI]:
                await channel.send(msg)
        if self.breakroom:
            await self.breakroom.send(msg)
        await ctx.send('Sent!')

    @checks.is_bot_admin()
    @commands.command(aliases=['cl'])
    async def clear(self, ctx):
        if self.archive:
            for channel in self.archive.text_channels:
                if channel.name[0] in [RAID_EMOJI, LOCKED_EMOJI, CLOSED_EMOJI]:
                    await channel.delete()

    async def clear_channels_dirty(self):
        if self.category:
            if self.listing_channel:
                await self.listing_channel.purge(limit=100, check=lambda m: m.author == self.bot.user)

            for channel in self.category.text_channels:
                if channel.name[0] in [RAID_EMOJI, LOCKED_EMOJI, CLOSED_EMOJI]:
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

        raids_cid = 661468408856051733 # test
        archive_cid = 666527061673771030 # test

        # raids_cid = 661425972158922772  # live
        # archive_cid = 652579764837679145  # live

        # raids_cid = 669605813727395864 # demo
        # archive_cid = 669605829984387098 # demo

        try:
            self.category = self.bot.get_channel(raids_cid)
            self.archive = self.bot.get_channel(archive_cid)
            self.guild = self.category.guild
            self.listing_channel = discord.utils.get(self.guild.text_channels, name='active-raids')
            self.thanks_channel = discord.utils.get(self.guild.text_channels, name='raid-thanks')
            self.log_channel = discord.utils.get(self.guild.text_channels, name='raid-log')
            self.breakroom = discord.utils.get(self.guild.text_channels, name='raid-chat')
            print(f'Bound to {raids_cid}', self.category, self.guild, self.listing_channel)

        except AttributeError:
            print(f'Could not bind to {raids_cid}')
            return False

        return True


def setup(bot):
    cog = Cog(bot)
    bot.add_cog(cog)
    bot.raid_cog = cog
