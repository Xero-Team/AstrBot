from astrbot.core.skills._skill_manager_discovery import SkillManagerDiscoveryMixin
from astrbot.core.skills._skill_manager_listing import SkillManagerListingMixin


class SkillManagerInventoryMixin(
    SkillManagerDiscoveryMixin,
    SkillManagerListingMixin,
):
    pass
