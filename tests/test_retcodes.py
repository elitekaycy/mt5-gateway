import pytest
from retcodes import RetcodeClass, classify_retcode, success_state


@pytest.mark.parametrize(
    ("retcode", "state"),
    [(10008, "placed"), (10009, "executed"), (10010, "partially_executed")],
)
def test_success_retcodes(retcode, state):
    info = classify_retcode(retcode)

    assert info.is_success
    assert success_state(retcode) == state


@pytest.mark.parametrize("retcode", [10004, 10020, 10021, 10024, 10031])
def test_retryable_retcodes(retcode):
    assert classify_retcode(retcode).is_retryable


def test_timeout_is_ambiguous():
    assert classify_retcode(10012).is_ambiguous


@pytest.mark.parametrize("retcode", [10018, 10019, 10030])
def test_permanent_retcodes(retcode):
    assert classify_retcode(retcode).classification is RetcodeClass.PERMANENT


def test_unknown_retcode_is_ambiguous():
    info = classify_retcode(99999)

    assert info.is_ambiguous
    assert info.name == "UNKNOWN_99999"
