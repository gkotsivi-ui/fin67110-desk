"""Elapsed times for run parts, including failures and cached reads."""
from contextlib import contextmanager
import re
import time
from pathlib import Path
from desk_sources import write_json


@contextmanager
def elapsed(run, name):
    began=time.perf_counter()
    try:
        yield
    finally:
        seconds=time.perf_counter()-began
        if run:
            key=re.sub(r'[^A-Za-z0-9_-]+','_',name)
            write_json(Path(run)/'timings'/f'{key}_{time.time_ns()}.json',
                       {'part':name,'seconds':seconds})
        print(f'Part {name}: {seconds:.3f} seconds',flush=True)


def timed_role(method):
    def call(self, role, *args, **kwargs):
        with elapsed(getattr(self,'output_dir',None),'role '+role):
            return method(self,role,*args,**kwargs)
    return call
