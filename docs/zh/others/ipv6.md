# IPv6支持

目前ipv6普及度很高，很多家庭宽带都支持ipv6,且具有公网ipv6地址，本教程将介绍如何在astrbot中充分利用ipv6。

# 准备

如果你是服务器环境，可以直接跳过以下内容，因为无需过多配置即可通过指定host，从而通过公网ipv6访问astrbot服务

如果你是家庭宽带环境，处于安全考虑，从外部无法直接访问，需按照以下步骤修改
这里以中国电信天翼宽带为例

进入光猫后台面板
你可以试试192.168.1.1

如图所示：
![image](https://files.astrbot.app/docs/source/images/ipv6/index.png)
如需修改光猫或路由器的高级配置，请优先联系你的运营商、设备厂商或网络安装人员，使用合规方式获取管理权限。

进入后菜单如下
![image](https://files.astrbot.app/docs/source/images/ipv6/index.png)

依此点击：安全-防火墙
![image](https://files.astrbot.app/docs/source/images/ipv6/firewall.png)
将防火墙等级设置为低
同时将启用IPV6 SESSEION关闭（此选项开启后将无法从外部访问）

# 启动服务

```bash
astrbot run
# 不出意外，你可以在输出里面看到24开头，一长串的ipv6链接
# http://[ipv6地址]:6185
```

当前分支默认使用 `::` 监听地址，并启用双栈支持。除非你明确改过配置，否则通常不需要再手动调整 `host`。
