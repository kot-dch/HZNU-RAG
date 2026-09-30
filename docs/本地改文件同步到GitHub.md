# 本地改文件 → 同步到 GitHub 完整流程

## 一、先理解三件事的区别

很多人混淆，先讲清概念，后面就不容易错：

| 位置 | 是什么 | 怎么变 |
| --- | --- | --- |
| **你的文件**（工作区） | 磁盘上 `campus-knowledge-rag\` 里的实际文件 | 你用编辑器改 |
| **本地仓库** | `.git` 目录里存的历史记录 | `git commit` 才会变 |
| **GitHub**（远程仓库） | 网上的那份 | `git push` 才会变 |

**关键**：改文件后 GitHub **完全不知道**。必须走完三步：

```
改文件  →  git add + git commit  →  git push
（工作区）    （存到本地仓库）        （推到 GitHub）
```

漏掉任何一步，GitHub 都不会变：

- 只改文件不 commit → GitHub 不变
- commit 了不 push → GitHub 还是不变
- push 了但没 commit → 没东西可推

---

## 二、日常更新流程（照抄这 5 条命令）

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag

# 1. 看改了什么（最重要的一步，永远别跳过）
git status
git diff

# 2. 存到本地仓库
git add -A
git commit -m "描述你改了什么"

# 3. 推到 GitHub
git push
```

### 每步在做什么

**`git status`** — 列出所有被改动/新增/删除的文件。红色是未暂存，绿色是已暂存。

**`git diff`** — 显示具体改了哪几行（`+` 是新增，`-` 是删除）。改错了能在这里发现。

**`git add -A`** — 把**所有**改动放进暂存区。
- 只想提交某个文件：`git add rag/store.py`
- 注意 `-A` 会把新文件、删除操作都包含进去

**`git commit -m "..."`** — 生成一条历史记录。`-m` 后面是说明，**要写清楚改了什么**，
因为这行字会永久留在仓库历史里（面试官也会看到）。

**`git push`** — 推到 GitHub。

### 成功长什么样

```
Enumerating objects: 5, done.
Counting objects: 100% (5/5), done.
Writing objects: 100% (3/3), 412 bytes | 412.00 KiB/s, done.
To https://github.com/kot-dch/HZNU-RAG.git
   2274aca..a1b2c3d  main -> main
```

**最后那行 `2274aca..a1b2c3d  main -> main` 是成功的标志。**

---

## 三、怎么验证真的同步上去了

**方法 1（最快）**：看 `git status` 的输出第一行

```
On branch main
Your branch is up to date with 'origin/main'.   ← 这行说明本地和远程一致
nothing to commit, working tree clean
```

**方法 2**：对比哈希

```powershell
git rev-parse HEAD          # 本地最新提交
git rev-parse origin/main   # 远程最新提交
```

两个哈希一样 = 已同步。

**方法 3（最直观）**：浏览器打开 <https://github.com/kot-dch/HZNU-RAG>，
看文件内容变了没有，或点 **Commits** 看提交记录。

---

## 四、只改了某个文件（更精确的做法）

```powershell
git status                      # 假设显示 modified: rag/config.py
git diff rag/config.py          # 确认改的内容
git add rag/config.py           # 只加这一个
git commit -m "调整检索阈值"
git push
```

---

## 五、⚠️ 最容易踩的坑：改错了目录

你桌面上有**两个目录**，只有其中一个是 git 仓库：

| 目录 | 是 git 仓库？ | 与 GitHub 的关系 |
| --- | --- | --- |
| `campus-secondhand` | ❌ 不是 | **改了永远不会同步** |
| `campus-knowledge-rag` | ✅ 是 | 就是它推到了 GitHub |

**如果你改的是 `campus-secondhand\rag\...`，怎么 commit 都没用** —— 那里没有 git 仓库。

### 怎么确认自己改对了

改完文件后执行：

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag
git status
```

- 看到 `modified: rag/xxx.py` → ✅ 改对了
- 看到 `nothing to commit, working tree clean` → ❌ 你改的是另一个目录（或没保存）

### 建议

**以后 RAG 的代码只改 `campus-knowledge-rag` 这一份**，把
`campus-secondhand\rag\` 当存档放着（或者删掉），避免混淆。

> 但 **`campus-secondhand` 里的 `miniprogram\` 和 `cloudfunctions\` 别删** ——
> 那是小程序代码，没有推到 GitHub（你说只要 RAG 一个仓库）。

---

## 六、改了代码后要重新跑索引吗

**要区分改的是什么：**

| 改动类型 | 要重新建索引吗 | 为什么 |
| --- | --- | --- |
| 改了 `data/docs/` 里的语料 | ✅ **必须** | 索引是语料生成的，语料变了索引就过时 |
| 改了切分参数（`config.py` 里的 `chunk_size` 等） | ✅ **必须** | 切分结果变了 |
| 改了 `embedder` 的向量化方式或维度 | ✅ **必须** | 向量变了 |
| 改了检索阈值、拒答闸门 | ❌ 不用 | 这些是检索时实时生效的 |
| 改了提示词（`generator.py`） | ❌ 不用 | 生成时才用 |
| 改了 `cli_*` 命令行脚本 | ❌ 不用 | 只是调用方式变了 |

重新建索引：

```powershell
python -m rag.cli_index
```

> **索引生成物（`rag/data/`）不入 Git 仓库**（被 `.gitignore` 排除），
> 所以别人克隆下来必须自己跑一次 `cli_index`。这也是为什么 README 里的
> 指标能保证"来自当前代码 + 当前语料"。

---

## 七、出错时的急救命令

### 改错了想撤销（还没 commit）

```powershell
git restore .                    # 撤销所有未提交的改动（慎用，改了会丢）
git restore rag/config.py        # 只撤销某个文件
```

### 已 commit 但还没 push，想撤销

```powershell
git reset --soft HEAD~1          # 撤销提交，但保留文件改动
# 改完再重新 commit
```

### 文件被误删了，想恢复

```powershell
git restore .                    # 从最后一次提交恢复所有文件
git restore README.md            # 只恢复某个文件
```

> 这招很管用：只要文件**曾经 commit 过**，就算从磁盘删掉了也能这样找回。
> 我实测过：不小心把 `README.md`、`NOTICE.md` 删掉并暂存删除，
> 一条 `git restore .` 就全回来了。

### push 被拒绝（远程有你本地没有的提交）

```powershell
git pull --rebase
git push
```

什么时候会遇到：你在 GitHub **网页上**直接改过文件（那样会产生远程提交）。

### 忘了加东西就想补进上一个提交

```powershell
git add 忘记的文件
git commit --amend --no-edit     # 合并进上一个提交，不改说明文字
```

⚠️ 如果上一个提交**已经 push 过了**，amend 会改哈希，需要 `git push --force-with-lease`。
**只在你一个人用的仓库里这么做**（多人协作时强推会覆盖别人的工作）。

---

## 八、查看历史

```powershell
git log --oneline                # 简版历史
git log --oneline -5             # 最近 5 条
git show HEAD                    # 看最后一次提交改了什么
git diff HEAD~1 HEAD             # 对比最近两次提交的差异
```

---

## 九、完整示例：把「拒答阈值从 0.11 调到 0.13」

假设你要改这个参数：

**1. 用编辑器打开**
```
C:\Users\Administrator\Desktop\campus-knowledge-rag\rag\config.py
```
找到 `score_threshold: float = 0.11`，改成 `0.13`，保存。

**2. 确认改对了**
```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag
git status
```
应该显示 `modified: rag/config.py`。

**3. 看具体改动**
```powershell
git diff rag/config.py
```
应该能看到 `-    score_threshold: float = 0.11` / `+    score_threshold: float = 0.13`。

**4. 验证效果**（改参数后一定要测）
```powershell
python -m rag.cli_eval
```
看 Recall@5 和拒答准确率变成多少了 —— 如果变差了，说明 0.13 不如 0.11。

**5. 提交推送**
```powershell
git add -A
git commit -m "调整拒答阈值 0.11 -> 0.13，拒答准确率 x% -> y%"
git push
```

**6. 验证**
浏览器打开仓库，点 Commits，看到新提交和说明。

---

## 十、commit 说明怎么写

这是**会永久留在仓库历史里的文字**，面试官会看。所以：

**❌ 差的写法**
```
update
修改
fix bug
```

**✅ 好的写法**（说清"改了什么 + 为什么"）
```
fix: 修正语料路径探测，支持独立仓库布局

原来写死为"上一级目录"，独立成仓库后找不到 data/docs。
改为按优先级探测多个候选路径，两种布局都能跑。
```

```
feat: 拒答闸门增加分档逻辑

覆盖率闸门一刀切会把 Recall@5 从 100% 压到 90%，
改为只作用于 score < 0.25 的低分带，三个指标同时达标。
```

**常用前缀**（可选，但显得专业）：
- `feat:` 新功能
- `fix:` 修 bug
- `docs:` 只改文档
- `refactor:` 重构，不改行为
- `chore:` 杂项（清理、配置）

---

## 十一、一张速查表

| 我想… | 命令 |
| --- | --- |
| 看改了什么 | `git status` / `git diff` |
| 提交所有改动并推送 | `git add -A` → `git commit -m "说明"` → `git push` |
| 只提交一个文件 | `git add 文件名` → `git commit -m "说明"` → `git push` |
| 确认是否已同步 | `git status`（看 "up to date"）或比对 `git rev-parse HEAD` 与 `origin/main` |
| 撤销未提交的改动 | `git restore .` |
| 找回被删的文件 | `git restore .` |
| 撤销已 commit 未 push | `git reset --soft HEAD~1` |
| 补东西进上一个提交 | `git add 文件` → `git commit --amend --no-edit` |
| 看历史 | `git log --oneline` |
| push 被拒 | `git pull --rebase` → `git push` |
