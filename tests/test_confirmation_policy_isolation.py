"""Target policy identity must not decide structural confirmation geometry."""
from dataclasses import replace
from bishop.v2.stories import _confirm
from test_frozen_bias_reference import fixture


def test_id_relabeling_cannot_replace_earlier_semantic_confirmation():
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    baseline=_confirm(reaction,origin,'H4',lower,structure,(origin,),parents)
    renamed=replace(structure,events=tuple(replace(e,id='zzz' if e.reference_id==old.id else 'aaa') for e in structure.events))
    changed=_confirm(reaction,origin,'H4',lower,renamed,(origin,),parents)
    assert baseline[2].reference_id==changed[2].reference_id==old.id
    assert baseline[0]==changed[0]
    assert baseline[1]==changed[1]


def test_different_simultaneous_reference_geometry_remains_ambiguous():
    reaction,origin,lower,structure,parents,old,last,external=fixture()
    same=replace(structure.events[0],clock=external.clock)
    simultaneous=replace(structure,events=(same,external))
    assert _confirm(reaction,origin,'H4',lower,simultaneous,(origin,),parents) is None
    strict=_confirm(reaction,origin,'H4',lower,simultaneous,(origin,),parents,reference_profile='last_pre_touch')
    assert strict[2].reference_id==last.id
