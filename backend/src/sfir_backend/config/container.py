from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from sfir_backend.application.cache.services import (
    AutocompleteCacheService,
    ConnectionStatusCacheService,
    DocumentationCacheService,
    FeatureFlagCacheService,
    GraphCacheService,
    ImpactCacheService,
    MetadataCacheService,
    OrgSettingsCacheService,
    PermissionCacheService,
    RateLimitCacheService,
    SearchCacheService,
)
from sfir_backend.application.pipeline import CanonicalMapper, MetadataPipeline
from sfir_backend.application.pipeline.mapper.strategies import (
    ApexClassStrategy,
    ApexTriggerStrategy,
    DashboardStrategy,
    EmailTemplateStrategy,
    FlowStrategy,
    GenericDictStrategy,
    LayoutStrategy,
    LightningStrategy,
    MetadataComponentStrategy,
    ObjectStrategy,
    PermissionSetStrategy,
    ProfileStrategy,
    QueueStrategy,
    ReportStrategy,
    RoleStrategy,
    SharingRuleStrategy,
    StaticResourceStrategy,
    ValidationRuleStrategy,
    WorkflowRuleStrategy,
)
from sfir_backend.application.pipeline.normalizer import CanonicalNormalizer
from sfir_backend.application.pipeline.normalizer.rules import (
    NormalizeDefaultsRule,
    NormalizeEnumRule,
    NormalizeNamesRule,
    NormalizeNullsRule,
    NormalizeOwnerRule,
    NormalizeParentRule,
    NormalizeStringsRule,
    NormalizeTimestampsRule,
    NormalizeTypeNameRule,
)
from sfir_backend.application.pipeline.resolver.canonical_relationship_resolver import (
    CanonicalRelationshipResolver,
)
from sfir_backend.application.pipeline.stages import (
    CanonicalMappingStage,
    DependencyGraphStage,
    GraphStage,
    NormalizationStage,
    ParserStage,
    PersistenceStage,
    RelationshipStage,
    SearchIndexStage,
    SearchStage,
    ValidationStage,
)
from sfir_backend.application.pipeline.validator import (
    CanonicalMetadataValidator,
)
from sfir_backend.application.pipeline.validator.rules import (
    ApiNameFormatRule,
    DuplicateApiNameRule,
    EmptyRequiredFieldRule,
    EnumValueRule,
    KnownTypeRule,
    ParentReferenceRule,
    RequiredIdentifiersRule,
    RoleCircularReferenceRule,
    VersionRangeRule,
)
from sfir_backend.application.retrieval import RetrievalEngine
from sfir_backend.application.use_cases.ai.agent import (
    AgentService,
    AnalyzeDependenciesTool,
    FindImpactTool,
    GraphSummaryTool,
    QueryMetadataTool,
)
from sfir_backend.application.use_cases.ai.code_intelligence import (
    CodeIntelligenceEngine,
)
from sfir_backend.application.use_cases.ai.confidence_scorer import ConfidenceScorer
from sfir_backend.application.use_cases.ai.conversation_manager import (
    ConversationManager,
)
from sfir_backend.application.use_cases.ai.coordinator import AIRequestCoordinator
from sfir_backend.application.use_cases.ai.dependency_analyzer import (
    DependencyAnalyzer,
)
from sfir_backend.application.use_cases.ai.documentation_generator import (
    DocumentationGenerator,
)
from sfir_backend.application.use_cases.ai.field_dependency_engine import (
    FieldDependencyEngine,
)
from sfir_backend.application.use_cases.ai.impact_assessor import ImpactAssessor
from sfir_backend.application.use_cases.ai.metadata_analyzer import MetadataAnalyzer
from sfir_backend.application.use_cases.ai.next_action_generator import (
    NextActionGenerator,
)
from sfir_backend.application.use_cases.ai.orchestrator import AIOrchestrator
from sfir_backend.application.use_cases.ai.prompt_builder import PromptBuilder
from sfir_backend.application.use_cases.ai.response_composer import ResponseComposer
from sfir_backend.application.use_cases.ai.tools import ToolRegistry
from sfir_backend.application.use_cases.auth import AuthUseCase
from sfir_backend.application.use_cases.graph.repository_service import (
    RepositoryGraphService,
)
from sfir_backend.application.use_cases.metadata.validation_engine import (
    MetadataValidationEngine,
)
from sfir_backend.application.use_cases.metadata_sync import SyncCoordinator
from sfir_backend.application.use_cases.organization import OrganizationUseCase
from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.application.use_cases.salesforce import SalesforceUseCase
from sfir_backend.config.settings import Settings
from sfir_backend.infrastructure.cache.connection_pool import RedisConnectionPool
from sfir_backend.infrastructure.cache.coordinator import CacheCoordinator
from sfir_backend.infrastructure.cache.health_monitor import CacheHealthMonitor
from sfir_backend.infrastructure.cache.invalidation import CacheInvalidationManager
from sfir_backend.infrastructure.cache.key_builder import CacheKeyBuilder
from sfir_backend.infrastructure.cache.manager import CacheManager
from sfir_backend.infrastructure.cache.metrics import CacheMetricsCollector
from sfir_backend.infrastructure.cache.null_cache import NullCache
from sfir_backend.infrastructure.cache.redis_cache import RedisCache
from sfir_backend.infrastructure.cache.response_cache import ResponseCache
from sfir_backend.infrastructure.cache.serializer import CacheSerializer
from sfir_backend.infrastructure.database.session import (
    create_engine,
    create_session_factory,
)
from sfir_backend.infrastructure.documentation.engine import DocumentationEngine
from sfir_backend.infrastructure.graph.cache import GraphCacheCoordinator
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine
from sfir_backend.infrastructure.jobs.engine import JobEngine
from sfir_backend.infrastructure.oauth_session.redis_oauth_session_repo import (
    RedisOAuthSessionRepository,
)
from sfir_backend.infrastructure.observability.alerting import AlertManager
from sfir_backend.infrastructure.observability.diagnostics import DiagnosticsService
from sfir_backend.infrastructure.observability.health import HealthCheckManager
from sfir_backend.infrastructure.observability.logging import LoggingManager
from sfir_backend.infrastructure.observability.manager import ObservabilityManager
from sfir_backend.infrastructure.observability.metrics import MetricsCollector
from sfir_backend.infrastructure.observability.profiler import PerformanceProfiler
from sfir_backend.infrastructure.observability.telemetry import TelemetryCoordinator
from sfir_backend.infrastructure.observability.tracing import TracingManager
from sfir_backend.infrastructure.persistence.repositories.audit_log_repo import (
    AuditLogRepository,
)
from sfir_backend.infrastructure.persistence.repositories.canonical_repo import (
    SQLAlchemyCanonicalDocumentRepository,
)
from sfir_backend.infrastructure.persistence.repositories.canonical_relationship_repo import (
    SQLAlchemyCanonicalRelationshipRepository,
)
from sfir_backend.infrastructure.persistence.repositories.graph_repo import (
    SQLAlchemyGraphRepository,
)
from sfir_backend.infrastructure.persistence.repositories.search_index_repo import (
    SQLAlchemySearchIndexRepository,
)
from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
    SQLAlchemyMetadataRepository,
)
from sfir_backend.infrastructure.persistence.repositories.org_member_repo import (
    OrgMemberRepository,
)
from sfir_backend.infrastructure.persistence.repositories.organization_repo import (
    OrganizationRepository,
)
from sfir_backend.infrastructure.persistence.repositories.refresh_token_repo import (
    RefreshTokenRepository,
)
from sfir_backend.infrastructure.persistence.repositories.role_repo import (
    RoleRepository,
)
from sfir_backend.infrastructure.persistence.repositories.salesforce_connection_repo import (
    SalesforceConnectionRepository,
)
from sfir_backend.infrastructure.persistence.repositories.session_repo import (
    SessionRepository,
)
from sfir_backend.infrastructure.persistence.repositories.sync_repos import (
    MetadataVersionRepository,
    SyncCheckpointRepository,
    SyncHistoryRepository,
    SyncJobRepository,
    SyncRetryQueueRepository,
    SyncStatisticsRepository,
)
from sfir_backend.infrastructure.persistence.repositories.user_repo import (
    UserRepository,
)
from sfir_backend.infrastructure.resilience.circuit_breaker import (
    CircuitBreakerRegistry,
)
from sfir_backend.infrastructure.resilience.graceful_degradation import (
    GracefulDegradationManager,
)
from sfir_backend.infrastructure.resilience.retry_policy import RetryPolicy
from sfir_backend.infrastructure.salesforce.graph.apex import ApexDependencyExtractor
from sfir_backend.infrastructure.salesforce.graph.extractor import CompositeExtractor
from sfir_backend.infrastructure.salesforce.graph.layout import LayoutDependencyExtractor
from sfir_backend.infrastructure.salesforce.graph.profile import ProfileDependencyExtractor
from sfir_backend.infrastructure.salesforce.graph.validation import (
    ValidationRuleDependencyExtractor,
)
from sfir_backend.infrastructure.salesforce.oauth import SalesforceOAuthService
from sfir_backend.infrastructure.salesforce.parsers.apex import (
    ApexClassParser,
    ApexTriggerParser,
)
from sfir_backend.infrastructure.salesforce.parsers.canonical_adapter import (
    build_canonical_parser_adapters,
)
from sfir_backend.infrastructure.salesforce.parsers.layout import LayoutParser
from sfir_backend.infrastructure.salesforce.parsers.object import CustomObjectParser
from sfir_backend.infrastructure.salesforce.parsers.registry import ParserRegistry
from sfir_backend.infrastructure.salesforce.parsers.validation import ValidationRuleParser
from sfir_backend.infrastructure.salesforce.sync.downloader import (
    MetadataDownloadManager,
)
from sfir_backend.infrastructure.salesforce.sync.manifest import (
    ManifestGenerator,
    MetadataChangeDetector,
    MetadataHashCalculator,
)
from sfir_backend.infrastructure.salesforce.sync.operations import (
    RetryManager,
    SyncRecovery,
)
from sfir_backend.infrastructure.search.engine import SearchEngine
from sfir_backend.infrastructure.security.encryption import EncryptionService
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.infrastructure.security.password import PasswordService
from sfir_backend.infrastructure.security.prompt_injection_filter import (
    PromptInjectionFilter,
)
from sfir_backend.infrastructure.security.rate_limiter import RateLimiter
from sfir_backend.infrastructure.security.security_manager import SecurityManager
from sfir_backend.infrastructure.security.tool_permission_guard import (
    ToolPermissionGuard,
)
from sfir_backend.infrastructure.time.utc_clock import UtcClock

logger = structlog.get_logger(__name__)


def _make_repos_from_session(session: AsyncSession) -> dict[str, Any]:
    return {
        "user": UserRepository(session),
        "organization": OrganizationRepository(session),
        "org_member": OrgMemberRepository(session),
        "role": RoleRepository(session),
        "session": SessionRepository(session),
        "refresh_token": RefreshTokenRepository(session),
        "audit_log": AuditLogRepository(session),
        "salesforce_connection": SalesforceConnectionRepository(session),
        "sync_job": SyncJobRepository(session),
        "metadata_version": MetadataVersionRepository(session),
        "sync_history": SyncHistoryRepository(session),
        "sync_retry_queue": SyncRetryQueueRepository(session),
        "sync_statistics": SyncStatisticsRepository(session),
        "sync_checkpoint": SyncCheckpointRepository(session),
        "metadata": SQLAlchemyMetadataRepository(session),
        "canonical_document": SQLAlchemyCanonicalDocumentRepository(session),
        "canonical_relationship": SQLAlchemyCanonicalRelationshipRepository(session),
        "graph": SQLAlchemyGraphRepository(session),
        "search_index": SQLAlchemySearchIndexRepository(session),
    }


class Container:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._redis_client: Redis | None = None
        self._redis_pool: RedisConnectionPool | None = None
        self._sessions: list[AsyncSession] = []
        self._initialized = False

        self._ports: dict[str, Any] = {}
        self._repositories: dict[str, Any] = {}
        self._services: dict[str, Any] = {}
        self._use_case_factories: dict[str, Any] = {}
        self._use_case_cache: dict[str, Any] = {}

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def engine(self) -> AsyncEngine | None:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession] | None:
        return self._session_factory

    async def startup(self) -> None:
        logger.info("container_startup_begin")

        if self._initialized:
            logger.warning("container_already_initialized")
            return

        if not self._settings.is_testing:
            self._engine = create_engine(self._settings)
            self._session_factory = create_session_factory(self._engine)
            self._redis_pool = RedisConnectionPool(self._settings)
            self._redis_client = await self._redis_pool.get_client()

        self._register_ports()
        self._register_services()
        self._register_use_case_factories()

        self._initialized = True
        logger.info("container_startup_complete")

    def _register_ports(self) -> None:
        if self._settings.is_testing:
            self._ports["cache"] = NullCache()
        elif self._redis_client:
            self._ports["cache"] = RedisCache(self._redis_client)
        else:
            self._ports["cache"] = NullCache()

        self._ports["clock"] = UtcClock()

        key_builder = CacheKeyBuilder(
            environment=self._settings.environment,
        )
        serializer = CacheSerializer()
        cache_metrics = CacheMetricsCollector()

        if self._settings.is_testing or not self._redis_client:
            manager = CacheManager(
                cache=self._ports["cache"],
                metrics=cache_metrics,
                serializer=serializer,
            )
        else:
            from sfir_backend.infrastructure.cache.distributed_cache import (
                DistributedCache,
            )

            distributed = DistributedCache(
                cache=self._ports["cache"],
                redis=self._redis_client,
                metrics=cache_metrics,
                serializer=serializer,
            )
            manager = CacheManager(
                cache=distributed,
                metrics=cache_metrics,
                serializer=serializer,
            )
            self._ports["distributed_cache"] = distributed

        coordinator = CacheCoordinator(manager)

        if not self._settings.is_testing and self._redis_pool:
            health_monitor = CacheHealthMonitor(self._redis_pool)
            self._ports["health_monitor"] = health_monitor

        invalidation = CacheInvalidationManager(coordinator, key_builder)

        self._ports["key_builder"] = key_builder
        self._ports["serializer"] = serializer
        self._ports["cache_metrics"] = cache_metrics
        self._ports["cache_manager"] = manager
        self._ports["cache_coordinator"] = coordinator
        self._ports["cache_invalidation"] = invalidation

        metrics_collector = MetricsCollector()
        tracing_mgr = TracingManager()
        logging_mgr = LoggingManager()
        health_mgr = HealthCheckManager(
            redis_pool=self._redis_pool,
            cache_health=self._ports.get("health_monitor"),
        )
        profiler = PerformanceProfiler(enabled=not self._settings.is_testing)
        alerting = AlertManager()
        telemetry = TelemetryCoordinator(
            metrics=metrics_collector,
            tracing=tracing_mgr,
            logging_mgr=logging_mgr,
            health=health_mgr,
            profiler=profiler,
            alerting=alerting,
            environment=self._settings.environment,
        )
        diagnostics = DiagnosticsService(
            health=health_mgr,
            metrics=metrics_collector,
            profiler=profiler,
            alerting=alerting,
            logging_mgr=logging_mgr,
            environment=self._settings.environment,
        )

        self._ports["metrics_collector"] = metrics_collector
        self._ports["tracing_manager"] = tracing_mgr
        self._ports["logging_manager"] = logging_mgr
        self._ports["health_manager"] = health_mgr
        self._ports["profiler"] = profiler
        self._ports["alert_manager"] = alerting
        self._ports["telemetry"] = telemetry
        self._ports["diagnostics"] = diagnostics

    def _register_services(self) -> None:
        self._services["password"] = PasswordService()
        self._services["jwt"] = JWTService(self._settings)
        self._services["oauth"] = SalesforceOAuthService(self._settings)
        self._services["encryption"] = EncryptionService(self._settings)
        self._services["rate_limiter"] = RateLimiter(self._settings)
        self._register_security()

    def _register_security(self) -> None:
        repos = self._make_repos()
        self._services["security"] = SecurityManager(
            settings=self._settings,
            encryption_service=self._services["encryption"],
            jwt_service=self._services["jwt"],
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
            session_repo=repos["session"],
            refresh_token_repo=repos["refresh_token"],
            audit_log_repo=repos["audit_log"],
            rate_limit_cache=self._services.get("rate_limit_cache"),
            metrics_collector=self._ports.get("metrics_collector"),
            alert_manager=self._ports.get("alert_manager"),
        )
        self._services["parser_registry"] = self._make_parser_registry()
        self._services["extractor"] = self._make_extractor()
        self._services["graph_engine"] = DependencyGraphEngine()
        self._services["search_engine"] = SearchEngine()
        self._services["documentation_engine"] = DocumentationEngine()
        self._services["job_engine"] = JobEngine()
        self._services["retrieval_engine"] = self._make_retrieval_engine()

        coordinator = self._ports["cache_coordinator"]
        key_builder = self._ports["key_builder"]
        cache_metrics = self._ports["cache_metrics"]

        self._services["metadata_cache"] = MetadataCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["graph_cache"] = GraphCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["search_cache"] = SearchCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["autocomplete_cache"] = AutocompleteCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["impact_cache"] = ImpactCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["documentation_cache"] = DocumentationCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["settings_cache"] = OrgSettingsCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["connection_cache"] = ConnectionStatusCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["permission_cache"] = PermissionCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["rate_limit_cache"] = RateLimitCacheService(
            coordinator, key_builder, cache_metrics,
        )
        self._services["feature_flag_cache"] = FeatureFlagCacheService(
            coordinator, key_builder, cache_metrics,
        )

        observability = ObservabilityManager(
            metrics=self._ports["metrics_collector"],
            tracing=self._ports["tracing_manager"],
            logging_mgr=self._ports["logging_manager"],
            health=self._ports["health_manager"],
            profiler=self._ports["profiler"],
            alerting=self._ports["alert_manager"],
            telemetry=self._ports["telemetry"],
            diagnostics=self._ports["diagnostics"],
        )
        self._services["observability"] = observability

        self._services["confidence_scorer"] = ConfidenceScorer()
        self._services["next_action_generator"] = NextActionGenerator()
        self._services["response_composer"] = ResponseComposer()

        graph_svc = self._services.get("graph_service") or self._make_graph_service()
        self._services["field_dependency_engine"] = FieldDependencyEngine(
            graph_service=graph_svc,
        )
        self._services["dependency_analyzer"] = DependencyAnalyzer(
            graph_service=graph_svc,
        )
        self._services["impact_assessor"] = ImpactAssessor(
            graph_service=graph_svc,
        )
        self._services["metadata_analyzer"] = MetadataAnalyzer(
            graph_service=graph_svc,
            search_engine=self._services.get("search_engine"),
            parser_registry=self._services.get("parser_registry"),
        )
        self._services["code_intelligence"] = CodeIntelligenceEngine()
        self._services["documentation_generator"] = DocumentationGenerator(
            graph_service=graph_svc,
            metadata_analyzer=self._services["metadata_analyzer"],
            dependency_analyzer=self._services["dependency_analyzer"],
        )

        self._services["prompt_injection_filter"] = PromptInjectionFilter(
            enabled=not self._settings.is_testing,
        )
        self._services["tool_permission_guard"] = ToolPermissionGuard()
        self._services["circuit_breaker_registry"] = CircuitBreakerRegistry()
        self._services["retry_policy"] = RetryPolicy(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0,
        )
        self._services["graceful_degradation"] = GracefulDegradationManager()
        self._services["response_cache"] = ResponseCache(
            default_ttl=300,
            max_entries=1000,
        )

    def _register_use_case_factories(self) -> None:
        self._use_case_factories["auth"] = lambda: self._make_auth_use_case()
        self._use_case_factories["organization"] = lambda: self._make_org_use_case()
        self._use_case_factories["rbac"] = lambda: self._make_rbac_use_case()
        self._use_case_factories["salesforce"] = lambda: self._make_salesforce_use_case()
        self._use_case_factories["sync_coordinator"] = lambda: self._make_sync_coordinator()
        self._use_case_factories["graph_service"] = lambda: self._make_graph_service()
        self._use_case_factories["agent_service"] = lambda: self._make_agent_service()
        self._use_case_factories["ai_orchestrator"] = lambda: self._make_ai_orchestrator()
        self._use_case_factories["metadata_pipeline"] = lambda: self._make_metadata_pipeline()
        self._use_case_factories["metadata_validation"] = lambda: self._make_metadata_validation_engine()

    def _get_session(self) -> AsyncSession:
        if not self._session_factory:
            raise RuntimeError("Database not initialized")
        session = self._session_factory()
        self._sessions.append(session)
        return session

    def _make_repos(self) -> dict[str, Any]:
        session = self._get_session()
        return {
            "user": UserRepository(session),
            "organization": OrganizationRepository(session),
            "org_member": OrgMemberRepository(session),
            "role": RoleRepository(session),
            "session": SessionRepository(session),
            "refresh_token": RefreshTokenRepository(session),
            "audit_log": AuditLogRepository(session),
            "salesforce_connection": SalesforceConnectionRepository(session),
            "sync_job": SyncJobRepository(session),
            "metadata_version": MetadataVersionRepository(session),
            "sync_history": SyncHistoryRepository(session),
            "sync_retry_queue": SyncRetryQueueRepository(session),
            "sync_statistics": SyncStatisticsRepository(session),
            "sync_checkpoint": SyncCheckpointRepository(session),
            "metadata": SQLAlchemyMetadataRepository(session),
            "canonical_document": SQLAlchemyCanonicalDocumentRepository(session),
            "canonical_relationship": SQLAlchemyCanonicalRelationshipRepository(session),
            "graph": SQLAlchemyGraphRepository(session),
            "search_index": SQLAlchemySearchIndexRepository(session),
        }

    def _make_oauth_session_repo(self) -> RedisOAuthSessionRepository | None:
        if self._redis_client is None:
            return None
        return RedisOAuthSessionRepository(self._redis_client)

    def _make_auth_use_case(self) -> AuthUseCase:
        repos = self._make_repos()
        return AuthUseCase(
            user_repo=repos["user"],
            org_repo=repos["organization"],
            org_member_repo=repos["org_member"],
            session_repo=repos["session"],
            refresh_token_repo=repos["refresh_token"],
            role_repo=repos["role"],
            audit_log_repo=repos["audit_log"],
            password_service=self._services["password"],
            jwt_service=self._services["jwt"],
        )

    def create_auth_use_case(self, session: AsyncSession) -> AuthUseCase:
        repos = _make_repos_from_session(session)
        return AuthUseCase(
            user_repo=repos["user"],
            org_repo=repos["organization"],
            org_member_repo=repos["org_member"],
            session_repo=repos["session"],
            refresh_token_repo=repos["refresh_token"],
            role_repo=repos["role"],
            audit_log_repo=repos["audit_log"],
            password_service=self._services["password"],
            jwt_service=self._services["jwt"],
        )

    def _make_org_use_case(self) -> OrganizationUseCase:
        repos = self._make_repos()
        return OrganizationUseCase(
            user_repo=repos["user"],
            org_repo=repos["organization"],
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
            audit_log_repo=repos["audit_log"],
            jwt_service=self._services["jwt"],
            connection_repo=repos["salesforce_connection"],
            version_repo=repos["metadata_version"],
        )

    def create_org_use_case(self, session: AsyncSession) -> OrganizationUseCase:
        repos = _make_repos_from_session(session)
        return OrganizationUseCase(
            user_repo=repos["user"],
            org_repo=repos["organization"],
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
            audit_log_repo=repos["audit_log"],
            jwt_service=self._services["jwt"],
            connection_repo=repos["salesforce_connection"],
            version_repo=repos["metadata_version"],
        )

    def _make_rbac_use_case(self) -> RBACUseCase:
        repos = self._make_repos()
        return RBACUseCase(
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
        )

    def create_rbac_use_case(self, session: AsyncSession) -> RBACUseCase:
        repos = _make_repos_from_session(session)
        return RBACUseCase(
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
        )

    def _make_salesforce_use_case(self) -> SalesforceUseCase:
        repos = self._make_repos()
        return SalesforceUseCase(
            connection_repo=repos["salesforce_connection"],
            org_repo=repos["organization"],
            audit_log_repo=repos["audit_log"],
            oauth_service=self._services["oauth"],
            encryption_service=self._services["encryption"],
            sync_coordinator=self._make_sync_coordinator(),
            oauth_session_repo=self._make_oauth_session_repo(),
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
        )

    def create_salesforce_use_case(self, session: AsyncSession) -> SalesforceUseCase:
        repos = _make_repos_from_session(session)
        return SalesforceUseCase(
            connection_repo=repos["salesforce_connection"],
            org_repo=repos["organization"],
            audit_log_repo=repos["audit_log"],
            oauth_service=self._services["oauth"],
            encryption_service=self._services["encryption"],
            sync_coordinator=self.create_sync_coordinator(session),
            oauth_session_repo=self._make_oauth_session_repo(),
            org_member_repo=repos["org_member"],
            role_repo=repos["role"],
        )

    def _make_sync_coordinator(self) -> SyncCoordinator:
        repos = self._make_repos()
        download_manager = MetadataDownloadManager()
        hash_calculator = MetadataHashCalculator()
        change_detector = MetadataChangeDetector()
        manifest_generator = ManifestGenerator()
        retry_manager = RetryManager(
            retry_repo=repos["sync_retry_queue"],
        )
        recovery = SyncRecovery(retry_manager=retry_manager)
        return SyncCoordinator(
            connection_repo=repos["salesforce_connection"],
            sync_job_repo=repos["sync_job"],
            version_repo=repos["metadata_version"],
            sync_history_repo=repos["sync_history"],
            retry_repo=repos["sync_retry_queue"],
            statistics_repo=repos["sync_statistics"],
            audit_log_repo=repos["audit_log"],
            encryption_service=self._services["encryption"],
            download_manager=download_manager,
            hash_calculator=hash_calculator,
            change_detector=change_detector,
            manifest_generator=manifest_generator,
            retry_manager=retry_manager,
            recovery=recovery,
            oauth_service=self._services["oauth"],
            metadata_pipeline=self._make_metadata_pipeline(),
            checkpoint_repo=repos["sync_checkpoint"],
            canonical_repo=repos["canonical_document"],
            canonical_relationship_repo=repos["canonical_relationship"],
        )

    def create_sync_coordinator(self, session: AsyncSession) -> SyncCoordinator:
        repos = _make_repos_from_session(session)
        download_manager = MetadataDownloadManager()
        hash_calculator = MetadataHashCalculator()
        change_detector = MetadataChangeDetector()
        manifest_generator = ManifestGenerator()
        retry_manager = RetryManager(
            retry_repo=repos["sync_retry_queue"],
        )
        recovery = SyncRecovery(retry_manager=retry_manager)
        return SyncCoordinator(
            connection_repo=repos["salesforce_connection"],
            sync_job_repo=repos["sync_job"],
            version_repo=repos["metadata_version"],
            sync_history_repo=repos["sync_history"],
            retry_repo=repos["sync_retry_queue"],
            statistics_repo=repos["sync_statistics"],
            audit_log_repo=repos["audit_log"],
            encryption_service=self._services["encryption"],
            download_manager=download_manager,
            hash_calculator=hash_calculator,
            change_detector=change_detector,
            manifest_generator=manifest_generator,
            retry_manager=retry_manager,
            recovery=recovery,
            oauth_service=self._services["oauth"],
            metadata_pipeline=self.create_metadata_pipeline(session),
            checkpoint_repo=repos["sync_checkpoint"],
            canonical_repo=repos["canonical_document"],
            canonical_relationship_repo=repos["canonical_relationship"],
        )

    def _make_retrieval_engine(self) -> RetrievalEngine:
        repos = self._make_repos()
        return RetrievalEngine(
            search_repo=repos["search_index"],
            canonical_repo=repos["canonical_document"],
            graph_repo=repos["graph"],
        )

    def _make_metadata_pipeline(self) -> MetadataPipeline:
        repos = self._make_repos()
        parser_registry = self._services["parser_registry"]
        graph_engine: DependencyGraphEngine = self._services["graph_engine"]
        search_engine: SearchEngine = self._services["search_engine"]
        metadata_repo = repos["metadata"]

        mapper = self._make_canonical_mapper()
        validator = self._make_canonical_validator()
        normalizer = self._make_canonical_normalizer()
        stages = [
            ParserStage(parser_registry=parser_registry),
            CanonicalMappingStage(mapper=mapper),
            ValidationStage(validator=validator),
            NormalizationStage(normalizer=normalizer),
            PersistenceStage(
                metadata_repo=metadata_repo,
                canonical_repo=repos["canonical_document"],
            ),
            RelationshipStage(
                relationship_repo=repos["canonical_relationship"],
                canonical_repo=repos["canonical_document"],
                resolver=self._make_canonical_relationship_resolver(),
            ),
            DependencyGraphStage(
                graph_repo=repos["graph"],
                canonical_repo=repos["canonical_document"],
                relationship_repo=repos["canonical_relationship"],
            ),
            SearchIndexStage(
                search_repo=repos["search_index"],
                canonical_repo=repos["canonical_document"],
                graph_repo=repos["graph"],
            ),
            GraphStage(graph_engine=graph_engine),
            SearchStage(search_engine=search_engine),
        ]
        return MetadataPipeline(stages=stages)

    def create_metadata_pipeline(self, session: AsyncSession) -> MetadataPipeline:
        repos = _make_repos_from_session(session)
        parser_registry = self._services["parser_registry"]
        graph_engine: DependencyGraphEngine = self._services["graph_engine"]
        search_engine: SearchEngine = self._services["search_engine"]
        metadata_repo = repos["metadata"]

        mapper = self._make_canonical_mapper()
        validator = self._make_canonical_validator()
        normalizer = self._make_canonical_normalizer()
        stages = [
            ParserStage(parser_registry=parser_registry),
            CanonicalMappingStage(mapper=mapper),
            ValidationStage(validator=validator),
            NormalizationStage(normalizer=normalizer),
            PersistenceStage(
                metadata_repo=metadata_repo,
                canonical_repo=repos["canonical_document"],
            ),
            RelationshipStage(
                relationship_repo=repos["canonical_relationship"],
                canonical_repo=repos["canonical_document"],
                resolver=self._make_canonical_relationship_resolver(),
            ),
            DependencyGraphStage(
                graph_repo=repos["graph"],
                canonical_repo=repos["canonical_document"],
                relationship_repo=repos["canonical_relationship"],
            ),
            SearchIndexStage(
                search_repo=repos["search_index"],
                canonical_repo=repos["canonical_document"],
                graph_repo=repos["graph"],
            ),
            GraphStage(graph_engine=graph_engine),
            SearchStage(search_engine=search_engine),
        ]
        return MetadataPipeline(stages=stages)

    def _make_metadata_validation_engine(self) -> MetadataValidationEngine:
        repos = self._make_repos()
        validator = self._make_canonical_validator()
        return MetadataValidationEngine(
            metadata_repo=repos["metadata"],
            validator=validator,
            sync_job_repo=repos["sync_job"],
        )

    def create_metadata_validation_engine(
        self, session: AsyncSession,
    ) -> MetadataValidationEngine:
        repos = _make_repos_from_session(session)
        validator = self._make_canonical_validator()
        return MetadataValidationEngine(
            metadata_repo=repos["metadata"],
            validator=validator,
            sync_job_repo=repos["sync_job"],
        )

    def _make_canonical_mapper(self) -> CanonicalMapper:
        mapper = CanonicalMapper()
        mapper.register(MetadataComponentStrategy())
        mapper.register(ApexClassStrategy())
        mapper.register(ApexTriggerStrategy())
        mapper.register(ObjectStrategy())
        mapper.register(ValidationRuleStrategy())
        mapper.register(FlowStrategy())
        mapper.register(LayoutStrategy())
        mapper.register(ProfileStrategy())
        mapper.register(PermissionSetStrategy())
        mapper.register(EmailTemplateStrategy())
        mapper.register(ReportStrategy())
        mapper.register(DashboardStrategy())
        mapper.register(RoleStrategy())
        mapper.register(QueueStrategy())
        mapper.register(SharingRuleStrategy())
        mapper.register(WorkflowRuleStrategy())
        mapper.register(LightningStrategy())
        mapper.register(StaticResourceStrategy())
        mapper.register(GenericDictStrategy())
        return mapper

    def _make_canonical_validator(self) -> CanonicalMetadataValidator:
        validator = CanonicalMetadataValidator()
        validator.register(RequiredIdentifiersRule())
        validator.register(KnownTypeRule())
        validator.register(ApiNameFormatRule())
        validator.register(DuplicateApiNameRule())
        validator.register(ParentReferenceRule())
        validator.register(RoleCircularReferenceRule())
        validator.register(EnumValueRule())
        validator.register(EmptyRequiredFieldRule())
        validator.register(VersionRangeRule())
        return validator

    def _make_canonical_relationship_resolver(self) -> CanonicalRelationshipResolver:
        return CanonicalRelationshipResolver()

    def _make_canonical_normalizer(self) -> CanonicalNormalizer:
        normalizer = CanonicalNormalizer()
        normalizer.register(NormalizeTypeNameRule())
        normalizer.register(NormalizeNamesRule())
        normalizer.register(NormalizeStringsRule())
        normalizer.register(NormalizeNullsRule())
        normalizer.register(NormalizeDefaultsRule())
        normalizer.register(NormalizeEnumRule())
        normalizer.register(NormalizeOwnerRule())
        normalizer.register(NormalizeTimestampsRule())
        normalizer.register(NormalizeParentRule())
        return normalizer

    def _make_parser_registry(self) -> ParserRegistry:
        registry = ParserRegistry()
        # Narrow runtime parsers first: they win for the 5 types they cover
        # (registry.get returns the first can_parse() match), preserving the
        # existing behavior exactly.
        registry.register(ApexClassParser())
        registry.register(ApexTriggerParser())
        registry.register(CustomObjectParser())
        registry.register(LayoutParser())
        registry.register(ValidationRuleParser())
        # Canonical adapters: richer broad parsers reused behind the same
        # MetadataParser contract for every other supported metadata type.
        for adapter in build_canonical_parser_adapters():
            registry.register(adapter)
        return registry

    def _make_extractor(self) -> CompositeExtractor:
        extractor = CompositeExtractor()
        extractor.register(ApexDependencyExtractor())
        extractor.register(ProfileDependencyExtractor())
        extractor.register(LayoutDependencyExtractor())
        extractor.register(ValidationRuleDependencyExtractor())
        return extractor

    def _make_graph_service(self) -> RepositoryGraphService:
        repos = self._make_repos()
        return RepositoryGraphService(
            metadata_repo=repos["metadata"],
            graph_engine=self._services["graph_engine"],
            cache=self._services["graph_cache"],
            cache_coordinator=GraphCacheCoordinator(),
        )

    def create_graph_service(self, session: AsyncSession) -> RepositoryGraphService:
        repos = _make_repos_from_session(session)
        return RepositoryGraphService(
            metadata_repo=repos["metadata"],
            graph_engine=self._services["graph_engine"],
            cache=self._services["graph_cache"],
            cache_coordinator=GraphCacheCoordinator(),
        )

    def _make_llm_provider(self) -> Any:
        if not self._settings.is_testing and self._settings.openai_api_key:
            try:
                from sfir_backend.infrastructure.llm.providers.openai import OpenAIProvider
                return OpenAIProvider(
                    api_key=str(self._settings.openai_api_key),
                    model=self._settings.openai_model or "gpt-4o",
                )
            except Exception:
                logger.warning("failed_to_init_llm_provider")
        return None

    def _register_engineering_tools(self, tool_registry: ToolRegistry, graph_svc: Any) -> None:
        from sfir_backend.application.use_cases.ai.engineering_tools import (
            CodeIntelligenceTool,
            CodeReviewTool,
            DependencyAnalysisTool,
            DeploymentRiskTool,
            DocumentationGenerationTool,
            FieldImpactTool,
            ImpactAssessmentTool,
            MetadataAnalysisTool,
            SafeDeleteTool,
            SecurityReviewTool,
        )
        tool_registry.register(QueryMetadataTool(graph_svc))
        tool_registry.register(AnalyzeDependenciesTool(graph_svc))
        tool_registry.register(FindImpactTool(graph_svc))
        tool_registry.register(GraphSummaryTool(graph_svc))

        field_dep = self._services.get("field_dependency_engine")
        if field_dep:
            tool_registry.register(FieldImpactTool(field_dep))

        dep_analyzer = self._services.get("dependency_analyzer")
        if dep_analyzer:
            tool_registry.register(DependencyAnalysisTool(dep_analyzer))

        impact = self._services.get("impact_assessor")
        if impact:
            tool_registry.register(ImpactAssessmentTool(impact))
            tool_registry.register(SafeDeleteTool(impact))
            tool_registry.register(DeploymentRiskTool(impact))

        meta_analyzer = self._services.get("metadata_analyzer")
        if meta_analyzer:
            tool_registry.register(MetadataAnalysisTool(meta_analyzer))

        code_intel = self._services.get("code_intelligence")
        if code_intel:
            tool_registry.register(CodeIntelligenceTool(code_intel))
            tool_registry.register(CodeReviewTool())
            tool_registry.register(SecurityReviewTool())

        doc_gen = self._services.get("documentation_generator")
        if doc_gen:
            tool_registry.register(DocumentationGenerationTool(doc_gen))

    def _make_agent_service(self) -> AgentService:
        graph_service = self._make_graph_service()
        tool_registry = ToolRegistry()
        self._register_engineering_tools(tool_registry, graph_service)
        llm = self._make_llm_provider()
        if not llm:
            from sfir_backend.infrastructure.llm.providers.base import (
                BaseLLMProvider,
                LLMResponse,
            )
            class _NoopProvider(BaseLLMProvider):
                async def chat(self, _messages=None, _tools=None,
                               _temperature=0.1, _max_tokens=4096):
                    return LLMResponse(content="LLM not configured. Set OPENAI_API_KEY.")

                async def chat_with_tools(self, _messages=None, _tools=None,
                                          _tool_choice="auto",
                                          _temperature=0.1, _max_tokens=4096):
                    return LLMResponse(content="LLM not configured. Set OPENAI_API_KEY.")
            llm = _NoopProvider()
        return AgentService(
            llm_provider=llm,
            tool_registry=tool_registry,
            graph_service=graph_service,
        )

    def create_agent_service(self, session: AsyncSession) -> AgentService:
        graph_service = self.create_graph_service(session)
        tool_registry = ToolRegistry()
        self._register_engineering_tools(tool_registry, graph_service)
        llm = self._make_llm_provider()
        if not llm:
            from sfir_backend.infrastructure.llm.providers.base import (
                BaseLLMProvider,
                LLMResponse,
            )
            class _NoopProvider(BaseLLMProvider):
                async def chat(self, _messages=None, _tools=None,
                               _temperature=0.1, _max_tokens=4096):
                    return LLMResponse(content="LLM not configured. Set OPENAI_API_KEY.")

                async def chat_with_tools(self, _messages=None, _tools=None,
                                          _tool_choice="auto",
                                          _temperature=0.1, _max_tokens=4096):
                    return LLMResponse(content="LLM not configured. Set OPENAI_API_KEY.")
            llm = _NoopProvider()
        return AgentService(
            llm_provider=llm,
            tool_registry=tool_registry,
            graph_service=graph_service,
        )

    def _make_ai_orchestrator(self) -> AIOrchestrator:
        from sfir_backend.application.use_cases.ai.tools import ToolRegistry
        from sfir_backend.infrastructure.llm.ai_cache import AICache
        from sfir_backend.infrastructure.llm.citation_generator import (
            CitationGenerator,
        )
        from sfir_backend.infrastructure.llm.context_retriever import (
            ContextCompressor,
            ContextRetriever,
        )
        from sfir_backend.infrastructure.llm.prompt_template import (
            PromptTemplateEngine,
        )
        from sfir_backend.infrastructure.llm.providers.registry import (
            create_provider_registry,
        )
        from sfir_backend.infrastructure.llm.response_validator import (
            ResponseFormatter,
            ResponseValidator,
        )
        from sfir_backend.infrastructure.llm.safety_filter import SafetyFilter
        from sfir_backend.infrastructure.llm.tracking import AIUsageTracker

        provider_registry = create_provider_registry(self._settings)
        prompt_template_engine = PromptTemplateEngine()
        prompt_builder = PromptBuilder(prompt_template_engine)
        context_retriever = ContextRetriever()
        context_compressor = ContextCompressor()
        citation_generator = CitationGenerator()
        response_validator = ResponseValidator()
        response_formatter = ResponseFormatter()
        safety_filter = SafetyFilter()
        usage_tracker = AIUsageTracker()
        ai_cache = AICache()

        confidence_scorer = self._services.get("confidence_scorer", ConfidenceScorer())
        next_action_generator = self._services.get("next_action_generator", NextActionGenerator())
        response_composer = self._services.get("response_composer", ResponseComposer())

        injection_filter = self._services.get("prompt_injection_filter")
        tool_permission_guard = self._services.get("tool_permission_guard")

        tool_registry = ToolRegistry()
        self._register_engineering_tools(tool_registry, self._make_graph_service())

        coordinator = AIRequestCoordinator(
            provider_registry=provider_registry,
            prompt_builder=prompt_builder,
            context_retriever=context_retriever,
            context_compressor=context_compressor,
            citation_generator=citation_generator,
            response_validator=response_validator,
            response_formatter=response_formatter,
            safety_filter=safety_filter,
            usage_tracker=usage_tracker,
            cache=ai_cache,
            tool_registry=tool_registry,
            confidence_scorer=confidence_scorer,
            next_action_generator=next_action_generator,
            response_composer=response_composer,
            injection_filter=injection_filter,
            tool_permission_guard=tool_permission_guard,
        )
        conversation_manager = ConversationManager()
        circuit_breaker_registry = self._services.get("circuit_breaker_registry")
        retry_policy = self._services.get("retry_policy")
        graceful_degradation = self._services.get("graceful_degradation")
        return AIOrchestrator(
            coordinator=coordinator,
            conversation_manager=conversation_manager,
            usage_tracker=usage_tracker,
            provider_registry=provider_registry,
            cache=ai_cache,
            circuit_breaker_registry=circuit_breaker_registry,
            retry_policy=retry_policy,
            graceful_degradation=graceful_degradation,
        )

    def get_port(self, name: str) -> Any:
        if name not in self._ports:
            raise KeyError(f"Port not registered: {name}")
        return self._ports[name]

    def get_repository(self, name: str) -> Any:
        if not self._repositories and not self._settings.is_testing:
            self._repositories = self._make_repos()
        if name not in self._repositories:
            raise KeyError(f"Repository not registered: {name}")
        return self._repositories[name]

    def get_service(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return self._services[name]

    def get_use_case(self, name: str) -> Any:
        if name not in self._use_case_factories:
            raise KeyError(f"Use case not registered: {name}")
        if name not in self._use_case_cache:
            self._use_case_cache[name] = self._use_case_factories[name]()
        return self._use_case_cache[name]

    def create_session(self) -> AsyncSession:
        if not self._session_factory:
            raise RuntimeError(
                "Database not initialized. "
                "Session factory is not available.",
            )
        return self._session_factory()

    async def shutdown(self) -> None:
        logger.info("container_shutdown_begin")

        for session in self._sessions:
            await session.close()
        self._sessions.clear()

        if self._engine:
            await self._engine.dispose()
            logger.info("database_engine_disposed")

        if self._redis_pool:
            await self._redis_pool.close()
            logger.info("redis_pool_closed")
        elif self._redis_client:
            await self._redis_client.aclose()
            logger.info("redis_connection_closed")

        self._initialized = False
        logger.info("container_shutdown_complete")
