# 构建与下载

本分支由 GitHub Actions 在 `macos-14` 上构建 TrollStore `.tipa`。

1. 打开仓库的 **Actions**。
2. 选择 **构建 出发 TrollStore 包**。
3. 打开最新的绿色成功运行。
4. 在 **Artifacts** 下载 `出发-2.4.9.25-<提交短哈希>.tipa`。
5. 解压下载的 Actions artifact，然后用 TrollStore 安装其中的 `.tipa`。

为避免旧 `RootHide.app`、旧 Bundle ID 和 dpkg 状态同时存在，建议先在旧版本里
执行“移除越狱”，重启设备，再安装新 `.tipa` 并重新越狱。
