class BalancedPool(object):
    def __init__(self):
        self.group = []
        self.group_miss = []
        self.q = []
        self.mb = []
        self.made_it_in = []
        self.attempts = {}
        self.used_mb = []
        self.join_history = []
        self.kicked = []

    def size(self):
        return len(self.mb) + len(self.q) + len(self.made_it_in)

    def remove(self, uid):
        if uid not in self.join_history:
            return False

        removed = False
        for group in [self.mb, self.q, self.made_it_in]:
            try:
                group.remove(uid)
                removed = True
            except ValueError:
                pass

        return removed

    def get_next(self, n=1, advance=False):
        out = []

        mb_out = self.mb[:n]
        out.extend(('mb', uid) for uid in mb_out)

        if advance:
            self.mb = self.mb[n:]

        if len(out) < n:
            pb_out = self.q[:n - len(out)]
            out.extend(('pb', uid) for uid in pb_out)

            if advance:
                self.q[:] = self.q[len(pb_out):]

        return out


class Test:
    def __init__(self):
        self.pool = BalancedPool()
        self.round = 0

    def round(self):
        reinsert = []
        for (join_type, uid) in self.pool.group:
            if join_type == 'pb':
                if uid in self.pool.group_miss:
                    reinsert.append(uid)
                    self.pool.attempts[uid] = self.pool.attempts.get(uid, 0) + 1
                else:
                    self.pool.made_it_in.append(uid)
                    self.pool.attempts.pop(uid, None)

        self.pool.q = reinsert + self.pool.q
        size = self.pool.size()
        if size < 3:
            print('need more raiders')

        self.round += 1
        self.pool.group = self.pool.get_next(3, advance=True)d