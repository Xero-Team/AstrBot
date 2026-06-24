from __future__ import annotations

from astrbot.core.skills._skill_manager_discovery import SkillManagerDiscoveryMixin
from astrbot.core.skills._skill_manager_listing import SkillManagerListingMixin


class SkillManagerInventoryMixin(
    SkillManagerDiscoveryMixin,
    SkillManagerListingMixin,
):
    pass
