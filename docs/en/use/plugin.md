# Plugins

AstrBot calls plugins Stars. A Star can register commands, tools, event listeners, and optional Dashboard pages.

Open **Plugins**. The per-profile plugin set is under **Config → Plugins**. Development is in the [plugin guide](/en/dev/star/plugin-new).

## Manage in WebUI

The **Installed** tab enables, disables, reloads, and uninstalls plugins, and shows load errors.

After load, unload, reload, enable, or disable, AstrBot immediately rebuilds the command catalog and refreshes enabled Telegram / Discord native command surfaces. You do not wait for the next message.

A failed load shows the error and **Try one-click reload**. Fix the environment or code, then reload without restarting the process.

The bottom-right **+** installs from a repository URL or a local file. Quote URLs that contain `&` or `#`. The same quoting applies to the command installer.

Enable and disable require `extension.manage`. URL installs require `extension.plugin_install` and a Dashboard step-up. See [Authorization](./authorization).

## Marketplace

The **Marketplace** tab uses an upstream compatibility source, not an official market for this fork:

1. It requests the upstream `cloud.astrbot.app` market JSON first;
2. On failure it falls back to `AstrBotDevs/AstrBot_Plugins_Collection` and its CDN.

Appearing in that list does not mean the plugin runs on this branch. This fork requires Python 3.14+ and does not support the old plugin API.

Check `astrbot_version` in the plugin metadata before installing. Plugins that need a Dashboard page must declare both:

- `requires.dashboard_extension: 1`
- an Extension Protocol v1 `assets.v1.json` manifest

If it is incompatible, install from a URL or file, or skip the plugin. Neither this fork nor upstream guarantees third-party plugin safety. The protocol is in [Dashboard extensions](/en/dev/star/plugin-dashboard-extension).

## Per-profile plugin set

Profile field `plugin_set` defaults to `["*"]`: every plugin that is **not disabled on the plugin page**. An empty list means this profile uses no plugins.

Priority:

1. Global disable on the plugin page: profile checkboxes do not load it.
2. Profile `plugin_set`: limits plugins for that profile.
3. [Custom rules](./custom-rules) session plugin lists: narrow further per UMO.

Different profiles can enable different sets. Saving rebuilds that profile's command catalog.

## Commands

- `/plugin list`: list loaded plugins.
- `/plugin show <plugin-name>`: version, author, and registered commands.
- `/plugin disable <plugin-name>`: disable; needs `extension.manage`.
- `/plugin enable <plugin-name>`: enable; needs `extension.manage`.
- `/plugin install <repository-url>`: install; needs `extension.plugin_install` and Dashboard step-up.

`/plugin` alone prints the subcommand tree. Example:

```text
/plugin install 'https://example.com/plugin.git?ref=main&source=manual#install'
```

The old short name `/plugin ls` is not an alias. See [Built-in commands](./command).

## Common misconfigurations

1. Marketplace install succeeds, then startup logs a Python or API incompatibility.
2. The plugin is disabled on the plugin page, but you keep ticking it in `plugin_set`.
3. The plugin ships a Dashboard page without `requires.dashboard_extension: 1`, so the page never appears.
4. Installing from an IM message without step-up rights.
