"""Shared device identity for the Svitlo Poltava entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SvitloPoltavaCoordinator


class PoltavaEntity(CoordinatorEntity[SvitloPoltavaCoordinator]):
    """One device for the selected queue."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SvitloPoltavaCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> DeviceInfo:
        queue = self.coordinator.queue
        return DeviceInfo(
            identifiers={(DOMAIN, queue)},
            manufacturer="e-potashkin",
            model=f"Queue {queue}",
            name=f"Svitlo Poltava {queue}",
            configuration_url="https://github.com/e-potashkin/svitlo_poltava",
        )
