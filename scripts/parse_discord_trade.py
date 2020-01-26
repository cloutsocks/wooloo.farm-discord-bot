import re

'''

type Mon struct {
	Species  null.Int64 `json:"species"`
	Form     null.Int64 `json:"form"`
	Shiny    null.Int64 `json:"shiny"`
	Level    int64      `json:"level"`
	Gender   int64      `json:"gender"`
	Ability  null.Int64 `json:"ability"`
	HeldItem null.Int64 `json:"held_item"`
	Nature   null.Int64 `json:"nature"`
	Lang     string     `json:"lang"`
	Moves    []int64    `json:"moves"`
	Ball     null.Int64 `json:"ball"`

	IVHP    null.Int64 `json:"iv_hp"`
	IVAtk   null.Int64 `json:"iv_atk"`
	IVDef   null.Int64 `json:"iv_def"`
	IVSpAtk null.Int64 `json:"iv_spatk"`
	IVSpDef null.Int64 `json:"iv_spdef"`
	IVSpd   null.Int64 `json:"iv_spd"`

	NIVs int64 `json:"n_ivs"`

	InvertLang bool `json:"invert_lang"`
}

'''

class HostedRaid(object):
    def __init__(self):
        self.species = None
        self.form = None
        self.shiny = False
        self.level = None
        self.gender = None
        self.ability = None
        self.held_item = None
        self.nature = None
        self.lang = None
        self.moves = None
        self.ball = None
        self.n_iv = None

    def parse_moves(self, txt):
        pass



'''

FT: <parse>
LF: <parse>


captures:
- multiline
- comma separated per pokemon (not \n)

first catch and remove:
- 1-6iv
- lv(\d) (and variants)
- male/female
- shiny
- HA
- (\w) nature
- EN / JP etc
- [move1] [move 1, move 2] etc

format for held items? non-ha ability? (check against list of all items and abilities?)

'''

msgs = [
    '''LF: Shiny Rookidee/Corvisquire/Corviknight (prefer HA)
FT: Various Apriballs, Ability Capsule, Mint of choice, Shiny Centiskorch (not G-Max), Gigantamix, Enternatus. (Almost done with post game to get Zamazenta and shield)'''
]


def should_parse(msg):
    haystack = msg.lower()
    return 'ft:' in haystack and 'lf:' in haystack

def parse_msg(msg):
    haystack = msg.lower()

    m = re.search(r'max=(\d*)', arg)
    if m:
        try:
            max_joins = int(m.group(1))
        except ValueError:
            return await send_message(ctx,
                                      'Invalid value for max raiders. Include `max=n` or leave it out for `max=30`',
                                      error=True)
        arg = arg.replace(m.group(0), '')
