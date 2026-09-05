# jellyfin-plugin-hub

把多个 Jellyfin 插件仓库清单合并成一个地址。Jellyfin 控制台里只需要添加这一个存储库；以后增删插件、源地址失效或更换时，只改本仓库里的 `sources.json` 并重新同步即可。

做法参考 [LxnChan/jellyfin-plugin-mirror](https://github.com/LxnChan/jellyfin-plugin-mirror)：对外只暴露一份 `manifest.json`。区别是本项目只聚合你自己要用的插件清单，不镜像官方全量仓库，也不重新托管插件 zip。安装时仍从各插件原始 `sourceUrl` 下载。

## 在 Jellyfin 中使用

把本仓库推送到 GitHub 或 GitLab 后，在 Jellyfin：

**控制台 -> 插件 -> 存储库 -> 添加**

填写（把 `OWNER` 换成你的用户名或组织名）：

```text
https://raw.githubusercontent.com/OWNER/jellyfin-plugin-hub/main/dist/manifest.json
```

jsDelivr 备用地址：

```text
https://cdn.jsdelivr.net/gh/OWNER/jellyfin-plugin-hub@main/dist/manifest.json
```

GitLab 地址：

```text
https://gitlab.com/OWNER/jellyfin-plugin-hub/-/raw/main/dist/manifest.json
```

添加成功后，到 **插件 -> 目录** 即可看到本仓库收录的插件并安装。原来那些逐个添加的存储库可以删掉。

如果暂时不推远程，也可以把 `dist/manifest.json` 放到任意 Jellyfin 能访问的 HTTP 服务上，存储库地址填该文件的 URL。

## 当前收录

| 来源 | 清单地址 | 说明 |
| --- | --- | --- |
| MetaTube | `https://cdn.jsdelivr.net/gh/metatube-community/jellyfin-plugin-metatube@dist/manifest.json` | 优先使用 |
| MetaTube | `https://raw.githubusercontent.com/metatube-community/jellyfin-plugin-metatube/dist/manifest.json` | 上一地址失败时回退 |
| MeiamSubtitles | `https://github.com/91270/MeiamSubtitles.Release/raw/main/Plugin/manifest-stable.json` | 含 Shooter / Thunder / Assrt |

同步后当前会生成 4 个插件条目：MetaTube、Jellyfin.MeiamSub.Shooter、Jellyfin.MeiamSub.Thunder、Jellyfin.MeiamSub.Assrt。

## 添加或更换插件源

编辑 `sources.json`。同一插件的多个清单地址写在同一个 `urls` 数组里，按顺序尝试，成功即停，避免重复条目。

```json
{
  "sources": [
    {
      "name": "MetaTube",
      "urls": [
        "https://cdn.jsdelivr.net/gh/metatube-community/jellyfin-plugin-metatube@dist/manifest.json",
        "https://raw.githubusercontent.com/metatube-community/jellyfin-plugin-metatube/dist/manifest.json"
      ]
    },
    {
      "name": "MeiamSubtitles",
      "urls": [
        "https://github.com/91270/MeiamSubtitles.Release/raw/main/Plugin/manifest-stable.json"
      ]
    }
  ]
}
```

可选字段：

- `include`：只保留列出的插件 GUID
- `exclude`：排除列出的插件 GUID

例如只要 MeiamSubtitles 里的 Thunder 和 Assrt：

```json
{
  "name": "MeiamSubtitles",
  "urls": [
    "https://github.com/91270/MeiamSubtitles.Release/raw/main/Plugin/manifest-stable.json"
  ],
  "exclude": [
    "038d37a2-7a1e-4c01-9b6d-aa215d29ab4c"
  ]
}
```

同一 GUID 出现在多个源时，保留先写入 `sources.json` 的那一份。

改完后在项目目录执行：

```bash
python3 sync.py
```

会更新：

- `dist/manifest.json`：给 Jellyfin 用的合并清单
- `dist/status.json`：本次同步用了哪条 URL、各源插件数量

默认任一源全部失败则不覆盖已有清单。若希望其余源成功时仍写出结果：

```bash
python3 sync.py --allow-partial
```

## 自动同步

GitHub Actions 会在每周一 UTC 01:00 拉取各源并提交更新后的 `dist/`。也可在 Actions 页面手动触发。

GitLab CI 会在默认分支、定时流水线或手动流水线中运行测试并生成 `dist/` 产物。若要在 GitLab 上回写提交，需要自行配置可写仓库的 token。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

仅依赖 Python 3.7+ 标准库。

## 版权

仓库内清单所指向的插件版权归各自作者所有。本项目只做清单聚合，不修改插件内容。
