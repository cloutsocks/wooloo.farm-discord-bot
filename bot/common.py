import asyncio
import re
import sys
import traceback

import discord
import copy
import difflib

from numpy import interp
from discord.ext import commands

idPattern = re.compile(r'<@!?(\d+?)>')

ICON_ATTACK = '⚔'
ICON_CLOSE = '❌'
ERROR_RED = 0xD32F2F
INFO_BLUE = 0x3579f0

DBL_BREAK = '\n \n'
FIELD_BREAK = '\n\u200b'

TYPE_COLORS = (
    0xFFFFFF,
    0xE88158,
    0x57AADE,
    0x7FBF78,
    0x9C6E5A,
    0xF2CB6F,
    0x9DD1F2,
    0xAD70D5,
    0xF0A1C1,
    0x222222,
    0x646EAB
)

ICON_ATTACK = '⚔'
ICON_CLOSE = '❌'

EMOJI = {
    'nonono': '<a:nononohoney:660738866654740480>',
    'heimlichegg': '<:heimlichandegg:656164155069562881>',
    'flop': '<:woolooflop:661638062119452677>',
    'wooloo': '<:wooloo:650911948757532672>',

    'sword': '<:sword:662369277411721246>',
    'shield': '<:shield:662369277457989635>',

    'join': '<:memberjoin:663542559573803043>',
    'pin_unread': '<:pinunread:663544333210746902>',

    'pokeball': '<:pb:662385068613828628>',
    'masterball': '<:mb:662385068097929228>',
    'skip': '<:skip:662385111060185088>',
}

ANNOUNCE_EMOJI = ['<:wuwu:650913724068134923>',
    '<:woolooflop:650913724131049501>',
    '<a:wooloofast:652220524138725376>',
    '<:woocooloo:656493244930064419>',
    '<:stinkey:653658038296641537>',
    '<:squirtle:658799430916374544>',
    '<:PREMIERballguy:652594607053602826>',
    '<:jacob:653477874812059649>',
    '<:jacobsdog:652706135937122318>',
    '<:elliot:652655772185919488>',
    '<:lily:652655770869170197>',
    '<:honks:656493643690934273>'
]

pokeballUrl = 'http://play.pokemonshowdown.com/sprites/itemicons/poke-ball.png'

def strip_extra(s):
    return re.sub('[^\sA-Za-z]+', '', s)

def resolve_mention(server, query, getId=True, useNicks=False, stripExtra=False):
    if not query:
        return None

    match = idPattern.search(query)
    if match:
        uid = int(match.group(1))
        return uid if getId else server.get_member(uid)

    #todo cache haystack?
    query = query.lower().strip()
    haystack = [m.nick if useNicks and m.nick else m.name for m in server.members]

    matches = difflib.get_close_matches(query, haystack, n=1)
    if matches:
        member = server.get_member_named(matches[0])
        return member.id if getId else member

    return None

async def send_message(ctx, text, message=None, ping=True, error=False, color=None, expires=None):

    message = message or ctx.message

    if(error):
        text = f"{EMOJI['heimlichegg']}{EMOJI['nonono']} {text}"

    e = discord.Embed(description=text)
    if color or error:
        e.color = color if color else ERROR_RED
    if expires is None and error:
        expires = 10

    header = '<@{}>'.format(message.author.id) if ping else ''
    sent = await message.channel.send(header, embed=e, delete_after=expires)
    return sent


async def send_user_not_found(ctx, arg):
    await send_message(ctx, f'''Couldn't find a trainer in this server by that name!''', error=True)


def enquote(text):
    return f'“{text}”'


def ordinal(num, bold=False):
    if 10 <= num % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(num % 10, 'th')
    return "**{}**{}".format(num, suffix) if bold else str(num) + suffix


def clamp(n, lo, hi):
    return max(min(n, hi), lo)


def print_error(ctx, error):
    print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

def setup(bot):
    pass




