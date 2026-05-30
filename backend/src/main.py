from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI

from src.adapters.elasticsearch.assistantstore import ElasticAssistantstore
from src.adapters.elasticsearch.casestore import ElasticCasestore
from src.adapters.elasticsearch.client import ElasticClients, build_async_client
from src.adapters.elasticsearch.detectionstore import ElasticDetectionstore
from src.adapters.elasticsearch.eventstore import ElasticEventstore
from src.adapters.filedatastore.store import FileDatastore
from src.adapters.kratos.userstore import KratosUserstore
from src.adapters.salt.gridmembers import SaltGridMembersstore
from src.adapters.salt.relay import FileQueueRelayClient
from src.adapters.salt.userstore import SaltAdminUserstore
from src.adapters.statickeyauth.middleware import StaticKeyAuth
from src.adapters.staticrbac.authorizer import StaticRbacAuthorizer
from src.adapters.stub.info_provider import StubInfoProvider
from src.adapters.stub.userstore import StubUserstore
from src.api import (
    assistant_routes,
    case_routes,
    detection_routes,
    events_routes,
    gridmembers_routes,
    info_routes,
    job_routes,
    jobs_routes,
    node_routes,
    roles_routes,
    users_routes,
)
from src.api.assistant_routes import router as assistant_router
from src.api.case_routes import router as case_router
from src.api.clients_routes import router as clients_router
from src.api.config_routes import router as config_router
from src.api.detection_routes import router as detection_router
from src.api.events_routes import router as events_router
from src.api.grid_routes import get_grid_service
from src.api.grid_routes import router as grid_router
from src.api.gridmembers_routes import router as gridmembers_router
from src.api.info_routes import router as info_router
from src.api.job_routes import router as job_router
from src.api.jobs_routes import router as jobs_router
from src.api.node_routes import router as node_router
from src.api.packet_routes import router as packet_router
from src.api.playbook_routes import router as playbook_router
from src.api.query_routes import router as query_router
from src.api.roles_routes import router as roles_router
from src.api.stream_routes import router as stream_router
from src.api.users_routes import router as users_router
from src.api.util_routes import router as util_router
from src.config import AppConfig, load_config
from src.domain.assistant import (
    BalanceResponse,
    HealthResponse,
    Message,
    ToolResponse,
)
from src.domain.status import Status
from src.domain.user import User
from src.ports.users import AdminUserstore, Userstore
from src.services.assistant_service import AssistantService
from src.services.case_service import CaseService
from src.services.detection_service import DetectionService
from src.services.events_service import EventsService
from src.services.grid_service import GridService
from src.services.gridmembers_service import GridMembersService
from src.services.info_service import InfoService
from src.services.job_service import JobService
from src.services.node_service import NodeService
from src.services.roles_service import RolesService
from src.services.users_service import UsersService


def _build_base_app() -> FastAPI:
    """Create a FastAPI instance with all routers and the health route.

    Shared by the module-level ``app`` and the ``create_app`` factory so the
    router registration stays in one place.
    """
    application = FastAPI(title="SecurityOnion SOC", version="0.1.0")

    application.include_router(assistant_router, prefix="/api")
    application.include_router(info_router, prefix="/api")
    application.include_router(config_router, prefix="/api")
    application.include_router(util_router, prefix="/api")
    application.include_router(grid_router, prefix="/api")
    application.include_router(gridmembers_router, prefix="/api")
    application.include_router(case_router, prefix="/api")
    application.include_router(detection_router, prefix="/api")
    application.include_router(events_router, prefix="/api")
    application.include_router(job_router, prefix="/api")
    application.include_router(jobs_router, prefix="/api")
    application.include_router(node_router, prefix="/api")
    application.include_router(packet_router, prefix="/api")
    application.include_router(query_router, prefix="/api")
    application.include_router(playbook_router, prefix="/api")
    application.include_router(stream_router, prefix="/api")
    application.include_router(users_router, prefix="/api")
    application.include_router(roles_router, prefix="/api")
    application.include_router(clients_router, prefix="/api")

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = _build_base_app()


class _NullStatusstore:
    """Statusstore that returns an empty status.

    The GET /api/grid/ (get_nodes) path never calls this, so a minimal
    implementation is sufficient for Tier 0 wiring.
    """

    async def get_status_summary(self) -> Status:
        return Status("")


class _UnconfiguredAdminUserstore:
    """AdminUserstore placeholder — no admin adapter is wired yet.

    Read paths (GET /users/) never touch these methods; write operations
    raise until a real AdminUserstore adapter (e.g. Kratos admin) is added.
    """

    async def add_user(self, user: User) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def delete_user(self, user_id: str) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def update_profile(self, user: User) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def reset_password(self, user_id: str, password: str) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def enable_user(self, user_id: str) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def disable_user(self, user_id: str) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def add_role(self, user_id: str, role: str, bypass_auth_check: bool = False) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def delete_role(self, user_id: str, role: str) -> None:
        raise NotImplementedError("AdminUserstore not configured")

    async def sync_users(self) -> None:
        raise NotImplementedError("AdminUserstore not configured")


class _UnconfiguredAssistantManager:
    """AssistantManager placeholder — no AI manager adapter is wired yet.

    The AI manager is a behavioral port (out of scope for the ES storage
    adapter). Wiring the ES-backed Assistantstore still needs *a* manager to
    construct AssistantService; persistence-only routes (sessions, history,
    usage) never touch these methods, while chat/tool/balance/health raise
    until a real manager adapter lands.
    """

    async def chat(self, model: str, messages: list[Message]) -> list[Message]:
        raise NotImplementedError("AssistantManager not configured")

    async def chat_stream(
        self, model: str, messages: list[Message],
    ) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError("AssistantManager not configured")

    async def execute_tool(
        self, tool_name: str, params: str, aux_data: str,
    ) -> ToolResponse:
        raise NotImplementedError("AssistantManager not configured")

    async def balance(self, model: str) -> BalanceResponse:
        raise NotImplementedError("AssistantManager not configured")

    async def health(self, model: str) -> HealthResponse:
        raise NotImplementedError("AssistantManager not configured")


def create_app(config_path: str | None = None) -> FastAPI:
    """Build a fresh FastAPI app with Tier 0 adapters wired in."""
    application = _build_base_app()

    cfg = load_config(config_path) if config_path else AppConfig()

    auth = StaticKeyAuth(cfg.statickeyauth.api_key, cfg.statickeyauth.anonymous_cidr)
    datastore = FileDatastore(
        job_dir=cfg.filedatastore.job_dir,
        retry_failure_interval_ms=cfg.filedatastore.retry_failure_interval_ms,
        retry_failure_max_attempts=cfg.filedatastore.retry_failure_max_attempts,
    )

    # Select the Userstore once and share it across InfoService (force_user_otp
    # lookup) and UsersService — otherwise /api/info/ and /api/users/ would read
    # from different backends (split-brain) when Kratos is configured.
    userstore: Userstore = (
        KratosUserstore(cfg.kratos.host_url) if cfg.kratos.host_url else StubUserstore()
    )
    # KratosUserstore owns an httpx.AsyncClient; close it on app shutdown so the
    # connection pool isn't leaked. (StubUserstore holds no resources.)
    if isinstance(userstore, KratosUserstore):
        application.router.on_shutdown.append(userstore.close)

    # Auth on every route module that exposes a request-context dependency.
    application.dependency_overrides[info_routes.get_request_context_dep] = auth
    application.dependency_overrides[job_routes.get_request_context_dep] = auth
    application.dependency_overrides[jobs_routes.get_request_context_dep] = auth
    application.dependency_overrides[node_routes.get_request_context_dep] = auth

    # Services.
    application.dependency_overrides[info_routes.get_info_service] = (
        lambda: InfoService(StubInfoProvider(), userstore)
    )
    application.dependency_overrides[job_routes.get_job_service] = (
        lambda: JobService(datastore)
    )
    application.dependency_overrides[jobs_routes.get_job_service] = (
        lambda: JobService(datastore)
    )
    application.dependency_overrides[get_grid_service] = (
        lambda: GridService(datastore, _NullStatusstore())
    )

    # Node check-in (POST /api/node/): FileDatastore now satisfies NodeDatastore
    # (async update_node->Node + get_next_job). Auth for node_routes is wired above.
    application.dependency_overrides[node_routes.get_node_service] = (
        lambda: NodeService(datastore)
    )

    # Tier 1: RBAC (Rolestore) + user management.
    rbac = StaticRbacAuthorizer()
    if cfg.staticrbac.role_files or cfg.staticrbac.user_files:
        rbac.init(
            user_files=cfg.staticrbac.user_files,
            role_files=cfg.staticrbac.role_files,
            scan_interval_ms=cfg.staticrbac.scan_interval_ms,
            default_role=cfg.staticrbac.default_role,
        )

    # Salt relay wiring (gated on a `salt` module block). The relay is the
    # file-based queue seam shared by the GridMembers and AdminUserstore
    # adapters; constructing FileQueueRelayClient is lazy (it only stores the
    # queue_dir, no I/O). When salt is absent, gridmembers stays UNWIRED and the
    # AdminUserstore falls back to the not-configured placeholder (writes raise).
    admin_userstore: AdminUserstore
    if cfg.salt is not None:
        salt_relay = FileQueueRelayClient(
            cfg.salt.queue_dir, timeout_ms=cfg.salt.timeout_ms
        )
        salt_gridmembers = SaltGridMembersstore(salt_relay)
        # rbac (StaticRbacAuthorizer) supplies scan_now() for the role reload
        # the AdminUserstore performs after add/role mutations.
        admin_userstore = SaltAdminUserstore(salt_relay, userstore, rbac)

        application.dependency_overrides[gridmembers_routes.get_request_context_dep] = (
            auth
        )
        application.dependency_overrides[gridmembers_routes.get_gridmembers_service] = (
            lambda: GridMembersService(salt_gridmembers, rbac)
        )
    else:
        admin_userstore = _UnconfiguredAdminUserstore()

    # Note: rbac and userstore are captured once and shared across requests
    # (unlike the per-request Tier 0 service lambdas) — StaticRbac holds parsed
    # role/user maps + a lock, and the single userstore is shared by InfoService,
    # RolesService, and UsersService.
    application.dependency_overrides[roles_routes.get_request_context_dep] = auth
    application.dependency_overrides[users_routes.get_request_context_dep] = auth
    application.dependency_overrides[roles_routes.get_roles_service] = (
        lambda: RolesService(rbac)
    )
    application.dependency_overrides[users_routes.get_users_service] = (
        lambda: UsersService(userstore, admin_userstore, rbac)
    )

    # Tier 2: Elasticsearch storage adapter. Only wired when an `elastic`
    # (or `elasticsearch`) module block with a host is configured; otherwise the
    # events/case/detection/assistant routes stay unwired (Tier-0 default app is
    # unchanged). One shared ElasticClients (primary + remotes) backs all four
    # stores so the connection pool isn't fanned out per route.
    es_cfg = cfg.elasticsearch
    if es_cfg is not None and es_cfg.host_url:
        primary = build_async_client(
            es_cfg.host_url, es_cfg.username, es_cfg.password,
            verify_cert=es_cfg.verify_cert, timeout_ms=es_cfg.timeout_ms,
        )
        remotes = [
            build_async_client(
                host, es_cfg.username, es_cfg.password,
                verify_cert=es_cfg.verify_cert, timeout_ms=es_cfg.timeout_ms,
            )
            for host in es_cfg.remote_host_urls
        ]
        clients = ElasticClients(primary=primary, remotes=remotes)
        for client in clients.all_clients:
            application.router.on_shutdown.append(client.close)

        eventstore = ElasticEventstore(clients, es_cfg)
        casestore = ElasticCasestore(clients, es_cfg)
        detectionstore = ElasticDetectionstore(clients, es_cfg)
        assistantstore = ElasticAssistantstore(clients, es_cfg)
        assistant_manager = _UnconfiguredAssistantManager()

        application.dependency_overrides[events_routes.get_request_context_dep] = auth
        application.dependency_overrides[case_routes.get_request_context_dep] = auth
        application.dependency_overrides[detection_routes.get_request_context_dep] = (
            auth
        )
        application.dependency_overrides[assistant_routes.get_request_context_dep] = (
            auth
        )

        application.dependency_overrides[events_routes.get_events_service] = (
            lambda: EventsService(eventstore)
        )
        application.dependency_overrides[case_routes.get_case_service] = (
            lambda: CaseService(casestore)
        )
        # Detection/assistant stores are ES-backed; their AI collaborators
        # (engines, manager) are behavioral ports out of scope here — pass empty
        # engines + the existing RBAC authorizer, and a not-configured manager.
        application.dependency_overrides[detection_routes.get_detection_service] = (
            lambda: DetectionService(detectionstore, {}, rbac)
        )
        application.dependency_overrides[assistant_routes.get_assistant_service] = (
            lambda: AssistantService(assistantstore, assistant_manager)
        )

    return application
