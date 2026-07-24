# Aurum Agent Web

基于 Vue 3、TypeScript、Vite、Pinia 与 Ant Design Vue 的浏览器端，覆盖前两个阶段的
登录注册、账户、交易、预算、投资持仓、行情和财务报表功能。

## 本地启动

```powershell
cd web
npm install
npm run dev
```

开发服务器默认运行在 `http://127.0.0.1:5173`，并将 `/api` 代理到
`http://127.0.0.1:8010`。

注册和修改密码时，密码长度必须为 10–128 位，并且至少包含一个英文字母和一个数字。
前端会在提交前执行该规则，后端会对绕过前端的请求返回 `422` 业务校验错误。

财务总览以右上角选中的币种为统一口径。账户数量、账户列表、当前余额、现金流、
最近交易、预算和投资组合均只展示该币种的数据，不会对不同币种进行隐式换汇或相加。

## 验证

```powershell
npm run type-check
npm run lint
npm run test
npm run build
```
