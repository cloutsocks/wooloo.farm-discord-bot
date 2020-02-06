import discord
import random

import discord
from discord.ext import commands

import checks
from common import send_message, EMOJI


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pets = 0
        self.max_pets = 3

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
        # todo fix this
        reaction = msg.reactions[0]
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

    @checks.is_wooloo_farm()
    @checks.is_bot_admin()
    @commands.command()
    async def gohome(self, ctx):
        await self.bot.get_channel(652367800912052244).send(f'''pls remember to move off topic chat to <#649042720458932234> ! so we can keep this channel about raiding {EMOJI['flop']}''')
        await ctx.message.add_reaction('✅')

    @commands.command()
    async def poll(self, ctx, *, arg):
        emoji = []
        if 'votes=' in arg:
            arg, votes = arg.split('votes=')
            emoji = votes.split(',')

        msg = await ctx.send(arg)
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


def setup(bot):
    misc = Misc(bot)
    bot.add_cog(misc)
    bot.misc = misc
