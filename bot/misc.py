import re

import discord
import random
import sys
import asyncio
import texts

import demoji
import discord
from discord.ext import commands

import checks
from common import send_message, EMOJI, FIELD_BREAK, idPattern, emojiPattern, customEmojiPattern


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pets = 0
        self.max_pets = random.randint(5, 420)

    @checks.is_bot_admin()
    @commands.command()
    async def admin(self, ctx):
        return await ctx.send(texts.ADMIN_HELP)

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

    @commands.command()
    @commands.dm_only()
    @commands.cooldown(1, 180.0, type=commands.BucketType.user)
    async def raffle(self, ctx, *, arg=''):
        try:
            n = int(arg)
            if n < 1 or n > 100:
                raise ValueError
        except ValueError:
            ctx.command.reset_cooldown(ctx)
            return await send_message(ctx, f'Please specify the number of winnners, i.e. `.raffle 1` or `.raffle 3`', error=True)
        cns = [702573798309888150, 663479080192049172]
        # cns = [685642926205960227, 709456316787064834]

        nums = ['1️⃣', '2️⃣', '3️⃣', '4️⃣'][:len(cns)]
        cn_text = '\n'.join([f'{nums[i]} <#{cid}>' for i, cid in enumerate(cns)])
        prompt = await ctx.send(f'Select a channel that contains your raffle post with the words `Raffle Time!`:\n\n{cn_text}')
        for i, cn in enumerate(cns):
            await prompt.add_reaction(nums[i])

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == prompt.id and str(reaction.emoji) in nums
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send('You took too long to make a selection.')
            return

        cid = cns[nums.index(str(reaction.emoji))]
        not_found = f'I could not find a message from you in the selected raffle channel <#{cid}> that has the phrase `Raffle Time!` within the last 100 messages. Either edit the post to include `Raffle Time!` or conduct the raffle yourself.'
        channel = self.bot.get_channel(cid)
        msg = await channel.history(limit=300).get(author__id=ctx.author.id)
        if not msg or 'raffle time!' not in msg.content.lower():
            await ctx.send(not_found)
            return

        if not msg.reactions:
            return await send_message(ctx, f'Your last raffle post does not have any reactions on it.', error=True)

        for reaction in msg.reactions:
            users = await reaction.users().flatten()
            if len(users) <= n:
                # everyone is a winner!
                winners = users
            else:
                winners = random.sample(users, n)

            names = ', '.join([str(winner) for winner in winners])
            mentions = ' '.join([str(winner.mention) for winner in winners])

            await ctx.author.send(f'{reaction.emoji} {n} winner(s ) for {reaction.count} submissions:\n{names}\n\nYou may copy and paste the following to easily tag them:\n```{mentions}```')


    @commands.command()
    async def pet(self, ctx):
        if self.pets > self.max_pets:
            return await ctx.send(f'''_Wooloo is all petted out and sleeping now._ {EMOJI['wooloo']}💤''')
        self.pets += 1
        if random.random() < 0.15:
            msg = f'''{EMOJI['weepinbegg']}💚💚'''
        else:
            em = random.choice([EMOJI['woopet'], EMOJI['woopet'], EMOJI['woopet'], EMOJI['wowloo'], EMOJI['wowloo'], EMOJI['wooletter'], EMOJI['flop'], EMOJI['wuwu'], EMOJI['wooloo_fast']])
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

        # emoji = list(re.findall(emojiPattern, arg, flags=re.DOTALL)) + list(re.findall(customEmojiPattern, arg, flags=re.DOTALL))
        emoji = list(demoji.findall(arg).keys()) + list(re.findall(customEmojiPattern, arg, flags=re.DOTALL))
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

    @checks.is_bot_admin()
    @commands.command()
    async def msg(self, ctx, *, arg):

        try:
            uid, msg = arg.split(' ', 1)
        except ValueError:
            await send_message(ctx, 'Please include a message to send. Usage: `.msg <user: id or tagged> <msg>', error=True)
            return

        match = idPattern.search(uid)
        if match:
            uid = int(match.group(1))
        else:
            try:
                uid = int(uid)
            except ValueError:
                await send_message(ctx, 'Please include a message to send. Usage: `.msg <user: id or tagged> <msg>', error=True)
                return

        member = ctx.message.guild.get_member(uid)
        if not member:
            await ctx.send(f'Member <@{uid}> not found on this server. Syntax is `.msg <user: id or tagged> <msg>')
            return

        prompt = await ctx.send(f'Click ✅ within 60 seconds to message {member} with:\n\n{msg}')
        await prompt.add_reaction('✅')

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == prompt.id and str(reaction.emoji) == '✅'
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            pass
        else:

            try:
                await member.send(msg)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                await ctx.send(f'Could not message user. Error: {type(e).__name__}, {e}')
                return

            await ctx.send('Sent successfully!')


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

    @checks.is_wooloo_farm()
    @checks.is_bot_admin()
    @commands.command()
    async def acsay(self, ctx, *, arg):
        msg = arg
        trade_category = self.bot.get_channel(697581143066804306)
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
