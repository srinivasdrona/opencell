from opencell.vivarium.karr_metabolism import KarrMetabolismProcess
p = KarrMetabolismProcess({'rng_seed': 0})
attrs = sorted([a for a in dir(p) if not a.startswith('_')])
print('All attrs:')
for a in attrs:
    try:
        v = getattr(p, a)
        if hasattr(v, '__len__') and not callable(v):
            print(f'  {a}: len={len(v)}')
    except Exception:
        pass
