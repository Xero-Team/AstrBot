# IPv6

Many home connections now have a public IPv6 address. This page covers how to use IPv6 with AstrBot.

## Prepare

On a server you can skip this section. Set the listen host and reach AstrBot over public IPv6.

On a home broadband link, inbound access is usually blocked. The steps below use China Telecom Tianyi as an example.

Open the optical modem admin panel. `192.168.1.1` is a common address:

![modem admin](https://files.astrbot.app/docs/source/images/ipv6/index.png)

If you need to change advanced modem or router settings, contact your ISP, device vendor, or installer and use a compliant way to obtain admin access.

Then: Security → Firewall

![firewall](https://files.astrbot.app/docs/source/images/ipv6/firewall.png)

Set the firewall level to low, and disable IPv6 SESSION. Leaving SESSION on blocks inbound access from outside.

## Start the service

```bash
astrbot run
# The log may print an IPv6 URL such as
# http://[ipv6-address]:6185
```

AstrBot listens on `127.0.0.1` by default. To reach WebUI over IPv6 or a remote network, set `dashboard.host` in `data/cmd_config.json` to `::` or the intended address, then restart AstrBot.
