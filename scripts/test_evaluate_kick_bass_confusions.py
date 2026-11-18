import importlib.util
from pathlib import Path

p=Path(__file__).with_name("evaluate_kick_bass_confusions.py")
spec=importlib.util.spec_from_file_location("kick_metrics",p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_kick_miss_and_two_bass_confusions_are_separate():
    refs=[
        {"track":"song","time_seconds":"1.0","annotation_label":"kick","decision":"accept"},
        {"track":"song","time_seconds":"2.0","annotation_label":"bass_guitar","decision":"accept"},
        {"track":"song","time_seconds":"3.0","annotation_label":"bass_synth_808","decision":"accept"},
        {"track":"song","time_seconds":"4.0","annotation_label":"kick","decision":"reject"},
    ]
    preds=[
        {"track":"song","arm":"cnn","time_seconds":"1.02","event_status":"prediction"},
        {"track":"song","arm":"cnn","time_seconds":"2.03","event_status":"prediction"},
        {"track":"song","arm":"cnn","time_seconds":"3.01","event_status":"prediction"},
    ]
    result=m.evaluate(refs,preds,.05)["arms"]["cnn"]["overall"]
    assert result["kick_reference_events"]==1
    assert result["kick_matched"]==1 and result["kick_missed"]==0
    assert result["bass_guitar_confused_as_kick"]==1
    assert result["bass_synth_808_confused_as_kick"]==1

def test_unmatched_prediction_is_not_assumed_to_be_bass():
    refs=[{"track":"song","time_seconds":"1","annotation_label":"kick","decision":"accept"}]
    preds=[{"track":"song","arm":"cnn","time_seconds":"5","event_status":"prediction"}]
    result=m.evaluate(refs,preds,.05)["arms"]["cnn"]["overall"]
    assert result["kick_missed"]==1
    assert result["unmatched_kick_predictions"]==1
    assert result["bass_guitar_confused_as_kick"]==0
    assert result["bass_synth_808_confused_as_kick"]==0
