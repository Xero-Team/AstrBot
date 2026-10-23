from astrbot.core.platform.sources.discord.components import DiscordEmbed


def test_discord_embed_keeps_explicit_black_color():
    component = DiscordEmbed.__new__(DiscordEmbed)
    object.__setattr__(component, "title", None)
    object.__setattr__(component, "description", None)
    object.__setattr__(component, "color", 0)
    object.__setattr__(component, "url", None)
    object.__setattr__(component, "thumbnail", None)
    object.__setattr__(component, "image", None)
    object.__setattr__(component, "footer", None)
    object.__setattr__(component, "fields", [])

    embed = component.to_discord_embed()

    assert embed.color is not None
    assert embed.color.value == 0
