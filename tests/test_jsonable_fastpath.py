"""Audit serialization keeps canonical types and stable causal identifiers."""
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from types import MappingProxyType
from bishop.v2.types import jsonable,stable_id

def test_primitive_fastpath_preserves_nested_canonical_json_and_ids():
    at=datetime(2026,1,5,tzinfo=timezone.utc)
    data={'a':(1,True,None,Decimal('1.25'),at,{'nested':2})}
    assert jsonable(data)=={'a':[1,True,None,'1.25','2026-01-05T00:00:00+00:00',{'nested':2}]}
    assert stable_id('jsonable-check',data)=='jsonable-check_1211b9508e7b0290d6f1533e'
    assert jsonable(MappingProxyType({None:'x',True:Decimal('2')}))=={'None':'x','True':'2'}
    assert jsonable((0.5,False))==[0.5,False]

def test_primitive_subclass_dataclass_still_serializes_its_fields():
    @dataclass
    class TaggedText(str):
        tag:str
    assert jsonable(TaggedText('demo'))=={'tag':'demo'}
