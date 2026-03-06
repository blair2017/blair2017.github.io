# WeChat Export (公众号可复制 HTML)

这个目录提供一个最小的“自动导出”脚本，把仓库里的 Markdown 文章批量转换为更适合粘贴到微信公众号后台的 HTML（尽量用内联样式）。

## 自动化流程（GitHub Actions）

仓库已配套一个 GitHub Actions 工作流：`.github/workflows/wechat-sync.yml`。它会在你 push 到 `master` 时自动：

1. 在 CI 里冒烟构建一次 Jekyll（避免站点因为语法/依赖问题构建失败）
2. 更新（或首次创建）`wechat-style` 分支
3. 运行导出脚本生成 `wechat_exports/`（可直接打开复制粘贴到公众号后台）
4. 可选：调用 webhook 通知你自己的“微信验证与发布服务”

下面这张 Mermaid 流程图对应当前仓库的实际分支与自动化：

```mermaid
graph TD
    A[本地编写 Markdown] -->|git push| B(GitHub: master 分支)
    B -->|触发 GitHub Actions| C{CI: wechat-sync}

    subgraph "CI 自动化处理"
    C -->|1. Jekyll build 冒烟| D[构建原始站点 (master)]
    C -->|2. checkout / create| E[切换/创建 wechat-style 分支]
    E -->|3. merge| F[合并 master -> wechat-style]
    F -->|4. 运行脚本| G[Markdown -> 公众号 HTML\n输出 wechat_exports/]
    G -->|5. commit + push| H(GitHub: wechat-style 分支)
    end

    H -->|可选: webhook| I[你的“微信验证与发布”服务]
    I -->|调用微信 API| J[微信公众平台]

    style A fill:#f9f,stroke:#333
    style J fill:#07c160,stroke:#333,color:#fff
```

## 本地运行

```bash
python3 -m pip install -r tools/wechat/requirements.txt
python3 tools/wechat/sync_wechat.py --out wechat_exports
```

输出目录默认是 `wechat_exports/`，其中：

- `wechat_exports/index.html`：导出列表页
- `wechat_exports/*.html`：每篇文章一份文件（可直接打开复制）

## 说明

- 脚本会把文章里的 `layout: post` 自动改成 `layout: post-wechat`（仅限本来就是 post 类型的文章）。
- 图片/链接会把以 `/` 开头的 URL 自动补全成绝对地址（默认读取 `_config.yml` 里的 `url:`）。

## 可选配置

- `WECHAT_PUBLISH_WEBHOOK_URL`（GitHub Actions Secret）：如果你有一个自己的发布服务（用来二次校验导出的 HTML、或进一步调用微信 API 创建草稿/群发），可以把 webhook URL 配置为这个 Secret；未配置则不会调用。
