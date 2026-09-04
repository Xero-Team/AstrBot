# IPv6 support

Many home and cloud connections support IPv6. This page explains how to make the AstrBot WebUI listen on IPv6 and how to troubleshoot external access.

## Prepare

For a cloud or hosted server, confirm that it has a public IPv6 address and that the security group and host firewall allow the WebUI port (default `6185`).

On a home broadband link, the modem or router often blocks inbound connections. The steps below use China Telecom Tianyi as an example; menu names vary by device.

Open the optical modem or router admin panel. `192.168.1.1` is a common address:

![modem admin](https://files.astrbot.app/docs/source/images/ipv6/index.png)

Open **Security → Firewall**.

![firewall](https://files.astrbot.app/docs/source/images/ipv6/firewall.png)

Do not disable the whole firewall or leave it at a low level just to expose AstrBot. Allow only the required port and trusted sources. If the device offers an IPv6 inbound rule or firewall exception, prefer that. The meaning of IPv6 SESSION or similar session-protection options varies by vendor; confirm that the option is actually blocking inbound access to the target port before changing it.

Keep WebUI authentication enabled for public access. Do not expose the administration panel without protection; prefer an HTTPS reverse proxy, access control, or VPN.

If you need to change advanced modem or router settings, contact your ISP, device vendor, or installer and use a compliant way to obtain admin access.

## Start the service

```bash
astrbot run
# Check the log for the actual listening address, for example:
# http://[2001:db8::10]:6185
```

AstrBot listens on `127.0.0.1` by default and accepts local connections only. To listen on IPv6, set `dashboard.host` in `data/cmd_config.json` to `::` or the intended IPv6 address, save the file, and restart AstrBot.

Open the address from the log in a browser. IPv6 addresses must be enclosed in brackets, for example `http://[2001:db8::10]:6185`.

If it still fails, check in order:

1. AstrBot listens on `::` or the intended IPv6 address;
2. the cloud security group, host firewall, modem, and router allow `6185`;
3. the client network has IPv6 connectivity;
4. you are using an HTTPS reverse proxy or VPN instead of exposing WebUI directly.
