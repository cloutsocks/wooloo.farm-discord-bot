class Pool(object):
    def __init__(self):
        self.group = []
        self.q = []
        self.mb = []
        self.used_mb = []
        self.join_history = []
        self.kicked = []
        self.group_miss = []

    def size(self):
        return len(self.mb) + len(self.q) + len(self.group)

    def in_group(self, uid):
        uids = [t['uid'] for t in self.group]
        return id in uids

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

    def get_next(self, n=1, advance=False):
        out = [{**x, 'attempts': x['attempts'] + 1} for x in self.group if x['uid'] in self.group_miss]

        mb_out = self.mb[:n - len(out)]
        out.extend({'uid': uid, 'join_type': 'mb', 'attempts': 0} for uid in mb_out)

        if advance:
            self.mb = self.mb[len(mb_out):]

        if len(out) < n:
            pb_out = self.q[:n - len(out)]
            out.extend({'uid': uid, 'join_type': 'pb', 'attempts': 0} for uid in pb_out)

            if advance:
                self.q[:] = self.q[len(pb_out):]

        if advance:
            self.group_miss.clear()

        return out

    def add_miss(self, uid):
        self.group_miss.append(uid)