from slk import live, settings
from test_slk_radar import started, SAME, NEXT


def test_live_retains_same_day_with_legacy_settings_and_overrides():
    for stored in ({}, {'next_day_rule': 'require'}, {'next_day_rule': 'flag'}):
        cfg, _, vals = live.build_cfg(stored)
        assert cfg['next_day_rule'] == vals['next_day_rule'] == 'flag'
        assert started(SAME, next_day_rule=cfg['next_day_rule'])['next_day'] is False
        assert started(NEXT, next_day_rule=cfg['next_day_rule'])['next_day'] is True
    assert live.build_cfg({}, {'next_day_rule': 'require'})[0]['next_day_rule'] == 'flag'
    assert settings.as_strings({'next_day_rule': 'require'})['next_day_rule'] == 'flag'


def test_same_day_alert_warns_without_timing_veto():
    story = {**started(SAME, next_day_rule='flag'), 'pair': 'EURUSD'}
    row = live.to_row(story, 'CONFIRMED')
    text = live.format_alert('CONFIRMED', row)
    assert 'Lower probability:' in text
    assert 'This timing alone does not block entries' in text
    assert 'NO_TRADE' not in text
