from discord.ext import commands

creators = [232650437617123328, 105072331935727616, 647665702052036628]

wooloo_staff = [
    232650437617123328, # jacob
    105072331935727616, # notjacob
    647665702052036628, # rory
    177891276589498369, # kishi
    180708630054567936, # data
    474971416358551554, # elliott
    156306267080622080, # gengu
    247386293741289473, # bee
    175681718815031296, # sharkie
    133539944940437505, # deane
    137323245304152064, # zabe
    85165505505136640,  # suzu
]

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
        return ctx.message.author.id in creators
    return commands.check(predicate)


def is_mod():
    async def predicate(ctx):
        return await check_guild_permissions(ctx, {'manage_guild': True})
    return commands.check(predicate)


def is_bot_admin():
    async def predicate(ctx):
        # todo check ctx.bot.config.admin_roles
        return wooloo_staff_id(ctx.author.id) or await check_guild_permissions(ctx, {'administrator': True})
    return commands.check(predicate)


def wooloo_staff_id(uid):
    return uid in wooloo_staff


def is_wooloo_staff():
    async def predicate(ctx):
        return wooloo_staff_id(ctx.author.id)
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


def is_wooloo_farm():
    return is_in_guilds(649042459195867136, 660997103014903818)
