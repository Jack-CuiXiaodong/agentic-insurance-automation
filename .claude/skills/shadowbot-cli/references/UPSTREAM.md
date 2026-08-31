# 上游来源

本目录下的参考文件来自影刀官方的 skills 仓库，**逐字复制，未作修改**（含各自的
YAML frontmatter——那是上游文件本来的样子；只有 `../SKILL.md` 会被 Claude Code
当成技能加载，这里的文件不会）。

- 仓库：<https://github.com/ying-dao/skills>
- 提交：`aaebb7c44cf105d1914207f8b53bf70e03b12e25`（2026-08-20，`Add ShadowBot CLI skill documentation`）

| 本地文件 | 上游路径 |
|---|---|
| `windows.md` | `shadowbot-cli/SKILL.md` |
| `posix.md` | `shadowbot-cli/mac/SKILL.md` |
| `cli-overview.zh-CN.md` | `shadowbot-cli/README.zh-CN.md` |

上游 `shadowbot-cli/信创/SKILL.md` 与 `shadowbot-cli/mac/SKILL.md` 内容完全一致
（`diff` 为空），所以这里只留一份 `posix.md`，Windows 之外都用它。

## 怎么更新

```bash
git clone --depth 1 https://github.com/ying-dao/skills /tmp/ying-dao-skills
diff /tmp/ying-dao-skills/shadowbot-cli/SKILL.md        .claude/skills/shadowbot-cli/references/windows.md
diff /tmp/ying-dao-skills/shadowbot-cli/mac/SKILL.md    .claude/skills/shadowbot-cli/references/posix.md
diff /tmp/ying-dao-skills/shadowbot-cli/README.zh-CN.md .claude/skills/shadowbot-cli/references/cli-overview.zh-CN.md
```

有差异就整份覆盖，然后把上面的提交号改掉。**不要**在副本里做局部修补——本仓库
自己的约定写在 `../SKILL.md` 里，那份才是我们维护的。
