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
| 连不上 GitHub | 见下方「十二」 |

---

## 十二、⚠️ push 报「连不上 github.com」怎么办

### 症状

```
fatal: unable to access 'https://github.com/kot-dch/HZNU-RAG.git/':
Failed to connect to github.com port 443 after 21099 ms: Could not connect to server
```

### 原因

**git 不会自动使用系统代理，而浏览器和 PowerShell 会。**

这台机器上开着代理（Clash Verge，监听 `127.0.0.1:7890`）：

| 程序 | 是否走代理 | 能否连上 GitHub |
| --- | --- | --- |
| 浏览器 | ✅ 自动读系统代理设置 | 能 |
| PowerShell（`Invoke-WebRequest`） | ✅ 自动读系统代理设置 | 能 |
| **git** | ❌ **默认不走**，直连 443 端口 | **被墙，失败** |

所以会出现"浏览器能打开 GitHub，但 git push 失败"这种看起来很矛盾的现象。

### 解决：给 git 显式配置代理

先确认代理端口是通的：

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 7890 -WarningAction SilentlyContinue
# 看 TcpTestSucceeded 是不是 True
```

端口通了就配置：

```powershell
git config --global http.proxy  "http://127.0.0.1:7890"
git config --global https.proxy "http://127.0.0.1:7890"
```

然后重新 push：

```powershell
git push
```

> 端口号可能不是 7890。在 Clash Verge 的「设置 → 端口」里能看到实际值
> （常见还有 7897、10809）。

### ⚠️ 换个网络后要记得取消

**代理配置是全局的**，如果之后你去了没有 Clash 的网络（比如教室、图书馆、
或者关了代理），git 会因为连不上 `127.0.0.1:7890` 而**全部失败**，报错是：

```
Failed to connect to 127.0.0.1 port 7890: Connection refused
```

那时候要取消代理：

```powershell
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### 怎么判断当前该开还是该关

```powershell
# 看代理配置
git config --global http.proxy

# 看代理端口通不通
Test-NetConnection -ComputerName 127.0.0.1 -Port 7890 -WarningAction SilentlyContinue
```

| 代理端口状态 | 该怎么做 |
| --- | --- |
| 通（Clash 在跑） | 配置 git 代理 |
| 不通（Clash 没开） | 取消 git 代理 |

### 其他备选方案

1. **改用 SSH 协议**（不受 HTTP 代理影响，但需要生成 SSH 密钥并传到 GitHub）
2. **换个时段重试** —— GitHub 在国内的连通性是**间歇性**的。
   实测过：同一个 `git push` 两次都失败，过一会儿 `git ls-remote` 却成功了。
3. **手机热点** —— 有时候换个出口网络就好了

### 怎么确认是不是网络问题，而不是 git 用错了

```powershell
# 测试 git 能否读到远程（只读操作，不推送）
git ls-remote --heads https://github.com/kot-dch/HZNU-RAG.git
```

- **能列出 `refs/heads/main`** → 网络通，问题在别处
- **报连接失败** → 就是网络/代理问题

---

## 十三、一次完整实操记录（真实执行过）

下面是我在你这台机器上实际跑通的完整流程，可以对照着做。

### 起点：改一个文件

用编辑器打开 `README.md`，在「快速开始」下面加一段提示，保存。

### 第 1 步：看改了什么

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag
git status --short
```

输出：

```
 M README.md
?? docs/本地改文件同步到GitHub.md
```

- ` M`（空格+M）= 已修改但未暂存
- `??` = 新文件，git 还没追踪

### 第 2 步：确认改动内容

```powershell
git diff
```

输出（`+` 是新增的行）：

```
@@ -24,6 +24,10 @@
 ## 快速开始

+> **本地开发提示**：修改代码后同步到 GitHub 只需三步 ——
+> `git add -A` → `git commit -m "说明"` → `git push`。
+> 详细流程见 [`docs/本地改文件同步到GitHub.md`](...)。
+
 **不需要任何 API Key、不需要向量数据库、不需要下载模型权重。**
```

### 第 3 步：暂存并提交

```powershell
git add -A
git commit -m "docs: 补充本地开发与同步流程说明"
```

提交后 `git status` 会显示：

```
On branch main
Your branch is ahead of 'origin/main' by 1 commit.     ← 关键：领先远程 1 个提交
```

**这时候 GitHub 上还是旧的！** 本地新提交 `bb28c90`，远程还是 `2274aca`。

### 第 4 步：推送

```powershell
git push
```

第一次失败（网络问题，见第「十二」节），配好代理后重试：

```
To https://github.com/kot-dch/HZNU-RAG.git
   2274aca..bb28c90  main -> main          ← 这行是成功的标志
```

### 第 5 步：验证

```powershell
git status
# → Your branch is up to date with 'origin/main'.    ← 已同步

git rev-parse HEAD          # 本地
git rev-parse origin/main   # 远程
# 两个哈希相同 = 同步完成
```

再去浏览器看 <https://github.com/kot-dch/HZNU-RAG>，
点 **Commits** 能看到新提交和它的说明文字。

