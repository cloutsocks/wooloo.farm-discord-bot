import difflib
import re
import sys
import traceback

import discord

idPattern = re.compile(r'<@!?(\d+?)>')
emojiPattern = re.compile(u'([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])')
customEmojiPattern = re.compile(r':[0-9]{8}')

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
    'wuwu': '<:wuwu:676228384615038988>',
    'flop': '<:woolooflop:676228385642381322>',
    'wooloo_fast': '<a:wooloofast:676228383528714240>',
    'wooloo': '<:wooloo:676228383411273769>',
    'cooloo': '<:woocooloo:676228383457280001>',
    'stinkey': '<:stinkey:676228383159615520>',
    'skip': '<:skip:676228383268667452>',
    'ballguy': '<:PREMIERballguy:676228385927594004>',
    'sword': '<:pkmnsw:676228382870077471>',
    'shield': '<:pkmnsh:676228382886723595>',
    'pin_unread': '<:pinunread:676228383289507881>',
    'pokeball': '<:pb:676228383201296414>',
    'nonono': '<a:nononohoney:676228383419662377>',
    'join': '<:memberjoin:676228383058690108>',
    'masterball': '<:mb:676228383218204672>',
    'lovehonk': '<:lovehonk:676228729097289748>',
    'lily': '<:lily:676228383100764160>',
    'jacobsdog': '<:jacobsdog:676228383998476318>',
    'jacob': '<:jacob:676229001416671281>',
    'honk': '<:honks:676228382996037658>',
    'elliot': '<:elliot:676228383146770436>',
    'discord': '<:discord:676228382895243282>',
    'check': '<:checkfilled:676228383566462976>',
    'check_empty': '<:checkempty:676228383062884364>',
    'heimlichegg': '<:heimlichandegg:676228382811226124>',
}

escuchameUrl = 'https://i.imgur.com/dJGmQXr.png'
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

async def send_message(ctx, text, message=None, ping=True, error=False, color=None, image_url=None, expires=None):

    message = message or ctx.message

    if(error):
        text = f"{EMOJI['heimlichegg']}{EMOJI['nonono']} {text}"

    e = discord.Embed(description=text)
    if color or error:
        e.color = color if color else ERROR_RED
    if expires is None and error:
        expires = 10
    if image_url is not None:
        e.set_image(url=image_url)

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




