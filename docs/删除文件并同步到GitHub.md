# 删除文件并同步到 GitHub

## 一、核心原理：删除也是"一次改动"

很多人以为删除文件是特殊的操作，其实**和改文件完全一样**：
git 只是记录"这个文件被删了"这个事实，然后你 commit + push 把这个事实同步上去。

```
删掉文件  →  git add -A  →  git commit  →  git push
（磁盘上没了）  （记录删除动作）  （存进本地仓库）  （GitHub 上才消失）
```

**关键认知**：文件从磁盘删掉后，**GitHub 上它还在**。必须走完 commit + push 才会消失。

---

## 二、标准流程（4 步）

### 步骤 1：删除文件

用任何你习惯的方式：

```powershell
# 方式 A：命令行删
Remove-Item C:\Users\Administrator\Desktop\campus-knowledge-rag\要删的文件.md

# 方式 B：直接在编辑器 / 资源管理器里删掉，效果一样
```

### 步骤 2：看 git 的反应

```powershell
cd C:\Users\Administrator\Desktop\campus-knowledge-rag
git status
```

你会看到：

```
On branch main

Changes not staged for commit:
	deleted:    docs/临时演示文件.md          ← git 已经知道文件没了
```

⚠️ **注意这句话**：`Changes not staged for commit` —— 删除动作**还没被记录**。
此时 GitHub 上文件还在。

### 步骤 3：提交删除

```powershell
git add -A
git status --short
```

现在显示：

```
D  docs/临时演示文件.md
```

`D` = 删除已暂存，等待提交。

```powershell
git commit -m "chore: 删除临时演示文件"
```

提交后 `git status` 显示：

```
Your branch is ahead of 'origin/main' by 1 commit.     ← GitHub 上文件还在！
```

### 步骤 4：推送

```powershell
git push
```

输出：

```
To https://github.com/kot-dch/HZNU-RAG.git
   3d11ea7..86812dd  main -> main                      ← 这时 GitHub 上才真正消失
```

---

## 三、更简洁的写法：用 `git rm` 一步搞定

如果你确定要删，可以用 `git rm`，它会**同时完成"磁盘删除"和"暂存删除"**：

```powershell
git rm 要删的文件.md          # 删文件 + 暂存删除
git commit -m "chore: 删除 xxx"
git push
```

相当于把步骤 1、2、3 合并了。

**和 `git add -A` 的区别**：

| 做法 | 磁盘文件 | 是否暂存删除 |
| --- | --- | --- |
| 手动删 + `git add -A` | 删掉 | 暂存 |
| `git rm 文件` | 删掉 | 暂存 |

两种结果一样，看个人习惯。我一般用「手动删 + `git add -A`」，
因为删文件常常是在编辑器里顺手删的。

---

## 四、删错了怎么恢复

### 情况 A：刚删掉，还没 commit

```powershell
git restore 被删的文件.md           # 恢复单个文件
git restore .                      # 恢复所有被删/被改的文件
```

这是**最常用的一招**。我实测过：不小心把 `README.md` 和 `NOTICE.md`
删掉并暂存了删除，一条 `git restore .` 全部回来了，一个字节都没丢。

### 情况 B：已经 commit 但还没 push

```powershell
git reset --soft HEAD~1            # 撤销这次提交（文件仍是删除状态）
git restore .                      # 再恢复文件
```

### 情况 C：已经 push 了

文件在历史里还在，可以取回来：

```powershell
# 从上一个提交里恢复某个文件
git checkout HEAD~1 -- 被删的文件.md
git commit -m "revert: 恢复误删的文件"
git push
```

**为什么能恢复**：git 保留完整历史。删除只是新增了一条"删除记录"，
之前的内容一直都在。这也是为什么**删除文件不要怕，只要 push 前发现就能救**。

---

## 五、⚠️ 三个容易踩的坑

### 坑 1：只删了磁盘，忘了 commit

```powershell
Remove-Item 文件.md
# 然后就去干别的了 —— GitHub 上文件还在，别人克隆下来还能看到
```

**怎么发现**：`git status` 显示 `deleted:` 但你没提交。

### 坑 2：删了不该删的，直接 push 了

例如误删 `rag/store.py`（核心代码），push 上去后别人克隆就跑不起来。

**怎么避免**：**push 前一定看 `git status` 和 `git diff --stat`**：

```powershell
git add -A
git diff --cached --stat        # ← push 前看一眼改动清单
```

输出形如：

```
 docs/临时演示文件.md | 3 ---
 1 file changed, 3 deletions(-)
```

看到删除的文件名不对，立刻：

```powershell
git reset                      # 取消暂存
git restore .                  # 恢复文件
```

### 坑 3：以为删了文件就"删干净了"

**GitHub 上仍然能在提交历史里看到这个文件的内容**，包括任何曾经提交过的密钥、
密码。所以：

- 密钥不小心提交过一次 → **立刻去平台作废那个密钥**，光删文件没用
- 想让敏感文件永不进入仓库 → 提前写进 `.gitignore`，而不是提交后再删

如果确实需要从历史里彻底清除，要用 `git filter-repo` 重写历史，
这属于高难度操作，且会改变所有提交哈希，**多人协作时非常危险**。

---

## 六、只删某个文件 vs 删除整个目录

### 删除单个文件

```powershell
Remove-Item 文件.md
git add -A
git commit -m "chore: 删除 xxx"
git push
```

### 删除整个目录

```powershell
Remove-Item 目录名 -Recurse -Force
git add -A
git commit -m "chore: 删除 xxx 目录"
git push
```

git 会记录目录下**每一个文件**的删除。`git status --short` 会列出一长串 `D`。

---

## 七、一次真实操作记录

下面是我实际跑通的一次演示，可以对照。

### 起点：仓库干净

```
$ git status --short
（无输出，干净）
```

### 第 1 步：创建并提交一个文件（作为删除的起点）

```powershell
# 创建 docs/临时演示文件.md
git add -A
git commit -m "chore: 创建临时演示文件"
git push
```

```
To https://github.com/kot-dch/HZNU-RAG.git
   8776d3c..3d11ea7  main -> main
```

此时文件存在于**磁盘 + 本地仓库 + GitHub** 三处。

### 第 2 步：删除文件

```powershell
Remove-Item docs\临时演示文件.md
git status
```

```
Changes not staged for commit:
	deleted:    docs/临时演示文件.md
```

**GitHub 上文件还在。**

### 第 3 步：提交删除

```powershell
git add -A
git status --short
```

```
D  docs/临时演示文件.md
```

```powershell
git commit -m "chore: 删除临时演示文件"
git status
```

```
Your branch is ahead of 'origin/main' by 1 commit.     ← 还是在
```

**GitHub 上文件依然在。**

### 第 4 步：推送

```powershell
git push
```

```
To https://github.com/kot-dch/HZNU-RAG.git
   3d11ea7..86812dd  main -> main
```

### 第 5 步：验证

```powershell
# 本地确认
Test-Path docs\临时演示文件.md          # → False

# 远程确认（用 GitHub API）
# GET /repos/kot-dch/HZNU-RAG/contents/docs/临时演示文件.md
# → HTTP 404，说明远程也没了
```

---

## 八、如果是删除后想撤销那个"删除提交"

上面演示完，历史里留下了两条没意义的提交
（`创建临时演示文件` + `删除临时演示文件`）。清理方法：

```powershell
git reset --hard <删除操作之前的那个提交哈希>
git push --force-with-lease origin main
```

**效果**：两条演示提交从历史里消失，就像从没发生过。

⚠️ **`--force-with-lease` 的使用前提**：

- 只有你一个人在用这个仓库（多人协作时强推会覆盖别人的提交）
- `--hard` 会丢弃工作区改动，**确认没有未提交的重要改动再用**

---

## 九、速查表

| 我想… | 命令 |
| --- | --- |
| 删文件并同步到 GitHub | `Remove-Item 文件` → `git add -A` → `git commit -m "说明"` → `git push` |
| 一步删掉并暂存 | `git rm 文件` → `git commit -m "说明"` → `git push` |
| 删整个目录 | `Remove-Item 目录 -Recurse` → `git add -A` → `git commit` → `git push` |
| 删错了（未 commit） | `git restore 文件` 或 `git restore .` |
| 删错了（已 commit 未 push） | `git reset --soft HEAD~1` → `git restore .` |
| 删错了（已 push） | `git checkout HEAD~1 -- 文件` → `git commit` → `git push` |
| 看某次改动删了哪些文件 | `git diff --cached --stat`（提交前）或 `git show --stat HEAD`（提交后） |
| 撤销最近一次删除提交 | `git reset --hard HEAD~1`（谨慎，会丢工作区改动） |
