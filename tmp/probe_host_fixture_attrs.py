from scipy.io import loadmat

mat = loadmat("data/karr_fixtures/per_process/HostInteraction_flat.mat", squeeze_me=True, struct_as_record=False)
fx = mat["data"].fixture
for attr in [
    "enzymeIndexs_tlr12Ligand",
    "enzymeIndexs_tlr26Ligand",
    "enzymeIndexs_antigen",
    "enzymeIndexs_adhesin",
    "enzymeIndexs_terminalOrganelle",
]:
    print(attr, getattr(fx, attr))
