class Pool(object):
    def __init__(self):
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
