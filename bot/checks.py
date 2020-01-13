from discord.ext import commands


async def check_permissions(ctx, perms, *, check=all):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    resolved = ctx.channel.permissions_for(ctx.author)
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def has_permissions(*, check=all, **perms):
    async def predicate(ctx):
        return await check_permissions(ctx, perms, check=check)
    return commands.check(predicate)


async def check_guild_permissions(ctx, perms, *, check=all):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def has_guild_permissions(*, check=all, **perms):
    async def predicate(ctx):
        return await check_guild_permissions(ctx, perms, check=check)
    return commands.check(predicate)

# These do not take channel overrides into account


def is_jacob():
    def predicate(ctx):
        return ctx.message.author.id in [232650437617123328, 105072331935727616, 647665702052036628]
    return commands.check(predicate)


def is_mod():
    async def predicate(ctx):
        return await check_guild_permissions(ctx, {'manage_guild': True})
    return commands.check(predicate)


def is_admin():
    async def predicate(ctx):
        return await check_guild_permissions(ctx, {'administrator': True})
    return commands.check(predicate)


def mod_or_permissions(**perms):
    perms['manage_guild'] = True
    async def predicate(ctx):
        return await check_guild_permissions(ctx, perms, check=any)
    return commands.check(predicate)


def admin_or_permissions(**perms):
    perms['administrator'] = True
    async def predicate(ctx):
        return await check_guild_permissions(ctx, perms, check=any)
    return commands.check(predicate)


def is_in_guilds(*guild_ids):
    def predicate(ctx):
        guild = ctx.guild
        if guild is None:
            return False
        return guild.id in guild_ids
    return commands.check(predicate)