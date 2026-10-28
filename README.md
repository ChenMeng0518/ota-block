# OTA Update Blocker

一个自己生成的 iOS 配置描述文件（Configuration Profile），用来屏蔽 OTA 系统更新，让设备停在当前固件上等越狱或养老。

不依赖任何第三方站点：源码、生成脚本、产物都在这个仓库里，任何人可以复现和核对。

---

## 它为什么有效

iOS 检查系统更新时，会向 Apple 的软件更新清单服务 `gdmf.apple.com` 发起请求，携带三样东西：设备的产品类型（如 `iPhone12,8`）、当前构建版本、以及一组 `AssetAudience` 标识。Apple 按 audience 在对应清单里查找匹配的固件并返回结果。

本 profile 是一个 `com.apple.dnsSettings.managed` 载荷——Apple 官方的 DNS 设置类型。它建立一条 DNS over HTTPS 规则，但**只对 `SupplementalMatchDomains` 中列出的域名生效**，也就是仅把 `gdmf.apple.com` 的解析交给指定的 DoH 服务器。

`ServerURL` 指向 `https://ota.invalid`。`.invalid` 是 RFC 2606 保留给「保证不存在」用途的顶级域，在 DNS 根区中不存在，解析必然返回 NXDOMAIN。

于是链路变成：

```
更新检查 → 解析 gdmf.apple.com → DoH 查询失败 → 拿不到固件清单 → 检查终止
```

失败方向是 **fail-closed**：报错「无法检查更新」，而不是回退到系统 DNS 继续查。

其余所有域名的解析完全不受影响——`SupplementalMatchDomains` 是白名单语义，只有列表里的域名走这个 DoH 服务器。

## 它做了什么，没做什么

**做了：**

- 一条 DoH 规则，仅作用于 `gdmf.apple.com`
- `OnDemandRules` 设为常连

**没做（可自行核对源码）：**

- 不含根证书，无法解密或篡改 TLS 流量
- 不含 VPN 隧道、不含代理配置
- 不含 `mesu.apple.com`。直觉上「多拦一个更保险」是错的：mesu 同时服务大量非更新类的 MobileAsset（语音资源、系统资源等），拦了会误伤
- 不写 `RemovalDate`，无有效期，不会像 tvOS 描述文件那样被到期回收或静默删除

---

## 仓库文件

| 文件 | 说明 |
|---|---|
| `gen.py` | 生成脚本。UUID 由 uuid5 派生，输出确定 |
| `block-ota.mobileconfig` | 生成产物，直接安装这个 |

## 安装

### 方式一：AirDrop（不联网）

把 `block-ota.mobileconfig` AirDrop 到目标设备 → 提示「描述文件已下载」→ 设置 顶部「已下载的描述文件」→ 安装 → 输入密码 → 重启。

不需要联网，也不需要签名。签名只在 MDM 强制推送时才有要求。

### 方式二：raw 直链

用设备 Safari 打开：

```
https://raw.githubusercontent.com/ChenMeng0518/ota-block/main/block-ota.mobileconfig
```

GitHub raw 对该扩展名返回 `application/octet-stream`，Safari 会下载而不是当文本渲染。

### 方式三：本机临时服务

```bash
python3 -m http.server 8000
# 设备浏览器访问 http://<你的内网IP>:8000/block-ota.mobileconfig
```

---

## 验收标准（必须实测）

装完重启，进入 **设置 → 通用 → 软件更新**：

- 显示「无法检查更新」或类似报错 → **生效**
- 正常列出新版本 → **未生效**

未生效时优先怀疑两件事：一是开着 VPN 或其他 DNS 代理覆盖了规则；二是 iOS 大版本更换了更新清单端点（见下方「已知限制」）。

## 卸载

设置 → 通用 → VPN 与设备管理（或「描述文件」）→ 选中 `OTA Update Blocker` → 移除 → 重启。

移除后更新检查立即恢复。

---

## 已知限制

**VPN 冲突。** 其他 VPN 或 DNS 代理会覆盖本规则。如果必须开 VPN，需要在 VPN 侧单独加一条针对 `gdmf.apple.com` 的拦截规则。

**Apple Watch。** 配对的手表也无法检查更新。需要更新手表时临时移除 profile。

**小红点残留。** 已下载的更新包会留在储存空间里。到 设置 → 通用 → iPhone 储存空间 删掉对应更新包，通知角标才会消失。

**端点变更风险。** 本方案假设 iOS 仍通过 `gdmf.apple.com` 获取更新清单。iOS 27 已移除全部 MDM 的 OS Update 命令（`ScheduleOSUpdateScanCommand`、`AvailableOSUpdatesCommand`、`ScheduleOSUpdateCommand`、`OSUpdateStatusCommand`），更新状态改走声明式设备管理通道。若 Apple 同时更换了设备侧的清单端点，本 profile 会**静默失效**——不报错，只是拦不住。因此装完必须按上面的验收标准实测。

**无签名。** 手动安装的 profile 本来就不签名。完整性靠仓库源码 + 下面的 sha256 核对，不靠证书。

---

## 校验

```bash
python3 gen.py --check    # 校验仓库里的文件与生成结果是否一致
sha256sum block-ota.mobileconfig
```

期望值：

```
18ff0aefbb9832f787e59c6d2cd6014a189ecb428f2959a04aa9cf8094ccf2bd
```

如果哈希对不上，说明文件被改过，不要安装。

## 许可

MIT
