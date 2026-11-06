# 第三方来源与署名

## bingaha/dnfhelper-helper

来源：https://github.com/bingaha/dnfhelper-helper

基准版本：`883a74b6d28e780cde5f280fbe261382bb01eede`。

原项目为 GPL-3.0，保留根目录 LICENSE。本桌面程序在其基础上增加多账户、调度、界面和活动实现。

## fzls/djc_helper

作者：fzls（风之凌殇）。

来源：https://github.com/fzls/djc_helper

参考版本：`66337b46d908bd41c482c32ad5c3e10c72a4bad8`（2026-11-03）。

活动接口、流程 ID、签名方式、活动日期与礼包处理参考其 `djc_helper.py`、`urls.py`、`sign.py` 等源码。道聚城协议使用其公开的 RSA 公钥和签名参数，公钥不是用户私钥。

项目使用者于 2026-11-06 明确表示已获得作者授权，要求接入并公开发布。本次依据该授权确认实施；这份记录不替代或扩大作者对原仓库代码的授权，也不声称原仓库采用 GPL-3.0。

新增桌面集成代码与修改遵循本项目 GPL-3.0；原作者的权利和署名保留。未整包引入原项目的付费检查、统计上报、云端匹配、自动更新或密码登录机制。

## 运行依赖

requests：Apache-2.0；PyCryptodome：BSD / 公有领域组件；tzdata：Apache-2.0 / IANA 时区数据；Python/Tk 与 PyInstaller 按各自许可证分发。PyInstaller 的打包例外允许分发生成的可执行文件。
