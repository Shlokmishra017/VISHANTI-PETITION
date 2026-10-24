import json
from app.ledger import append_event, verify_chain, GENESIS_PREV_HASH, get_actor_ref
from app.models import CaseEvent

def test_ledger_genesis_and_hash_chaining(db_session, fixtures):
    case = fixtures["case"]

    # verify genesis event
    events = db_session.query(CaseEvent).filter_by(case_id=case.id).all()
    assert len(events) == 1
    genesis = events[0]
    assert genesis.seq == 1
    assert genesis.prev_hash == GENESIS_PREV_HASH
    assert len(genesis.hash) == 64

    # append second event
    ev2 = append_event(
        db=db_session,
        case_id=case.id,
        event_type="NOTE_ADDED",
        actor_ref="official-1",
        payload={"note": "Exam sheet located in archives"}
    )
    db_session.commit()

    assert ev2.seq == 2
    assert ev2.prev_hash == genesis.hash

    # verify entire chain
    result = verify_chain(db_session, case.id)
    assert result["valid"] is True
    assert result["checked"] == 2
    assert result["first_broken_seq"] is None

def test_ledger_tamper_detection(db_session, fixtures):
    case = fixtures["case"]

    # append two subsequent events
    append_event(db_session, case.id, "STATUS_CHANGE", "official-1", {"state": "Assigned"})
    append_event(db_session, case.id, "STATUS_CHANGE", "official-1", {"state": "In Review"})
    db_session.commit()

    # verify clean chain first
    assert verify_chain(db_session, case.id)["valid"] is True

    # simulate tamper by modifying payload of seq 2
    ev2 = db_session.query(CaseEvent).filter_by(case_id=case.id, seq=2).one()
    tampered = json.loads(ev2.payload_json)
    tampered["state"] = "Resolved"
    ev2.payload_json = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    db_session.commit()

    # verification must fail and detect broken seq 2
    verification = verify_chain(db_session, case.id)
    assert verification["valid"] is False
    assert verification["first_broken_seq"] == 2
    assert verification["checked"] == 1

def test_actor_ref_anonymity():
    case_id = "test-case-123"
    ref1 = get_actor_ref(None, case_id)
    ref2 = get_actor_ref(None, case_id)

    # anonymous actor ref must be deterministic for the case but never leak identity
    assert ref1.startswith("anon_")
    assert ref1 == ref2
    assert len(ref1) == 21 # anon_ (5) + 16 chars

