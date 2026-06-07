from tests.vivarium import _l2_2_design_a_runner_helpers as h

p = h._translation_process(0)
names = tuple(sorted(vars(p)))
stateful = tuple(name for name in names if "ribosome" in name.lower() or "bound" in name.lower())
print("attrs", names)
print("ribosome_or_bound_attrs", stateful)
