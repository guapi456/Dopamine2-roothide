# 出发 / 商店 / 清理 identity map

Build baseline: RootHide Dopamine `v2.4.9.x`, version `2.4.9.25`.

| Component | Display name | Bundle or package identifier |
|---|---|---|
| Main application | 出发 | `com.departure.launcher` |
| Package manager | 商店 | `com.departure.shopfront` / `com.departure.shop` |
| RootHide manager | 清理 | `com.departure.cleaner` |
| Mach service | — | `com.departure.coordinator` |
| Download launch daemon | — | `com.departure.transferd` |
| Startup launch daemon | — | `com.departure.initializer` |

`CFBundleIdentifier` and Debian `Package` fields use ASCII reverse-domain IDs;
the Chinese names are the labels shown in SpringBoard and package-management UI.
The build workflow runs `Scripts/repack_bundled_apps.py` with `ldid`, so the two
prebuilt package-manager applications are re-signed after their payload,
metadata, and package IDs are updated.
