# 零基础构建

1. 把本目录的修改提交到你自己的 `departure-v2.4.9.25` 分支。
2. 打开 GitHub 仓库的 **Actions** 页面。
3. 选择 **构建 出发 TrollStore 包**。
4. 点击 **Run workflow**，分支选择 `departure-v2.4.9.25`。
5. 构建完成后，在页面底部下载 `出发-版本号.tipa` 工件并解压一次。
6. 在手机中把得到的 `.tipa` 分享给 TrollStore 安装。

首次换用这组身份前，先在原版越狱环境中执行“移除越狱”，重启后删除原版
Dopamine/RootHide Manager/Sileo，再安装“出发”。这样可避免旧 bootstrap 中的
官方 package ID、旧 launchd label 与新身份并存。
