import time
from contextlib import contextmanager


class StageTimer:
    def __init__(self):
        self.totals = {}

    @contextmanager
    def stage(self, name):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.totals[name] = self.totals.get(name, 0.0) + \
                                (time.perf_counter() - t0)

    def snapshot(self):
        return dict(self.totals)