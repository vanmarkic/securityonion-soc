from fastapi import FastAPI

from src.adapters.filedatastore.store import FileDatastore
from src.adapters.kratos.userstore import KratosUserstore
from src.adapters.statickeyauth.middleware import StaticKeyAuth
from src.adapters.staticrbac.authorizer import StaticRbacAuthorizer
from src.adapters.stub.info_provider import StubInfoProvider
from src.adapters.stub.userstore import StubUserstore
from src.api import (
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
from src.domain.status import Status
from src.domain.user import User
from src.ports.users import Userstore
from src.services.grid_service import GridService
from src.services.info_service import InfoService
from src.services.job_service import JobService
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


def create_app(config_path: str | None = None) -> FastAPI:
    """Build a fresh FastAPI app with Tier 0 adapters wired in."""
    application = _build_base_app()

    cfg = load_config(config_path) if config_path else AppConfig()

    auth = StaticKeyAuth(cfg.statickeyauth.api_key, cfg.statickeyauth.anonymous_cidr)
    datastore = FileDatastore(job_dir=cfg.filedatastore.job_dir)

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

    # NodeService wiring deferred: FileDatastore does not satisfy NodeDatastore
    # (needs async update_node->Node + get_next_job).

    # Tier 1: RBAC (Rolestore) + user management.
    rbac = StaticRbacAuthorizer()
    if cfg.staticrbac.role_files or cfg.staticrbac.user_files:
        rbac.init(
            user_files=cfg.staticrbac.user_files,
            role_files=cfg.staticrbac.role_files,
            scan_interval_ms=cfg.staticrbac.scan_interval_ms,
            default_role=cfg.staticrbac.default_role,
        )

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

    return application
