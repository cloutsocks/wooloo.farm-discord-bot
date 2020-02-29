import re

import discord
import random
import sys

import discord
from discord.ext import commands

import checks
from common import send_message, EMOJI, FIELD_BREAK, emojiPattern, customEmojiPattern


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pets = 0
        self.max_pets = 3

    @checks.is_bot_admin()
    @commands.command()
    async def restart(self, ctx, arg=''):
        await ctx.send('Force restarting the botte, this should not be done often or repeatedly or you risk being blacklisted by Discord.')
        self.execute_restart(by_command=True)

    def execute_restart(self, by_command):
        print('[SYS] Restarting by command' if by_command else '[SYS] Restarting')
        sys.exit(1)

    async def remove_raw_reaction(self, payload, user=None):
        if not user:
            user = self.bot.get_user(payload.user_id)
            if not user:
                return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, user)

    @checks.is_wooloo_farm()
    @checks.is_bot_admin()
    @commands.command()
    async def raffle(self, ctx, n:int, msg_id:int, channel_id:int = 663479080192049172):
        channel = self.bot.get_channel(channel_id)
        msg = await channel.fetch_message(msg_id)

        for reaction in msg.reactions:
            users = await reaction.users().flatten()
            if len(users) <= n:
                # everyone is a winner!
                winners = users
            else:
                winners = random.sample(users, n)

            names = ', '.join([str(winner) for winner in winners])
            mentions = ' '.join([str(winner.mention) for winner in winners])

            await ctx.author.send(f'{reaction.emoji} {n} winner(s) for {reaction.count} submissions:\n{names}\n\nYou may copy and paste the following to easily tag them:\n```{mentions}```')

    @commands.command()
    async def pet(self, ctx):
        if self.pets > self.max_pets:
            return await ctx.send(f'''_Wooloo is all petted out and sleeping now._ {EMOJI['wooloo']}💤''')
        self.pets += 1
        if random.random() < 0.25:
            msg = f'''{EMOJI['heimlichegg']}💚💚'''
        else:
            em = random.choice([EMOJI['flop'], EMOJI['wuwu'], EMOJI['wooloo_fast']])
            msg = f'''{em}💙'''
        await ctx.send(f'{msg} _\\*is pet\\* _ x {self.pets}')

    @checks.is_bot_admin()
    @commands.command()
    async def maxpets(self, ctx, *, arg):
        try:
            self.max_pets = int(arg)
        except ValueError:
            return await send_message(ctx, 'Type a number.', error=True)
        await ctx.message.add_reaction('✅')

    @checks.is_bot_admin()
    @commands.command()
    async def resetpets(self, ctx):
        self.pets = 0
        await ctx.send('Done.')

    @commands.command()
    async def poll(self, ctx, *, arg):
        emoji = []

        if 'votes=' in arg:
            return await send_message(ctx, '''You don't need to do votes= for emoji anymore, I'll pull them automatically.''', error=True)

        emoji = list(re.findall(emojiPattern, arg, flags=re.DOTALL)) + list(re.findall(customEmojiPattern, arg, flags=re.DOTALL))
        msg = await ctx.send(f"**Poll time! <@{ctx.author.id}> asks:**\n{arg}")
        for reaction in emoji:
            await msg.add_reaction(reaction.strip('<> '))

    @commands.command()
    @checks.is_jacob()
    async def repeat(self, ctx, *, arg):
        await ctx.send(arg)

    @checks.is_bot_admin()
    @commands.command()
    async def say(self, ctx, channel:discord.TextChannel, *, arg):
        await channel.send(arg)
        await ctx.message.add_reaction('✅')

    @checks.is_wooloo_farm()
    @checks.is_bot_admin()
    @commands.command()
    async def tradesay(self, ctx, *, arg):
        msg = arg
        trade_category = self.bot.get_channel(650910708900298752)
        for channel in trade_category.text_channels:
            try:
                await channel.send(msg)
            except Exception as e:
                pass
        await ctx.send('Sent!')

    @commands.command()
    async def testmax(self, ctx, *, arg):
        lens = arg.split(' ')

        e = discord.Embed(title='Active Raiders', description='')
        for val in lens:
            lines = ['<@232650437617123328>'] * int(val)
            txt = '\n'.join(lines)
            e.add_field(name=str(val), value=txt, inline=False)
        await ctx.send(embed=e)

    # @commands.command()
    # @checks.is_jacob()
    # async def debugsay(self, ctx):
    #     pls_read = f'''\nPlease read <#665681669860098073> and the **pinned messages** or you will probably end up **banned** without knowing why. _We will not be undoing bans if you didn't read them._'''
    #
    #     ad_message = f'\n_This bot was developed by **jacob#2332** and **rory#3380** of <https://wooloo.farm/>\nFor bot suggestions, please visit <https://discord.gg/wooloo> _{FIELD_BREAK}'
    #     await ctx.channel.send(
    #                 f"{FIELD_BREAK}{EMOJI['join']} <@{ctx.author.id}> has joined the raid! {pls_read}\nsome cool info{FIELD_BREAK}{ad_message}")


def setup(bot):
    misc = Misc(bot)
    bot.add_cog(misc)
    bot.misc = misc
