import sys
sys.dont_write_bytecode = True
from integration_common import *
import pytest
import xml.etree.ElementTree as ET

source = ROOT / "tests/scripts/test_ptrans_published_attestation.py"
original_sha = sha(source)
assert original_sha == "3d7e27e2a220d80f6c75b75b46f49e7b3efd3ab258272d4b9cbe9a73f602e19d"
args = [
    "tests/scripts/test_ptrans_published_attestation.py", "-q", "-s", "-rsxX",
    "-p", "no:cacheprovider",
    "--basetemp=artifacts/m1_integration/independent_pt/scratch/pytest/publication",
    "--junitxml=artifacts/m1_integration/independent_pt/publication.xml",
]
event("four_original_publication_assertions_start", pytest_args=args,
      source_sha256=original_sha, plugins_supplied=[], input_retargeting=False)
rc = pytest.main(args)
assert sha(source) == original_sha
modules = [m for m in list(sys.modules.values())
           if getattr(m, "__file__", None) and Path(m.__file__).resolve() == source]
assert modules
assert all(m.EVIDENCE_ROOT == BUNDLE_ROOT and m.BUNDLE == PT for m in modules)
suite = ET.parse(OUT / "publication.xml").getroot().find("testsuite")
assert suite is not None
testcases = [{"classname": e.get("classname"), "name": e.get("name"),
              "duration_s": e.get("time"),
              "children": [child.tag for child in e]} for e in suite.findall("testcase")]
save("publication_test_result.json", {
    "exit_code": int(rc), "xml": "publication.xml", "xml_sha256": sha(OUT / "publication.xml"),
    "tests": int(suite.get("tests")), "errors": int(suite.get("errors")),
    "failures": int(suite.get("failures")), "skipped": int(suite.get("skipped")),
    "testcases": testcases,
    "actual_EVIDENCE_ROOT": str(BUNDLE_ROOT), "actual_BUNDLE": str(PT),
    "original_source_sha256": original_sha, "input_constants_modified": False,
    "custom_plugins_supplied": [], "pytest_args": args})
event("four_original_publication_assertions_complete", exit_code=int(rc),
      tests=suite.get("tests"), failures=suite.get("failures"),
      errors=suite.get("errors"), skipped=suite.get("skipped"), input_retargeting=False)
assert int(rc) == 0 and (suite.get("tests"), suite.get("errors"), suite.get("failures"),
                       suite.get("skipped")) == ("4", "0", "0", "0")
assert all(not e["children"] for e in testcases)
