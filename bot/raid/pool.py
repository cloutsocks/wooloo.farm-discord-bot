class IndexPool(object):
    def __init__(self):
        self.i = 0
        self.q = []
        self.mb = []
        self.used_mb = []
        self.join_history = []
        self.kicked = []

    def size(self):
        return len(self.mb) + len(self.q)

    def remove(self, uid):
        if uid not in self.join_history:
            return False

        removed = False
        if uid in self.mb:
            self.mb.remove(uid)
            removed = True

        try:
            index = self.q.index(uid)
            if index < self.i:
                self.i -= 1
            self.q.remove(uid)
            removed = True

        except ValueError:
            pass

        return removed

    def as_text(self):
        return f'''mb {self.mb}
pb {self.q}
used_mb {self.used_mb}'''

    def get_next(self, n=1, advance=False):

        mb_out = self.mb[:n]
        out = [('mb', uid) for uid in mb_out]

        if advance:
            self.mb = self.mb[n:]

        wraparound = False
        end = self.i + n - len(out)
        out += [('pb', uid) for uid in self.q[self.i:end]]
        if len(out) < n:
            wraparound = True
            end = remaining = n - len(out)
            out += [('pb', uid) for uid in self.q[0:remaining]]

        if advance:
            self.i = end
            # self.q += mb_out

        return out, wraparound