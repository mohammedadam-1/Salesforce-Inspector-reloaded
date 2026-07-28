from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.permissions import MetadataPermissionSet, MetadataProfile
from sfir_backend.domain.metadata.profiles import PermissionSet, Profile


class ProfileStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Profile)

    def map(self, parsed: object) -> MetadataProfile:
        prof = parsed
        return MetadataProfile(
            api_name=prof.name,
            label=prof.name,
            user_license=prof.user_license or "",
            custom=prof.custom,
            object_permissions=[o.__dict__ for o in prof.object_permissions] if prof.object_permissions else [],
            field_permissions=[f.__dict__ for f in prof.field_permissions] if prof.field_permissions else [],
            class_permissions=[c.__dict__ for c in prof.class_permissions] if prof.class_permissions else [],
            page_permissions=[p.__dict__ for p in prof.page_permissions] if prof.page_permissions else [],
            user_permissions=[u.__dict__ for u in prof.user_permissions] if prof.user_permissions else [],
            record_type_visibilities=[r.__dict__ for r in prof.record_type_visibilities] if prof.record_type_visibilities else [],
            metadata_properties={
                "component_id": prof.component_id,
                "description": prof.description,
                "login_hours": prof.login_hours,
                "login_ip_ranges": prof.login_ip_ranges,
            },
        )


class PermissionSetStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, PermissionSet)

    def map(self, parsed: object) -> MetadataPermissionSet:
        ps = parsed
        return MetadataPermissionSet(
            api_name=ps.name,
            label=ps.label or ps.name,
            user_license=ps.user_license or "",
            is_owned_by_profile=ps.is_owned_by_profile,
            profile_name=ps.profile,
            has_activation=ps.has_activation,
            object_permissions=[o.__dict__ for o in ps.object_permissions] if ps.object_permissions else [],
            field_permissions=[f.__dict__ for f in ps.field_permissions] if ps.field_permissions else [],
            class_permissions=[c.__dict__ for c in ps.class_permissions] if ps.class_permissions else [],
            page_permissions=[p.__dict__ for p in ps.page_permissions] if ps.page_permissions else [],
            user_permissions=[u.__dict__ for u in ps.user_permissions] if ps.user_permissions else [],
            record_type_visibilities=[r.__dict__ for r in ps.record_type_visibilities] if ps.record_type_visibilities else [],
            metadata_properties={
                "component_id": ps.component_id,
                "description": ps.description,
            },
        )
