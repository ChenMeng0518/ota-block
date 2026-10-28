#!/usr/bin/env python3
"""
生成屏蔽 iOS OTA 更新的 Configuration Profile (.mobileconfig)。

原理
----
iOS 检查系统更新时，会向 Apple 的软件更新清单服务 gdmf.apple.com 发起请求，
携带设备的产品类型、当前构建版本和 AssetAudience。服务器按 audience 在对应
清单里查找匹配固件并返回。

本 profile 是一个 com.apple.dnsSettings.managed 载荷（Apple 官方 DNS 设置类型），
它建立一条 DoH（DNS over HTTPS）规则，但只对 SupplementalMatchDomains 中列出的
域名生效 —— 也就是仅把 gdmf.apple.com 的解析交给 ServerURL 指定的服务器。

ServerURL 指向 RFC 2606 保留顶级域 .invalid 下的一个主机名，该域名在 DNS 根区
中不存在，解析必然返回 NXDOMAIN。于是：

    更新检查 → 解析 gdmf.apple.com → DoH 查询失败 → 拿不到固件清单 → 检查终止

失败方向是 fail-closed：报错「无法检查更新」，而不是回退到系统 DNS 去查。
其余所有域名的解析完全不受影响。

无有效期（不写 RemovalDate），不会像 tvOS 描述文件那样被 Apple 到期回收。

用法
----
    python3 gen.py            # 生成 block-ota.mobileconfig
    python3 gen.py --check    # 只校验现有文件与生成结果是否一致

输出是确定性的：UUID 由 uuid5 派生，同样的输入永远得到逐字节相同的文件，
所以仓库里的文件可以用 sha256 校验。
"""

import argparse
import hashlib
import plistlib
import sys
import uuid
from pathlib import Path

# 固定的 UUID 命名空间，保证生成结果可复现
NAMESPACE = uuid.UUID("6f1a2b3c-4d5e-5f60-8712-9a0b0c0d0e0f")

ORG = "chenmeng0518"
PREFIX = "dev.chenmeng0518.otablocker"

# RFC 2606 / RFC 6761 保留域名，保证永远不解析
DOH_SERVER = "https://ota.invalid"

# 只拦更新清单服务。刻意不包含 mesu.apple.com：
# 该域名同时服务大量非更新类 MobileAsset（语音、系统资源等），拦了会误伤。
BLOCKED_DOMAINS = ["gdmf.apple.com"]

OUT = Path(__file__).with_name("block-ota.mobileconfig")


def _uid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name)).upper()


def build() -> dict:
    dns_payload = {
        "PayloadType": "com.apple.dnsSettings.managed",
        "PayloadVersion": 1,
        "PayloadIdentifier": PREFIX + ".dns",
        "PayloadUUID": _uid("dns-payload"),
        "PayloadDisplayName": "OTA Update Blocker (DNS)",
        "PayloadDescription": (
            "将 gdmf.apple.com 的解析重定向到一个不存在的主机，"
            "使系统更新检查无法获取固件清单。"
        ),
        "DNSSettings": {
            "DNSProtocol": "HTTPS",
            "ServerURL": DOH_SERVER,
            "SupplementalMatchDomains": list(BLOCKED_DOMAINS),
        },
        "OnDemandRules": [{"Action": "Connect"}],
    }

    return {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": PREFIX,
        "PayloadUUID": _uid("root"),
        "PayloadDisplayName": "OTA Update Blocker",
        "PayloadOrganization": ORG,
        "PayloadDescription": (
            "屏蔽 iOS OTA 系统更新。仅影响 gdmf.apple.com 的解析，"
            "其余网络请求不受影响。无有效期，删除本描述文件即可恢复更新。"
        ),
        "ConsentText": {
            "default": (
                "本描述文件仅添加一条 DNS 规则：把 gdmf.apple.com 的解析"
                "交给一个不存在的主机名（ota.invalid，RFC 2606 保留域），"
                "从而让系统更新检查失败。\n\n"
                "不包含证书、VPN 隧道或代理配置，无法拦截或篡改其它任何流量。"
                "源码见仓库，可自行核对后生成。"
            )
        },
        "PayloadContent": [dns_payload],
    }


def render() -> bytes:
    return plistlib.dumps(build(), fmt=plistlib.FMT_XML, sort_keys=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="校验现有文件，不写入")
    args = ap.parse_args()

    data = render()

    if args.check:
        if not OUT.exists():
            print(f"缺少文件: {OUT}", file=sys.stderr)
            return 1
        cur = OUT.read_bytes()
        if cur == data:
            print(f"一致: {OUT.name} sha256={hashlib.sha256(cur).hexdigest()}")
            return 0
        print("不一致：仓库里的文件与生成结果不同", file=sys.stderr)
        return 1

    OUT.write_bytes(data)
    print(f"已写入 {OUT} ({len(data)} 字节)")
    print(f"sha256={hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
