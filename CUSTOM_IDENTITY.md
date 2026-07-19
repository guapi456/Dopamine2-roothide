# 出发 / 商店 / 清理 identity map

Build baseline: RootHide Dopamine `v2.4.9.x`, version `2.4.9.25`.

| Component | Display name | Bundle or package identifier |
|---|---|---|
| Main application | 出发 | `com.departure.launcher` |
| Package manager | 商店 | `org.coolstar.SileoStore` / `org.coolstar.sileo` |
| RootHide manager | 清理 | `com.roothide.manager` |

`CFBundleIdentifier` and Debian `Package` fields use ASCII reverse-domain IDs.
The main app uses its custom identifier, while 商店 and 清理 retain their upstream
runtime identifiers and physical payload paths for APT and RootHide compatibility.
The build workflow runs `Scripts/repack_bundled_apps.py` with `ldid`, so the two
prebuilt package-manager applications are re-signed after their Chinese display
names are updated.
