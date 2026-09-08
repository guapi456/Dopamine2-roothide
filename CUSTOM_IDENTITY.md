# 出发定制身份（最新上游）

- 上游分支：`v2.4.9.x`
- 上游提交：`f72767b369c6440e0683439d78c25255e1d37012`（tag `26`）
- BaseBin 版本：`2.4.9.25`

## 应用身份

| 角色 | 显示名 | iOS Bundle ID | App 目录 | 可执行文件 | Debian 包名 |
|---|---|---|---|---|---|
| 主 App | 出发 | `com.departure.launcher` | `Dop.app` | `Dopamine` | 不适用 |
| 越狱商店 | 商店 | `com.departure.marketapp` | `Sileo.app` | `Sileo` | `org.coolstar.sileo` |
| RootHide Manager | 清理 | `com.departure.cleaner` | `RTHD.app` | `RootHide` | `com.roothide.manager` |

Sileo 与 RootHide 的 Debian 包名保持官方值。这两个字段属于 APT/dpkg 依赖 ABI，
不是 iOS Bundle ID；保留它们可避免插件依赖、升级和包管理状态失配。

## RootHide 屏蔽联动

- `com.departure.launcher` 已写入 RootHide 静态内建 App/敏感 App 集合。
- 引导时仍会把主 App Bundle ID 写入 `/basebin/.AppIdentifier`，形成动态登记。
- `com.departure.launcher`、`com.departure.marketapp`、`com.departure.cleaner`
  都会写入清理 App 内置的 `varCleanRules.json`，覆盖偏好、缓存和快照等痕迹。
- Sileo 的旧 Bundle ID 在 Mach-O 中按等长新 ID 原位修补，再由 `ldid` 重签。
- RootHide 的 `postinst` 会同步改为 `uicache -p /Applications/RTHD.app`，
  并对 `/Applications/RTHD.app/RootHide` 执行 `chown`/`chmod +s`。

## 构建门禁

CI 会在上传前验证：

1. TIPA 仅包含 `Payload/Dop.app`，不存在 `Payload/Dopamine.app`。
2. 三个 App 的 Bundle ID、显示名、目录和可执行文件一致。
3. 两个嵌入 `.deb` 的 control/data tar 均无 PAX 扩展头。
4. 清理的 postinst 不保留 `RootHide.app` 路径。
5. RootHide 清理规则包含三个新 Bundle ID，不保留对应旧 ID。

身份和路径重命名可以减少基于固定字符串的识别，但不能承诺任何越狱环境对
所有第三方检测方案“完全不可检测”；内核状态、运行时行为和设备侧残留仍可能被检测。
