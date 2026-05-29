import json, sys
for p in ['data/karr_fixtures/per_process/Metabolite.json',
          'data/karr_fixtures/per_process/Metabolism.json',
          'data/karr_fixtures/per_process_replay/Metabolism.json']:
    try:
        d = json.load(open(p))
        if isinstance(d, dict):
            print(f'\n=== {p}: top keys = {list(d.keys())[:15]}')
            for k in d:
                v = d[k]
                if isinstance(v, list):
                    print(f'  {k}: list len={len(v)}, head={v[:5]}')
                elif isinstance(v, dict):
                    sub = list(v.keys())[:15]
                    print(f'  {k}: dict, {len(v)} keys, sample={sub}')
                    # look for substrate-related sub-keys
                    for sk in v:
                        if 'substrate' in sk.lower() or 'wholecellmodel' in sk.lower():
                            sv = v[sk]
                            if isinstance(sv, list):
                                print(f'    .{sk}: list len={len(sv)}, head={sv[:20]}')
                                if 'ADP' in sv[:50]:
                                    print(f'    --> ADP at index {sv.index("ADP")}')
                            elif isinstance(sv, (str, int, float)):
                                print(f'    .{sk}: {sv}')
                else:
                    print(f'  {k}: {type(v).__name__} = {str(v)[:80]}')
    except Exception as e:
        print(f'{p}: ERR {e}')

