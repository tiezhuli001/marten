# Private Agent Suite Example

这个示例展示一个独立私有项目如何复用 `Marten`：

- 继续使用官方内置 `main-agent`、`ralph`、`code-review-agent`
- 为私有编码入口绑定独立 endpoint
- 在私有项目层声明私有知识域 `private-sop`
- 不直接 import `app/control/*` 等 internal-only 细节

最小验证关注的是配置装配和能力复用，不是把私有业务逻辑重新塞回框架仓库。
