import random
from collections import namedtuple

# Raider = namedtuple('Raider', ['uid', 'join_type', 'attempts'], defaults=[0])

class BalancedPool(object):
    def __init__(self):
        self.group = []
        self.group_miss = []
        self.q = []
        self.mb = []
        self.used_mb = []
        self.join_history = []
        self.kicked = []

    def __repr__(self):
        return f'''
group: {self.group}
group_miss: {self.group_miss}
q: {self.q}
mb: {self.mb}
'''

    def size(self):
        return len(self.mb) + len(self.q)

    def remove(self, uid):
        if uid not in self.join_history:
            return False

        removed = False
        for collection in [self.mb, self.q]:
            try:
                collection.remove(uid)
                removed = True
            except ValueError:
                pass

        return removed

    def get_next(self, n=1, advance=False, retain=None):
        if retain is None:
            retain = []

        out = [{**x, 'attempts': x['attempts'] + 1} for x in self.group if x['uid'] in retain]

        mb_out = self.mb[:n - len(out)]
        out.extend({'uid': uid, 'join_type': 'mb', 'attempts': 0} for uid in mb_out)

        if advance:
            self.mb = self.mb[len(mb_out):]

        if len(out) < n:
            pb_out = self.q[:n - len(out)]
            out.extend({'uid': uid, 'join_type': 'pb', 'attempts': 0} for uid in pb_out)

            if advance:
                self.q[:] = self.q[len(pb_out):]

        return out

class Test:
    def __init__(self):
        self.pool = BalancedPool()
        self.round = 0
        self.pool.q = [str(i + 1) for i in range(30)]

        for i in range(20):
            self.do_round()
            print(f'Rd {self.round}')
            print(self.pool)
            for raider in self.pool.group:
                if raider['join_type'] == 'pb':
                    if random.random() < 0.5:
                        self.pool.group_miss.append(raider['uid'])
                        # self.pool.group = [raider for raider in self.pool.group if raider[1] != uid]

            print(f'Misses: {self.pool.group_miss}')
            print('\n\n')





    def do_round(self):
        reinsert = []
        for raider in self.pool.group:
            if raider['join_type'] == 'pb':
                # print(uid, uid in self.pool.group_miss, self.pool.group_miss)
                if raider['uid'] in self.pool.group_miss:
                    reinsert.append(raider['uid'])
                    raider['attempts']
                    raider = raider._replace(attempts=raider['attempts']+1)
                else:
                    self.pool.q.append(raider['uid'])

        self.pool.q = reinsert + self.pool.q
        size = self.pool.size()
        if size < 3:
            print('need more raiders')

        # if not self.pool.mb and not self.pool.q:
        #     print('=== Everyone In! Refresh ===')
        #     self.pool.q = self.pool.made_it_in[:]
        #     self.pool.made_it_in = []

        self.round += 1
        self.pool.group = self.pool.get_next(5, advance=True)
        self.pool.group_miss = []

test = Test()