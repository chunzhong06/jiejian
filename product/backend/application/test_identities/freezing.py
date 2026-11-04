"""正式检查和试运行共用的无秘密身份快照；实际主体仍由Runner核验。"""
from product.backend.domain.identities.models import identity_source_fingerprint


def freeze_check_identity(record,binding,actor_label,verification,*,environment):
    actual=None if verification is None else verification.model_dump(mode='json')
    if environment is not None and record.authentication is not None:
        profile=record.authentication.verification
        actual=dict(namespace=record.project_id,expected_application_subject_id=profile.expected_subject,
            expected_actor_id=record.actor_id,expected_actor_revision=record.actor_revision,
            request=dict(method='GET',path=profile.path),subject_json_path='$.'+'.'.join(profile.subject_path))
        if profile.expected_role is not None:
            actual.update(role_json_path='$.'+'.'.join(profile.role_path),expected_role=profile.expected_role)
    return dict(identity_id=record.identity_id,actor_id=record.actor_id,actor_revision=record.actor_revision,
        identity_fingerprint=identity_source_fingerprint(record),label=record.label,actor_label=actor_label,
        binding=binding.binding.model_dump(mode='json'),verification=actual)
