import time
from collections import namedtuple

import aiohttp
import discord
import checks
from discord.ext import commands

from common import send_message, resolve_mention, send_user_not_found, \
    EMOJI, DBL_BREAK

CardRecord = namedtuple('CardRecord',
                        'discord_id, discord_name, fc, ign, switch_name, title_1, title_2, pkmn_icon, color, img, quote')

ENDPOINT = 'https://wooloo.farm'


async def get_user_by_credential(realm, identifier, endpoint=ENDPOINT):
    async with aiohttp.ClientSession() as session:
        r = await session.get(ENDPOINT + '/trainer-by-credential.json',
                              params={'realm': realm, 'identifier': identifier})
        if r.status not in (200, 404):
            r.raise_for_status()
        return await r.json()


async def has_wf_ban(uid, endpoint):
    async with aiohttp.ClientSession() as session:
        r = await session.get((endpoint),
                              params={'id': uid})
        if r.status not in (204, 404):
            r.raise_for_status()

        return r.status == 204


def has_raid_info(profile):
    if not profile:
        return False, 'WF_NO_ACCOUNT'

    for key in ['friend_code', 'switch_name', 'games']:
        if key not in profile or not profile[key]:
            return False, f'WF_NOT_SET: {key}'

    sw = '0' in profile['games'] and 'name' in profile['games']['0']
    sh = '1' in profile['games'] and 'name' in profile['games']['1']
    if not sw and not sh:
        return False, f'WF_NO_IGN'

    return True, None


def ign_as_text(profile, delimeter='\n'):
    text = '✨ **IGN**: Not Set!'
    if not profile or 'games' not in profile:
        return text

    games = []
    if '0' in profile['games'] and 'name' in profile['games']['0'] and profile['games']['0']['name']:
        games.append(f"{EMOJI['sword']} **IGN**: {profile['games']['0']['name']}")

    if '1' in profile['games'] and 'name' in profile['games']['1'] and profile['games']['1']['name']:
        games.append(f"{EMOJI['shield']} **IGN**: {profile['games']['1']['name']}")

    if not games:
        return text

    return delimeter.join(games)


def fc_as_text(profile):
    fc = f"SW-{profile['friend_code']}" if profile['friend_code'] else 'Not set!'
    switch = profile['switch_name'] if profile['switch_name'] else 'Not set!'

    return f'''**🗺️ FC**: {fc}
{ign_as_text(profile)}
**🎮 Switch Name**: {switch}'''


class Trainers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.userdb = bot.trainerdb
        self.wfcache = {}

    '''
    wf profile
    '''

    async def get_wf_profile(self, uid, ctx=None, refresh=False):
        if refresh or uid not in self.wfcache or time.time() > self.wfcache[uid]['expires']:
            if ctx:
                await ctx.trigger_typing()
            profile = await get_user_by_credential('discord', uid)
            if not profile:
                return None

            hri, err = has_raid_info(profile)
            expires = -1 if not hri else time.time() + 86400 / 2
            self.wfcache[uid] = {'profile': profile, 'expires': expires}

        return self.wfcache[uid]['profile']

    @checks.is_bot_admin()
    @commands.command()
    async def wf(self, ctx, uid:int):

        profile = await self.get_wf_profile(uid, ctx, refresh=True)
        if not profile:
            return await send_message(ctx, f'<@{uid}> does not have a profile on http://wooloo.farm/', error=True)

        await ctx.send(f'<@{uid}>\n{profile}')

    @commands.command()
    async def fc(self, ctx, *, arg=''):
        await self.view_fc(ctx, arg, False)

    @commands.command()
    async def fcr(self, ctx, *, arg=''):
        await self.view_fc(ctx, arg, True)

    @commands.command(aliases=['bl'])
    async def blacklist(self, ctx, *, arg=''):
        msg = 'Coming soon! Last update: NEVER'
        await ctx.author.send(msg)
        await ctx.message.delete()

    async def view_fc(self, ctx, arg, refresh=False):
        if not arg or refresh:
            member = ctx.author
        else:
            member = resolve_mention(ctx.message.guild, arg, False)
            if not member:
                return await send_user_not_found(ctx, arg)

        profile = await self.get_wf_profile(member.id, ctx, refresh)
        if not profile:
            return await send_message(ctx, f'{str(member)} does not have a profile on http://wooloo.farm/', error=True)

        msg = f'''_{str(member)}_
{fc_as_text(profile)}'''

        hri, err = has_raid_info(profile)
        if not hri:
            msg += f'{DBL_BREAK}_go to <https://wooloo.farm/profile/edit> to enter missing info_'  # , then_ `.fcr` _to refresh_'
        elif not refresh:
            msg += f'\n`.fcr` to refresh'

        await ctx.send(msg)

    '''
    permissions
    '''

    async def can_raid(self, member, host_id, ctx=None):

        # todo maybe has raiders role check

        roles = member.roles
        if any(role.id == self.bot.config['banned_from_raiding_role'] for role in member.roles):
            return False, 'ROLE_BANNED_FROM_RAIDING'

        profile = await self.get_wf_profile(member.id, ctx)
        hri, err = has_raid_info(profile)
        if not hri:
            return hri, err

        # todo check block list

        wf_ban = await has_wf_ban(member.id, self.bot.config['wf_ban_endpoint'])
        if wf_ban:
            print(f'{member} (ID: {member.id}) is BANNED from raiding by authoritative server.')
            return False, 'WF_BAN'

        return True, None

    async def can_host(self, member, ctx=None):

        # todo maybe has raiders role check

        roles = member.roles
        if any(role.id == self.bot.config['banned_from_raiding_role'] for role in member.roles):
            return False, 'ROLE_BANNED_FROM_RAIDING'
        if any(role.id == self.bot.config['banned_from_hosting_role'] for role in member.roles):
            return False, 'ROLE_BANNED_FROM_HOSTING'

        profile = await self.get_wf_profile(member.id, ctx)
        hri, err = has_raid_info(profile)
        if not hri:
            return hri, err

        wf_ban = await has_wf_ban(member.id, self.bot.config['wf_ban_endpoint'])
        if wf_ban:
            print(f'{member} (ID: {member.id}) is BANNED from hosting by authoritative server.')
            return False, 'WF_BAN'

        return True, None

    '''
    card
    '''

    # @commands.command()
    # async def card(self, ctx, *, arg=None):
    #     if not arg:
    #         await self.view_card(ctx)
    #         return
    #
    #     helpMsg = '''TODO help menu'''
    #     mention = resolve_mention(ctx.message.guild, arg)
    #     if mention:
    #         await self.view_card(ctx, mention)
    #         return
    #
    #     await send_message(ctx, f'''Couldn\'t find that user!{DBL_BREAK}{helpMsg}''', error=True)
    #
    # async def view_card(self, ctx, member=None):
    #     member = member or ctx.author
    #
    #     # await ctx.trigger_typing()
    #
    #     name = str(member)
    #     img = 'https://cdn.discordapp.com/attachments/655294736323575818/661139313790156830/trainercard-_Rina.png'
    #     gif = 'https://play.pokemonshowdown.com/sprites/xyani/floette-eternal.gif'
    #     color = random.choice(TYPE_COLORS)
    #     print(color)
    #     footer = '🛡️ Pokémon Shield'
    #     code = '6639-5237-7783'
    #
    #     description = '_sleepy boy 24/7_'
    #
    #     e = discord.Embed(title=name, description=description, color=color) \
    #         .set_image(url=img).set_thumbnail(url=gif).set_footer(text=footer) \
    #         .add_field(name='🗺️ FC', value=code, inline=False) \
    #         .add_field(name='✨ IGN', value='Rina', inline=False) \
    #         .add_field(name='🎮 Switch Name', value='Rina\'s Switch', inline=False)
    #
    #     await ctx.send(f'<@{ctx.author.id}>', embed=e)


def setup(bot):
    trainers = Trainers(bot)
    bot.add_cog(trainers)
    bot.trainers = trainers
