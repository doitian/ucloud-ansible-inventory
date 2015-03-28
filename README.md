# UCloud Ansbile Inventory

本项目是[UCloud三周年API开发大赛](http://www.ucloud.cn/sdk/index)参赛作品，如果觉得有用，可以[投上一票](https://campaign.gitcafe.com/ucloud-sdk-2015/cadidates?tags%5B%5D=工具类)

[UCloud][]'s Ansible  [Dynamic Inventory][] script

[Ansible][] 是自动化配置工具，Dynamic Inventory 允许使用脚本获到需要配置的机器列表和信息。

可以参考 hosts.yml 的示例 ansible playbook 如何为所有 uhost 生成 hosts 文件来方便访问，如果换成调用 DNSPod API 就能实现自动更新 DNS 记录。


# 开始

## 安装

可以直接 clone 本项目作为 ansible playbook 的根目录，或者把 inventory 目录复制到您 ansible playbook 的根目录下，并使用 inventory 目录作为 inventtory host file

> 设置 host file 可以使用命令参数 `-i` 或者在 ansible.cfg 中配置，参考本项目中的 ansible.cfg

如果您还有其它的 inventory 条目，也放到 inventory 目录下，参考 ansible multiple inventory sources [相关文档](http://docs.ansible.com/intro_dynamic_inventory.html#using-multiple-inventory-sources)

脚本  ucloud.py 使用 python 2，在默认 python 版本为 3 的环境下使用自行修改 ucloud.py 的第一行。

## 配置

复制示例配置文件并进行修改。配置文件必须命名为 `ucloud.ini` 并且和 `ucloud.py` 在同一目录下。因为 ucloud.ini 会包含私密信息，注意不要提交到公共的版本控制仓库中。

	cp inventory/ucloud.example.ini inventory/ucloud.ini

首先需要修改 ucloud API 的连接信息，`region` 配置参考 [数据中心列表](http://docs.ucloud.cn/api/regionlist.html)。目前只支持单个机房，需要跨机房复制几份 `ucloud.py`，注意配置文件的名字要和脚本名字一致，比如 `ucloud_east.py` 读取配置文件 `ucloud_east.ini`，并且缓存文件不能同名。

	[ucloud]
	public_key = changeme
	private_key = changeme
	base_url = http://api.spark.ucloud.cn/
	region = cn-north-03


然后需要配置 SSH 连接信息，uhost, ucdn 和 ulb 分别对应云主机、CDN 和负载均衡的配置，配置中支持 Python 的 `%` 替换，比如 uhost 中的 `%(Name)s` 会替换成云主机的名称。括号中可以是任何 UCloud API 返回结果中的字段，另外为了方便使用 IP，还有以下额外字段可以使用

-	`BgpIP` BGP 机房出口 IP
-	`InternationalIP` 国际出口 IP
-	`TelecomIP` 电信出口 IP
-	`UnicomIP` 联通出口 IP
-	`PublicIP` 出口 IP，从 `BgpIP`, `InternationalIP`, `TelecomIP` 和 `UnicomIP` 中返回第一个存在的 IP

配置文件还支持对某个 uhost, ucdn 或者 ulb 进行单独配置，只要新建新的小节，以资源类型和名称作为小节的名字，比如 uhost ops 会优先使用 `uhost.ops` 小节中的配置，见下面例子。命名规则见本文档后面的内容。

	[uhost.ops]
	host = ops.example.com
	port = 2222
	user = ops

## 测试

直接运行脚本 `ucloud.py`，没有错误应该会打印出符合 ansible dynamic inventory 要求的 JSON，然后可以运行 ansible 列表所有机器

	ansible all -i inventory --list-hosts

如果一切正常可以测试下 demo playbook hosts.yml

	ansible-playbook hosts.yml

该 playbook 会在当前目录生成 hosts，如果覆盖 /etc/hosts 可以使用里面配置的主机名比如 `ops.ucloud` 来访问 ucloud 主机了。而如果云主机已经配置能使用 ubuntu sudo 进行 ansible 操作，那么这些主机名也更新到所有的云主机上了。

## 缓存

示例配置中默认开启了缓存，如果改变了 ucloud 的设置想要立即更新主机信息，可以手动执行下面命令刷新缓存

	inventory/ucloud.py --refresh-cache

# 命名规则

## 主机名

即相应资源在 ansible 中使用的 host 名称。

uhost 使用 Name 字段, ulb 使用 ULBName, ucdn 使用 Domain

所有名称都将除了字母，数字和 `-` `_` 的其它字符替换成了 `_`，比如 ucdn test.example.com 对应的名称是 `test_example_com`

## 主机组

首先所有的资源都按照类型进行了分组， uhost, ulb, ucdn 分别对应 ansible 的组 uhosts, ulbs 和 ucdns

另外 uhost 还支持自定义分组，规则是使用『业务组名称』(对应 API 返回结果中的 Tag)。业务组名称使用英文逗号分隔之后并加上 `tag_` 前缀即为该主机要加入的 ansible 主机组。比如主机 ops 的业务组名称是 `dev,public` 那么在 ansible 中会包含在组 `tag_dev` 和 `tag_public` 中。

## 主机变量名

所有 API 返回结果以及上面提到的额外 IP 字段都会嵌套在主机变量 ucloud 下，比如在 jinja2 模板中引用出口 IP

    {{ ucloud.PublicIP }}

[ansible]: http://www.ansible.com
[dynamic inventory]: http://docs.ansible.com/intro_dynamic_inventory.html
[ucloud]: http://www.ucloud.cn
