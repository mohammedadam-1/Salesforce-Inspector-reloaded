from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    PENDING_VERIFICATION = "pending_verification"
    DISABLED = "disabled"


class OrgMemberStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"
    REMOVED = "removed"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    SUSPENDED = "suspended"
