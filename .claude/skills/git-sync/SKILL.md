---
name: git-sync
description: VoiceScribe WebUI git 管理 — 提交、推送、查看状态和历史
---

# Git Sync

管理 VoiceScribe WebUI 项目的 git 仓库，自动或手动同步代码变更到 GitHub。

## 自动同步

每次对话结束后，Stop hook 会自动执行 `scripts/git-sync.sh`：
- `git add -A`
- 有变更时自动 commit（消息包含变更文件列表）
- `git push` 到 origin

无需手动操作。如果 push 失败（网络问题），commit 仍在本地，下次 push 会一起推送。

## 手动命令

需要手动 git 操作时直接运行对应命令：

```bash
cd "/Users/silver/Documents/computer science/voicescribe-webui"

# 查看当前状态
git status

# 查看提交历史
git log --oneline -10

# 查看最近变更
git diff HEAD~1

# 手动同步（和自动脚本一样）
scripts/git-sync.sh

# 回退最近一次提交（保留文件变更）
git reset --soft HEAD~1

# 放弃所有本地变更
git checkout .
```

## 远程仓库

- Remote: `origin` → `https://github.com/S1lverYin/Podcast-demo.git`
- Branch: `main`
