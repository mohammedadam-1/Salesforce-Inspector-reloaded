from enum import StrEnum


class SalesforceEnvironment(StrEnum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    DEVELOPER = "developer"
    SCRATCH = "scratch"
    CUSTOM_DOMAIN = "custom_domain"
    GOVERNMENT_CLOUD = "government_cloud"
    HYPERFORCE = "hyperforce"


class SalesforceConnectionStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    FAILED = "failed"
    PENDING = "pending"


class SalesforceApiVersion(StrEnum):
    V62 = "62.0"
    V61 = "61.0"
    V60 = "60.0"
    V59 = "59.0"
    V58 = "58.0"
    V57 = "57.0"
    V56 = "56.0"
    V55 = "55.0"
    V54 = "54.0"
    V53 = "53.0"
    V52 = "52.0"


SALESFORCE_LOGIN_URLS: dict[SalesforceEnvironment, str] = {
    SalesforceEnvironment.PRODUCTION: "https://login.salesforce.com",
    SalesforceEnvironment.SANDBOX: "https://test.salesforce.com",
    SalesforceEnvironment.DEVELOPER: "https://login.salesforce.com",
    SalesforceEnvironment.SCRATCH: "https://test.salesforce.com",
    SalesforceEnvironment.CUSTOM_DOMAIN: "",  # dynamically determined
    SalesforceEnvironment.GOVERNMENT_CLOUD: "https://login.salesforce.gov",
    SalesforceEnvironment.HYPERFORCE: "",  # dynamically determined
}


SALESFORCE_INSTANCE_URLS: dict[SalesforceEnvironment, str] = {
    SalesforceEnvironment.PRODUCTION: "https://{instance}.salesforce.com",
    SalesforceEnvironment.SANDBOX: "https://{instance}.sandbox.my.salesforce.com",
    SalesforceEnvironment.DEVELOPER: "https://{instance}.develop.my.salesforce.com",
    SalesforceEnvironment.SCRATCH: "https://{instance}.scratch.my.salesforce.com",
    SalesforceEnvironment.CUSTOM_DOMAIN: "https://{instance}.my.salesforce.com",
    SalesforceEnvironment.GOVERNMENT_CLOUD: "https://{instance}.salesforce.gov",
    SalesforceEnvironment.HYPERFORCE: "https://{instance}.hyperforce.my.salesforce.com",
}


class SalesforceAuthError(Exception):
    pass


class SalesforceApiError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        sf_error_code: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.sf_error_code = sf_error_code
        super().__init__(message)
