"""Inspect iPS189 species naming to plan subnetwork selection."""
import libsbml

m = libsbml.SBMLReader().readSBML(r"E:\opencell\data\m1_sources\iPS189.xml").getModel()

print("--- first 25 species ---")
for i in range(min(25, m.getNumSpecies())):
    s = m.getSpecies(i)
    name = (s.getName() or "")[:40]
    print(f"  {s.getId():25}  {name:40}  cmp={s.getCompartment()}")

print()
print("--- M1-relevant species (greedy match) ---")
keys = ["glc","g6p","f6p","fdp","dhap","g3p","13dpg","3pg","2pg","pep","pyr",
        "atp","adp","amp","nad","nadh","nadp","nadph",
        "lac","ac_","accoa","actp","coa","pi","h2o","h_","ppi"]
hits = []
for i in range(m.getNumSpecies()):
    s = m.getSpecies(i)
    sid = s.getId().lower()
    name = (s.getName() or "").lower()
    for k in keys:
        if k in sid:
            hits.append((s.getId(), s.getName(), s.getCompartment()))
            break

for sid, name, cmp in sorted(hits):
    print(f"  {sid:25}  {(name or '')[:38]:38}  {cmp}")

print(f"\ntotal hits: {len(hits)}")

# Now look at reactions whose ALL species are in the hits set
hit_set = {h[0] for h in hits}
print()
print("--- reactions fully inside hit set ---")
n = 0
for i in range(m.getNumReactions()):
    rx = m.getReaction(i)
    species = set()
    for j in range(rx.getNumReactants()):
        species.add(rx.getReactant(j).getSpecies())
    for j in range(rx.getNumProducts()):
        species.add(rx.getProduct(j).getSpecies())
    if species and species.issubset(hit_set):
        rs = " + ".join(f"{rx.getReactant(j).getStoichiometry():g} {rx.getReactant(j).getSpecies()}"
                        for j in range(rx.getNumReactants()))
        ps = " + ".join(f"{rx.getProduct(j).getStoichiometry():g} {rx.getProduct(j).getSpecies()}"
                        for j in range(rx.getNumProducts()))
        arrow = "<->" if rx.getReversible() else "-->"
        print(f"  {rx.getId():12}  {rs}  {arrow}  {ps}")
        n += 1
print(f"\ntotal subnetwork reactions: {n}")
