"""Process-global advanced-effect backend."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .effect_active_workspace import ActiveEffectWorkspaceRepository
from .effect_application import EffectStudioApplication
from .effect_deployment_diagnostics import EffectDeploymentDiagnosticBridge
from .effect_deployments import EffectDeploymentRepository
from .effect_diagnostics import EffectDiagnosticHistory
from .effect_identity import EffectDeviceCache
from .effect_migration import EffectMigrationBackup
from .effect_preview import EffectPreviewManager
from .effect_runtime import EffectDeploymentEngine
from .effect_scene_defaults import NativeSceneDefaultRepository
from .effect_storage import EffectLibraryRepository
from .effect_template_defaults import CatalogueTemplateDefaultRepository
from .effect_user_state import EffectUserStateRepository


@dataclass(slots=True)
class EffectBackend:
    library: EffectLibraryRepository
    deployments: EffectDeploymentRepository
    device_cache: EffectDeviceCache
    active_workspaces: ActiveEffectWorkspaceRepository
    user_state: EffectUserStateRepository
    scene_defaults: NativeSceneDefaultRepository
    template_defaults: CatalogueTemplateDefaultRepository
    application: EffectStudioApplication
    engine: EffectDeploymentEngine
    preview: EffectPreviewManager
    diagnostics: EffectDiagnosticHistory
    _diagnostic_bridge: EffectDeploymentDiagnosticBridge
    _migration_backup: EffectMigrationBackup

    @classmethod
    async def async_create(cls, hass: HomeAssistant) -> EffectBackend:
        migration_backup = await EffectMigrationBackup.async_prepare(hass)
        library = EffectLibraryRepository(hass)
        deployments = EffectDeploymentRepository(hass)
        device_cache = EffectDeviceCache(hass)
        active_workspaces = ActiveEffectWorkspaceRepository(hass)
        user_state = EffectUserStateRepository(hass)
        scene_defaults = NativeSceneDefaultRepository(hass)
        template_defaults = CatalogueTemplateDefaultRepository(hass)
        loaded = False
        try:
            library_snapshot = await library.async_load()
            deployment_snapshot = await deployments.async_load()
            await device_cache.async_load()
            await active_workspaces.async_load()
            await deployments.async_reconcile_library_hashes(library_snapshot.items)
            await device_cache.async_reconcile_library_hashes(library_snapshot.items)
            deployment_snapshot = deployments.snapshot()
            await user_state.async_load()
            await scene_defaults.async_load()
            await template_defaults.async_load()
            loaded = True
        finally:
            if not loaded:
                await migration_backup.async_rollback()
        diagnostics = EffectDiagnosticHistory()
        engine = EffectDeploymentEngine(
            deployments,
            device_cache,
            active_workspaces,
        )
        return cls(
            library=library,
            deployments=deployments,
            device_cache=device_cache,
            active_workspaces=active_workspaces,
            user_state=user_state,
            scene_defaults=scene_defaults,
            template_defaults=template_defaults,
            application=EffectStudioApplication(library, deployments, user_state, device_cache),
            engine=engine,
            preview=EffectPreviewManager(
                hass,
                device_cache,
                scene_defaults,
                template_defaults,
                diagnostics,
                active_workspaces=active_workspaces,
            ),
            diagnostics=diagnostics,
            _diagnostic_bridge=EffectDeploymentDiagnosticBridge(
                deployments,
                diagnostics,
                deployment_snapshot,
            ),
            _migration_backup=migration_backup,
        )

    async def async_complete_storage_migration(self) -> None:
        committed = False
        try:
            await self._migration_backup.async_commit()
            committed = True
        finally:
            if not committed:
                await self._migration_backup.async_rollback()
