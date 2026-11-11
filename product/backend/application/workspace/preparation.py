"""工作台与本次检查共用的准备建议；读取和范围均由调用者持有。"""
from product.backend.application.workspace.tasks import allow_control_task, PreparationTaskSelection
from product.backend.domain.recording.models import RecordingPurpose


def preparation_task(boundary, preparation, understanding, reading):
    selected = allow_control_task(preparation)
    if selected is not None:
        return selected
    candidates = []
    for action in sorted(preparation.actions, key=lambda item: item.action_id):
        selection = PreparationTaskSelection(boundary, action, understanding, reading.recordings)
        effects = {item.effect_id for item in action.effect_evidence}
        for recording in selection.current_recordings:
            if recording.resource_owner_test_identity_id not in selection.prepared_ids:
                continue
            if recording.purpose is RecordingPurpose.OBSERVATION and recording.effect_id not in effects:
                continue
            if recording.purpose is RecordingPurpose.RECOVERY and not action.assurance_contract.recovery_required:
                continue
            if reading.resumable(recording, selection.prepared_ids):
                selection.resume_recording(recording)
        selection.prepare_missing()
        selection.complete_materials(reading.parent_for(action))
        candidates.extend(selection.candidates)
    return min(candidates, key=lambda item: item[0])[1] if candidates else None
