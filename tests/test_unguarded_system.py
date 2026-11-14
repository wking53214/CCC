"""A CCCSystem refuses to be built without a write permission or a human verifier unless the caller says so."""

import pytest

from ccc import Actor, CCCSystem
from ccc.errors import UnguardedSystemError, WritePermissionRefused, HumanVerificationRefused

YES = lambda request: True  # noqa: E731
NO = lambda request: False  # noqa: E731
ALLOW = dict(allow_unguarded_writes=True, allow_unverified_humans=True)


def test_construction_is_refused_with_neither():
    with pytest.raises(UnguardedSystemError):
        CCCSystem()


def test_construction_is_refused_without_a_write_permission():
    with pytest.raises(UnguardedSystemError, match="write_permission") as info:
        CCCSystem(human_verifier=YES)
    assert "allow_unguarded_writes=True" in str(info.value)


def test_construction_is_refused_without_a_human_verifier():
    with pytest.raises(UnguardedSystemError, match="human_verifier") as info:
        CCCSystem(write_permission=YES)
    assert "allow_unverified_humans=True" in str(info.value)


def test_each_flag_covers_only_its_own_piece():
    with pytest.raises(UnguardedSystemError):
        CCCSystem(allow_unguarded_writes=True)
    with pytest.raises(UnguardedSystemError):
        CCCSystem(allow_unverified_humans=True)
    CCCSystem(human_verifier=YES, allow_unguarded_writes=True)
    CCCSystem(write_permission=YES, allow_unverified_humans=True)


def test_the_flags_do_not_replace_a_given_guard():
    system = CCCSystem(write_permission=NO, human_verifier=NO, **ALLOW)
    with pytest.raises(WritePermissionRefused):
        system.ingest("note", actor=Actor.model("m"))
    assert system._human_verifier is NO


def test_a_real_permission_and_verifier_build_without_flags():
    system = CCCSystem(write_permission=YES, human_verifier=YES)
    assert system.ingest("note", actor=Actor.human("h")) is not None


def test_load_refuses_without_them_and_names_the_opt_out(tmp_path):
    path = CCCSystem(**ALLOW).save(tmp_path / "s.json")
    with pytest.raises(UnguardedSystemError, match="allow_unguarded_writes"):
        CCCSystem.load(path)
    with pytest.raises(UnguardedSystemError, match="allow_unverified_humans"):
        CCCSystem.load(path, write_permission=YES)
    with pytest.raises(UnguardedSystemError, match="allow_unguarded_writes"):
        CCCSystem.load(path, human_verifier=YES)


def test_load_keeps_what_it_is_given_and_accepts_the_flags(tmp_path):
    path = CCCSystem(**ALLOW).save(tmp_path / "s.json")
    guarded = CCCSystem.load(path, write_permission=NO, human_verifier=NO)
    assert guarded._write_permission is NO and guarded._human_verifier is NO
    with pytest.raises(WritePermissionRefused):
        guarded.ingest("note", actor=Actor.model("m"))
    with pytest.raises(HumanVerificationRefused):
        guarded.decide("d", actor=Actor.human("h"), reason="r", authorization_basis="b")
    open_system = CCCSystem.load(path, **ALLOW)
    assert open_system._write_permission is None and open_system._human_verifier is None


def test_the_error_is_a_ccc_error():
    from ccc.errors import CCCError
    assert issubclass(UnguardedSystemError, CCCError)
