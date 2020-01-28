from common import EMOJI, enquote


CREATE_HELP = '''_Creating a Raid_
`.host <mode> <channel name>`, where mode is set to `flexible`, `ffa`, or `queue` (defaults to `flexible` if omitted)
**+** _optional:_ `.host <channel name> "description goes here"` to set requirements (e.g. "leave after catching") or details (stats, etc)
**+** _optional:_ `.host <channel name> max=20` to limit raiders
**+** _optional:_ add `no mb` to disable priority masterball raiders
**+** _optional:_ add `private` to hide the code from lurkers
**+** _optional:_ add `locked` lock the raid until you unlock with `.lock`'''

HOST_COMMANDS = '''`.host help` to show these commands
`.fc <@user>` to display FC / IGN / Switch Name
`.queue` / `.q` to show the current queue in the channel for everyone to see
`.round <4 digit code>` to start a new round (you can _optionally_ re-use the code thereafter with `.round`)
`.skip @user` to skip and replace someone in the current round
`.remove @user` to remove (and skip) a user from this raid (they cannot rejoin!)
`.block @user` to remove (and skip) a user from **all** of your raids
`.group <msg>` to ping everyone in the current round's group with a message
`.end` to end the raid, i'll DM you a list of users to help you clean your friend list
`.pin` to pin your last message
`.unpin <#>` to unpin a message
`.max <#>` to adjust max participants
`.lock` to temporarily prevent new raiders from joining (without stopping the raid)
`.private` to toggle a private raid (hidden codes from lurkers)
`.qfc` show the current queue WITH fc / switch name
[**NEW**]
`.poll <poll message> votes=🐄,🐈,🐖,🦌` to make a poll with reactions
`.echo <tag> <message goes here>` to set an echo
`.echo <tag>` to have the botte repeat it
'''

RAID_NOT_FOUND = '''You can only do this in an active raid channel. If this _was_ a raid channel, it has been disconnected from the botte, but the host can remake it from scratch. We're exploring possible options to handle this more gracefully.'''


def make_readme(mode, desc, active_raids_id):
    notice = f"\n\nThe host expects everyone to know the following: _{enquote(desc)}_" if desc else ""

    # todo message limit

    # standard / queue
    if mode == 0 or mode == 2:
        return [f'''{EMOJI["wooloo"]} **Everyone, Read This Carefully** {EMOJI["wooloo"]}

I help manage raids! Everyone gets a turn in the order they joined, with {EMOJI["masterball"]} getting priority. Even if you don't catch it, it still counts as a turn. But don't worry! Once we cycle through everyone, we start the queue over.{notice}
''',

f'''
**For Participants**
_Commands_
`.queue` / `.q` to have the current queue DM'd to you
`.caught` to indicate you've caught the Pokémon
`.code` to view the code (if set)
`.leave` to leave the raid

{EMOJI['check']} **1**)  if you don't follow instructions, you might get kicked or blocked by the host
{EMOJI['check']} **2**)  enter this raid by visiting <#{active_raids_id}>
{EMOJI['check']} **3**)  do not join until instructed to do so by the botte
{EMOJI['check']} **4**)  don't ask the host to join, for their friend code, or what the raid code is—**i'll tell you all of that when it's your turn** {EMOJI["flop"]}
{EMOJI['check']} **5**)  when you're done raiding, you **have** to leave the raid by **unclicking** the {EMOJI["pokeball"]} or {EMOJI["masterball"]} in <#{active_raids_id}> or by typing `.leave`
{EMOJI['check']} **6**)  you must also **remove the host from your friend's list**, even if you intend to raid with them again later!
{EMOJI['check']} **7**)  **you can rejoin** at any time (unless you've used a {EMOJI["masterball"]})
{EMOJI['check']} **8**)  hosts are completely free to remove users for **any reason whatsoever, no questions asked**! this is their room and they do not have to host you.
{EMOJI['check']} **9**)  don't react to a kick or block! **hosts do not have to explain why they blocked you.** if this happens, please contact mods.
{EMOJI['check']} **10**)  if you joined with a {EMOJI["pokeball"]}, you can switch to a masterball **once** by going back to <#{active_raids_id}> and clicking the {EMOJI["masterball"]} (but you better use one or you'll get blocked!)
{EMOJI['check']} **11**)  when you've caught the Pokémon, please write `.caught`!
{EMOJI['check']} **12**)  please `.pet`. me
''',

f'''
**For Hosts**
_Commands_
{HOST_COMMANDS}

{EMOJI['check']} **1**)  you can `.remove` / `.block` someone for **any reason**, no questions asked! don't hesitate
{EMOJI['check']} **2**)  if someone is unnecessarily greedy, hostile, joins out of order, spammy or worse - just `block` them
{EMOJI['check']} **3**)  if a trainers "forgets" to use their masterball when they sign up as {EMOJI["masterball"]} _definitely_ block them
{EMOJI['check']} **4**)  **do not go afk when hosting!** _you cannot pause raids._ if you wait 30 minutes, it's likely many of the users in your pool will be away and the whole thing falls apart
{EMOJI['check']} **5**)  you can, however, `.end` the raid and create a new one when you're back! it'll work just as good :))
{EMOJI['check']} **6**)  `.skip` `.remove` or `.block` anyone who is afk during their turn (removed and blocked users **cannot rejoin**)
''']

    # ffa
    if mode == 1:
        return [ f'''{EMOJI["wooloo"]} **Everyone, Read This Carefully** {EMOJI["wooloo"]}

This is a **free-for-all** raid! There is no queue, but follow the instructions of the host.{notice}
''',

f'''
**For Participants**
_Commands_
`.queue` / `.q` to have the current queue DM'd to you
`.caught` to indicate you've caught the Pokémon
`.code` to view the code (if set)
`.leave` to leave the raid

{EMOJI['check']} **1**)  if you don't follow instructions, you might get kicked or blocked by the host
{EMOJI['check']} **2**)  enter this raid by visiting <#{active_raids_id}>
{EMOJI['check']} **3**)  when you're done raiding, you **have** to leave the raid by **unclicking** the {EMOJI["pokeball"]} or {EMOJI["masterball"]} in <#{active_raids_id}> or by typing `.leave`
{EMOJI['check']} **4**)  you must also **remove the host from your friend's list**, even if you intend to raid with them again later!
{EMOJI['check']} **5**)  hosts are completely free to remove users for **any reason whatsoever, no questions asked**! this is their room and they do not have to host you.
{EMOJI['check']} **6**)  don't react to a kick or block! **hosts do not have to explain why they blocked you.** if this happens, please contact mods.
{EMOJI['check']} **7**)  when you've caught the Pokémon, please write `.caught`!
{EMOJI['check']} **8**)  please `.pet`. me
''',

f'''
**For Hosts**
_Commands_
{HOST_COMMANDS}

{EMOJI['check']} **1**)  you can `.remove` / `.block` someone for **any reason**, no questions asked! don't hesitate
{EMOJI['check']} **2**)  if someone is unnecessarily greedy, hostile, joins out of order, spammy or worse - just `.block` them
{EMOJI['check']} **3**)  **do not go afk when hosting!** _you cannot pause raids._
{EMOJI['check']} **4**)  you can, however, `.end` the raid and create a new one when you're back! it'll work just as good :))
''']


def make_error_msg(err, uid):
    if err == 'WF_NO_ACCOUNT':
        msg = 'You do not have a linked profile on http://wooloo.farm/ ! In order to raid, you must link a **public** (not marked private) discord account with your 🗺️ **friend code**, ✨ **in-game name**, and 🎮 **switch name**. This allows others to quickly add or verify you during a chaotic raid.'

    elif err.startswith('WF_NOT_SET'):
        key = err.split(': ')[1]
        msg = f'Your {key} is not set on http://wooloo.farm/profile/edit , please update it accordingly. In order to raid, you must link a **public** (not marked private) discord account with your 🗺️ **friend code**, ✨ **in-game name**, and 🎮 **switch name**. This allows others to quickly add or verify you during a chaotic raid.'

    elif err.startswith('WF_NO_IGN'):
        msg = f'Your in-game name is not set on http://wooloo.farm/profile/edit , please update it accordingly. This is the trainer name that appears in-game. If you own both games, both can be stored.'

    elif err == 'ROLE_BANNED_FROM_RAIDING':
        msg = 'You are currently banned from raiding on the server. You will not be able to join or host any raids.'

    elif err == 'ROLE_BANNED_FROM_HOSTING':
        msg = 'You are currently banned from hosting raids on the server. You will be able to join raids, but you cannot host your own.'

    else:
        msg = f'An unknown error {err} is preventing that action for your account. Please contact jacob#2332 with this error message.'

    return f"<@{uid}> {msg} {EMOJI['flop']}"
