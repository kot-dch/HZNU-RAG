# 把 RAG 项目推上 GitHub · 具体操作步骤

仓库位置：`C:\Users\Administrator\Desktop\campus-knowledge-rag`
已准备好：56 个文件 / 317 KB（源码 + 测试 + 评测集 + 30 份语料 + 文档）

---

## ⚠️ 推之前：一个隐私坑必须先避开

Git 会把 **user.email 写进每一次提交记录**，而 GitHub 上任何人都能看到。
如果你用真实邮箱（比如 QQ 邮箱、163），等于公开了。

**正确做法**：用 GitHub 提供的**匿名邮箱**。格式是：

```
<你的GitHub用户名>@users.noreply.github.com
```

例如用户名是 `duanchuanhao`，就用 `duanchuanhao@users.noreply.github.com`。
这个邮箱收得到通知，但不会暴露真实地址。

> 也可以在 GitHub 网页里勾选「Keep my email addresses private」，
> 它会直接告诉你该用哪个 noreply 地址。

---

## 第 1 步：配置 git 身份（一次性，之后不用再设）

把下面两行的值换成**你自己的**：

```powershell
git config --global user.name "duanchuanhao"
git config --global user.email "duanchuanhao@users.noreply.github.com"
```

验证：

```powershell
git config --global user.name
git config --global user.email
```

**建议同时设置默认分支名为 main**（GitHub 的默认，避免推送后还要改名）：

```powershell
git config --global init.defaultBranch main
```

---

## 第 2 步：初始化本地仓库并提交

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag

git init
git add -A
git status
```

**`git status` 这一步别跳过**，它列出即将提交的文件。确认：

- ✅ 应该出现：`rag/` `tests/` `data/docs/` `README.md` `.gitignore` `LICENSE` `NOTICE.md`
- ❌ **不应出现**：`rag/data/`（索引生成物）、`__pycache__`、任何 `.env`

确认无误后提交：

```powershell
git commit -m "feat: 校园知识问答助手（RAG）初始版本

- 完整 RAG 链路：清洗 → 条款切分 → 向量化 → 检索 → 带引用生成
- 支持 API 与本地离线双向量化链路，无 Key 可完整体验
- 两道拒答闸门：相似度阈值（分布标定）+ 分档覆盖率
- 42 题评测集：Recall@5 100% / MRR 0.950 / 拒答准确率 91.7%
- 37 项自动化测试，含 2 个历史 bug 回归用例"
```

---

## 第 3 步：在 GitHub 上创建空仓库

1. 打开 <https://github.com/new>
2. 填写：
   - **Repository name**：`campus-knowledge-rag`（要和本地文件夹同名，好认）
   - **Description**：`基于 RAG 的校园文档问答服务 | Recall@5 100%`
   - **Public**（公开）← 简历要用，必须公开
   - ⚠️ **不要勾选**下面的三个初始化选项：
     - ❌ Add a README file
     - ❌ Add .gitignore
     - ❌ Choose a license
   
   **为什么都不勾**：本地已经有这些文件了。如果 GitHub 上也生成一份，
   推送时会发生历史冲突，还得先 `git pull --rebase` 才能推，容易出错。
3. 点 **Create repository**

创建后会看到一个"快速设置"页面，里面有仓库地址，形如：

```
https://github.com/你的用户名/campus-knowledge-rag.git
```

---

## 第 4 步：关联远程仓库并推送

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag

git remote add origin https://github.com/你的用户名/campus-knowledge-rag.git
git branch -M main
git push -u origin main
```

### 第一次推送会要求登录

GitHub 从 2021 年起**不再接受账号密码**，必须用 **Personal Access Token**（PAT）
或 SSH Key。推荐 PAT，步骤：

1. 打开 <https://github.com/settings/tokens>
2. 选 **Generate new token** → **Generate new token (classic)**
3. 填写：
   - **Note**：`push campus-knowledge-rag`（随便写，方便以后认）
   - **Expiration**：建议 90 天（不要选 No expiration）
   - **Scopes**：勾选 **`repo`**（整个 repo 大项）
4. 点 **Generate token** → **立刻复制**那串 `ghp_xxxx`

   > ⚠️ 这串只在生成时显示一次，关掉页面就再也看不到，只能重新生成。

5. 回到 PowerShell，`git push` 会弹窗让你输入：
   - **Username**：你的 GitHub 用户名
   - **Password**：**粘贴刚才的 token**（不是你的登录密码）

> PowerShell 里粘贴用**鼠标右键**，不是 Ctrl+V。

---

## 第 5 步：验证

推送成功后打开：

```
https://github.com/你的用户名/campus-knowledge-rag
```

**重点检查这几件事**：

- [ ] README 正常渲染，指标表格显示出来了（不是一堆纯文本）
- [ ] 仓库里**没有** `rag/data/` 目录
- [ ] 没有 `__pycache__`
- [ ] 你的邮箱显示为 `xxx@users.noreply.github.com`（点某次 commit 能看到）
- [ ] 别人点开能不能看懂 → 把自己当面试官，从头翻一遍 README

---

## 第 6 步：验证"克隆下来能跑"（最关键的一步）

这一步必做。**很多人的仓库点进去很漂亮，但克隆下来跑不起来**——
README 里的命令和实际代码对不上。找一个空目录实测：

```powershell
cd C:\Users\Administrator\Desktop
mkdir _clonetest
cd _clonetest
git clone https://github.com/你的用户名/campus-knowledge-rag.git
cd campus-knowledge-rag
python -m pip install -r requirements.txt
python -m rag.cli_index
python -m rag.cli_ask "转专业需要什么条件"
python -m rag.cli_eval
```

应该看到和本地一致的结果：`151 个片段`、`Recall@5 100.0%`。

跑通后删掉测试目录：

```powershell
cd C:\Users\Administrator\Desktop
Remove-Item _clonetest -Recurse -Force
```

> 这一步我已经在本地验证过了（两种目录布局都能跑），但你自己在**全新克隆**
> 的场景下再验一次更保险。

---

## 之后的日常操作

改完代码想更新到 GitHub：

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag
git add -A
git commit -m "描述你改了什么"
git push
```

---

## 常见问题

| 报错 | 原因与解决 |
| --- | --- |
| `fatal: not a git repository` | 没在仓库目录里。先 `cd` 到 `campus-knowledge-rag` |
| `Author identity unknown` | 第 1 步的 user.name / user.email 没设 |
| `remote origin already exists` | 之前加过。`git remote set-url origin <新地址>` 覆盖 |
| `Authentication failed` | 密码栏填错——必须填 **token**，不是登录密码 |
| `Updates were rejected` | GitHub 上建仓库时勾了 README/LICENSE。执行 `git pull --rebase origin main` 再 push |
| `src refspec main does not match any` | 还没 commit。先 `git add -A && git commit` |
| 中文文件名在 GitHub 上显示乱码 | 正常现象，Git 默认不转义中文路径，不影响使用 |
| 推上去发现推错了文件 | `git rm --cached <文件>` 然后重新 commit（加到 `.gitignore` 后不会再被追踪） |
| 不小心把 Key 推上去了 | **立即去平台作废那个 Key**，然后从历史里清除（`git filter-repo`）。光删文件没用，历史里还在 |

---

## 关于仓库设置的建议（可选但推荐）

推上去之后，在仓库页面可以补几个设置，让面试官观感更好：

1. **About 区**（右上角齿轮）：
   - Description：`基于 RAG 的校园文档问答服务 | Recall@5 100% / MRR 0.950`
   - Topics：`rag` `llm` `prompt-engineering` `vector-search` `fastapi` `python`
2. **Releases**：打个 `v1.0.0` 标签，显得有版本管理意识
3. 如果后续加了截图或演示动图，放在 README 顶部——**面试官停留时间很短，
   一张架构图或终端截图比一千字有效**

---

## 现在需要你提供两个信息

我帮不了的部分：**你的 GitHub 用户名**和**你想用的邮箱**。

告诉我这两个，我可以：
1. 直接帮你把 `git config` 设好
2. 执行 `git init` + `git add` + `git commit`
3. 把 `git remote add origin` 的具体命令写好给你（remote 地址需要你的用户名）

推送那一步（第 4 步）**必须你自己做**——需要输入 token，
我不应该也不可能接触你的凭据。
