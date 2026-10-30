# Axiom-manager

把任务完成后 Git 提交、中文 Commit、语义化版本、README 更新及文件命名与存放规则安装到项目的 `AGENTS.md`，并提供可独立运行的校验脚本。

安装后，读取 `AGENTS.md` 的编码助手按“完成修改 → 核对文件规则 → 同步相关文档并复核 → 验证 → 中文 Commit → 本地提交”的顺序工作。每次任务更新及 README 修改后，先核对 AGENTS.md 的命名与存放说明，确保每个文件有符合要求的位置、名称和用途出处。默认只提交本地；推送可配置。任务提交和版本发布分别执行，日常提交不自动增加版本号。

需要 **Python 3.11+**；提交、发布和推送还需要 Git。使用 Python 标准库，无第三方 Python 依赖。Windows 使用 `python`，Linux/macOS 可改为 `python3`。

## 安装到项目

在目标项目中，让编码助手执行：

```text
把 Axiom-manager 安装到当前项目，来源：E:/zl/01-Project/axiom-manager。先阅读该工具仓库的 AGENTS.md，再按说明安装并配置适合本项目的验证命令。
```

来源可以替换为本工具的实际本地路径或已发布的 Git 仓库地址。助手取得来源后，在本机执行安装器；不需要运行远程下载的 shell 命令。

手动安装（以下以 Windows 路径为例）：

```powershell
# 预览：不写入任何文件
python E:/zl/01-Project/axiom-manager/scripts/install_rules.py E:/work/my-project

# 实际安装
python E:/zl/01-Project/axiom-manager/scripts/install_rules.py E:/work/my-project --write

# 再运行：应显示 unchanged
python E:/zl/01-Project/axiom-manager/scripts/install_rules.py E:/work/my-project --write
```

目标目录应已存在。安装不要求 Git 已初始化；实际提交和发布要求项目是 Git 仓库根目录。

| 目标文件 | 行为 |
|---|---|
| `AGENTS.md` | 更新独立工具规则块；缺少文件规则时按项目现状生成初稿，升级时保留项目专属文件规则及其他原文 |
| `.axiom-manager/manage.py` | 安装独立运行脚本；更新时保护本地修改 |
| `.axiom-manager/config.json` | 首次生成配置；重新安装保留用户设置 |
| `.axiom-manager/install-state.json` | 记录安装版本、文件来源和哈希，用于更新与卸载 |
| `.axiom-manager/backups/` | 有旧文件发生变化时，先保存原始字节；备份不应提交 Git |

建议把 `.axiom-manager/backups/` 加入目标项目 `.gitignore`，其余规则、脚本、配置和安装记录可随项目提交。规则模板只有一份：[assets/agents-block.md](assets/agents-block.md)。安装器不会覆盖目标项目的 README、CHANGELOG 或现有版本文件。

初次安装后，助手需阅读目标项目已有的命名和位置说明，结合实际文件用途核对自动生成的初稿；已有文字约定保持有效。安装器不会自动重命名、搬动项目文件，也不会在升级时用新模板重置项目专属文件规则。

## 配置验证和推送

修改目标项目 `.axiom-manager/config.json`。例如 Python 项目：

```json
{
  "schema": 1,
  "auto_push": false,
  "remote": "origin",
  "branch": null,
  "checks": [
    ["{python}", "-m", "unittest", "discover", "-s", "tests", "-v"]
  ],
  "check_timeout_seconds": 300,
  "version_file": null,
  "sync_version_files": []
}
```

| 字段 | 说明 |
|---|---|
| `checks` / `check_timeout_seconds` | 逐条运行命令参数数组，每条超时秒数；`{python}` 替换为当前解释器，不通过 shell 执行 |
| `auto_push` | 默认 `false`；显式设为 `true` 表示以后提交和发布后自动推送 |
| `remote` / `branch` | 远端名称和目标分支；默认 `origin`，分支为 `null` 时使用当前分支名 |
| `version_file` / `sync_version_files` | 权威版本文件及需要同步的其他版本文件，路径相对项目根目录 |
| `schema` | 配置结构版本，当前为 `1`；未知字段会报错，避免配置拼写错误静默失效 |

新安装的 `checks` 为空，助手应根据项目配置真实验证命令。确无适用自动检查时，可以传 `--no-checks-reason "纯文档修改，已人工核对命令和链接"`；已有检查失败时仍会停止。

Node 项目可以运行平台实际可执行的程序，例如 Windows 的 `npm.cmd` 或 `pnpm.cmd`，Linux/macOS 的 `npm` 或 `pnpm`。shell 管道、重定向和脚本字符串不会自动解释；需要复杂操作时调用项目自己的脚本。

## 文件命名、位置与特殊任务

项目的文件规则保存在 **AGENTS.md 本身**，说明文件可放在哪里、如何命名、用途是什么。不要另外创建 `agent.md` 或大小写不同的副本。

每次更新完成及 README 修改后，执行以下步骤：

1. 先阅读 AGENTS.md 中的现有说明，检查是否同时包含命名和存放要求；缺少时根据实际文件建立，保留已有合理约定。
2. 逐项检查当前文件，包括新文件和未提交文件。没有规则出处、命名不符或多条规则重叠时，先处理再提交。
3. 合理的新类别补充具体位置、命名示例和用途；文件确实错放或命名不规范时，修正文件及引用，不用宽泛规则掩盖问题。
4. 有特殊任务时，按任务约定专门位置和命名规则。例如界面验收截图、实验结果或交付包，应采用该项目实际需要的位置；不凭空建空目录。
5. 同步 README 和相关说明，再次检查所有文件的命名和出处，通过后与修改内容一并提交。

```powershell
# 查看每个文件对应的 AGENTS.md 规则
python .axiom-manager/manage.py layout --verbose

# 旧项目尚无可检查的规则时，先按当前项目生成初稿
python .axiom-manager/manage.py layout --init
python .axiom-manager/manage.py layout --init --write
```

`--init` 默认预览，`--write` 才写入 AGENTS.md 并在修改前备份。已有可检查规则时初始化显示 `unchanged`，不会借重新初始化为新文件自动放行；应按检查结果修订具体规则。初稿按现有目录分组、逐个登记已有文件的名称；用途来自当前结构，仍需助手阅读内容后细化，不能将初稿视为对命名合理性的自动认定。

文件规则使用独立标记块中的 JSON，核心字段如下：

| 字段 | 说明 |
|---|---|
| `id` / `paths` | 唯一规则标识和相对项目根目录的路径模式；`*` 不跨目录，`**` 可跨多层 |
| `name_pattern` / `naming` | 匹配文件名的完整正则及可读的中文命名说明 |
| `purpose` | 文件职责和存放依据；检查结果会显示文件对应的规则 id |
| `task` | 特殊任务名称，与专门路径和命名规则一起使用 |
| `excluded` | 生成目录或文件的具体路径及 `reason`；例如缓存、依赖和安装备份 |

例如，项目确有界面验收截图任务时，可以在 `rules` 中增加：

```json
{
  "id": "ui-evidence",
  "paths": ["tests/evidence/ui/*.png"],
  "name_pattern": "[a-z0-9]+(?:_[a-z0-9]+)*_step_[0-9]{2}\\.png",
  "naming": "功能名_step_两位步骤号.png，例如 login_step_01.png",
  "purpose": "界面验收步骤对应的截图原件",
  "task": "界面验收截图"
}
```

该例只供有此任务的项目采用。普通规则与特殊任务规则应划清路径，保证同一文件只匹配一条规则。不能用 `*`、`**/*` 等整个项目兜底路径，也不能无理由排除未归类文件。

检查范围包括项目内当前文件，不会仅因 `.gitignore` 忽略就跳过。Git 内部数据库不属于项目文件；依赖、缓存和安装备份按规则中明确的路径及原因排除。目录链接本身需要归属，检查不会跟随链接读取项目外文件。命令在项目验证前后各复核一次；验证命令产生的新文件也必须有规则出处。

脚本检查路径、命名、必填用途和唯一归属；“用途是否准确、特殊任务位置是否合理”由助手结合实际项目判断。只读来源原件和用户已有修改仍按原有权限保留，不因整理规则擅自删除或搬动。

## 检查与提交

在目标项目根目录运行：

```powershell
python .axiom-manager/manage.py status
python .axiom-manager/manage.py layout --verbose
python .axiom-manager/manage.py check

# 预览本次提交；逐个列出文件
python .axiom-manager/manage.py commit -m "feat(export): 支持导出项目摘要" --files src/export.py tests/test_export.py README.md CHANGELOG.md

# 验证通过后实际提交
python .axiom-manager/manage.py commit -m "feat(export): 支持导出项目摘要" --files src/export.py tests/test_export.py README.md CHANGELOG.md --write
```

从其他目录调用时，将 `--project 目标项目根目录` 放在子命令前面。路径有空格时加引号；重命名同时列出旧文件和新文件。所选文件没有实际改动时跳过，目录参数会被拒绝，避免把无关修改一起提交。

已有暂存内容、未解决冲突、游离 HEAD、未完成的合并或缺少 Git 身份时，先处理并保留原内容。开始任务时应识别用户已有改动；同一文件中的混合改动仍需助手判断和分离，脚本不能自动辨别是谁写的。

中文 Commit 格式：

```text
feat(git): 支持任务完成后自动提交
fix(install): 修复重复安装导致规则重复的问题
docs(readme): 补充 Windows 卸载命令
```

支持 `feat/fix/docs/refactor/perf/test/build/ci/chore/style/revert`。范围可选；类型和标点使用兼容工具的英文格式，说明以中文为主。标题不超过 72 个 Unicode 字符，中文说明建议 30 字以内。复杂修改在空行后的正文解释原因和影响。

不兼容修改必须有 `!` 及迁移说明，保存为 UTF-8 文件后使用 `--message-file`：

```text
feat(config)!: 将 push 配置字段改为 auto_push

BREAKING CHANGE: 旧配置中的 push 字段需改为 auto_push，取值保持不变
```

可单独运行 `python .axiom-manager/manage.py lint-message --message-file commit-message.txt`。不要把临时提交说明文件混入产品提交。

## 版本发布

| 累计用户变化 | 稳定版本升级示例 |
|---|---|
| 不兼容修改 | `1.4.2 → 2.0.0` |
| 兼容新功能 | `1.4.2 → 1.5.0` |
| 兼容修复或性能改进 | `1.4.2 → 1.4.3` |

一次发布按最高影响升级一次。`0.x` 阶段的不兼容修改升级次版本。`perf → patch` 是本工具的约定；纯文档、测试和内部整理默认不触发版本发布。需要发版时才运行发布命令。

未配置版本来源时，检查根目录 `package.json`、`pyproject.toml` 和 `VERSION`。多个来源必须一致；没有来源时，首次发布创建 `VERSION`，默认 `0.1.0`。支持 `project.version` 和 `tool.poetry.version` 的静态 TOML 版本；动态版本和其他格式需要使用显式静态版本文件或项目自己的发布工具。独立产品的多包工作区不应自动统一版本。

配置 `version_file` 后只维护该文件及 `sync_version_files`。存在同目录 `package-lock.json` 或 `npm-shrinkwrap.json` 时，同步项目根版本和 `packages[""]`，保留依赖版本。pnpm、Yarn、Poetry 的锁文件没有对应的项目根版本字段，本工具不改写它们。

发布前先提交所有已完成的改动，确保工作区干净，检查 README 和待发布说明：

```powershell
# 预览：按上次可达的最高语义化版本标签之后的提交判断升级级别
python .axiom-manager/manage.py release

# 同步版本和 CHANGELOG，验证后提交，再创建本地附注标签
python .axiom-manager/manage.py release --write

# 明确发布版本：预发布或进入稳定版本
python .axiom-manager/manage.py release --version 0.2.0-beta.1 --write
python .axiom-manager/manage.py release --version 1.0.0 --write
```

首次发布沿用当前版本。`--version` 不能低于文件版本，且必须高于已有发布标签；`+构建元数据` 不增加版本优先级。预发布的下一版使用显式 `--version`。`--bump patch/minor/major` 可明确选择升级级别，与 `--version` 互斥。

标签统一为 `v版本`，例如 `v0.1.0`。本工具按单一版本线工作，采用当前分支可达的最高版本标签；多个长期维护版本线或独立包版本需要使用项目自己的发布流程。发布创建本地提交和标签，默认不会创建 GitHub Release、上传安装包或部署。

发布检查失败时恢复工具自身产生的版本和 CHANGELOG 修改，验证命令另外产生的内容保留供检查。提交失败恢复原暂存区；标签创建失败保留已经完成的发布提交，修复原因后重试 `release --write` 会补建标签。

## README 与 CHANGELOG

README 按实际项目保留合理结构，介绍用途、安装、使用、配置、验证、常见问题与卸载。安装、命令、默认值、环境要求或兼容性变化时同步对应说明和示例；内部调整只需检查，仍准确时不强制修改。

用户可见的新增、修复或不兼容变化写入 `CHANGELOG.md` 的待发布段：

```markdown
# 更新日志

## [Unreleased]

### 新增

- 支持将项目摘要导出为 JSON。
```

发布时保留一个空待发布段，将内容归入 `## [版本] - YYYY-MM-DD`，日期为 Asia/Shanghai。缺少 CHANGELOG 时可以创建；已有文件必须包含独立的 `## [Unreleased]` 或 `## [待发布]`，其他自定义结构先由助手整理。待发布段为空时从 `feat/fix/perf` 和不兼容提交整理简短说明；复杂迁移应事先人工补充。同一目标版本从预发布转为正式版时，累计该版本全部预发布说明并去重；没有新增变化的后续预发布沿用上一版说明。历史已发布记录保持原样。

脚本检查 AGENTS.md 中每个文件的命名与存放出处、非空 README、Markdown 行内本地链接、版本一致性以及配置的验证命令；不会自动验证远端链接、参考式链接或判断文档语义。说明准确性和应更新哪些章节由助手结合实际差异检查。

## 推送与失败重试

单次使用 `--push` 可以覆盖默认设置，`--no-push` 可以覆盖 `auto_push=true`。例如：

```powershell
# 自动推送已经提交的修改，默认仍先预览
python .axiom-manager/manage.py push
python .axiom-manager/manage.py push --write

# 原子推送发布提交和标签；标签必须指向当前提交
python .axiom-manager/manage.py push --tag v0.1.0 --write
```

远端不存在、认证失败或远端拒绝推送时，本地提交和标签保持有效。修复原因后使用 `push` 重试，不重复提交。发布提交与标签使用 `git push --atomic`；远端不支持时会报错，保留本地结果。不强制推送，不自动改写历史。

## 更新与卸载

使用更新后的工具来源重新安装即可。原有配置保持不变；如果运行脚本存在本地修改，安装器停止，先保存并处理修改再更新。

```powershell
# 先预览卸载
python E:/zl/01-Project/axiom-manager/scripts/install_rules.py E:/work/my-project --uninstall

# 移除规则块和未修改的安装文件
python E:/zl/01-Project/axiom-manager/scripts/install_rules.py E:/work/my-project --uninstall --write
```

卸载移除 Axiom-manager 工具块，包括在该块内首次生成的文件规则；块外已有的项目规则保持原样。需要继续保留块内项目文件规则时，应先将其完整移到块外再卸载。用户修改过的运行文件、安装前已有的配置、备份和其他规则保留，保留自定义运行文件时也保留安装记录。空目录可检查后手动清理。若需要回到安装前的 AGENTS.md，可核对 `.axiom-manager/backups/` 中的原件；恢复整份文件前先保留安装后的其他修改。

锁文件用于排除同工具并发操作。异常中止后，如果确认相关进程已经结束，检查并移除目标根目录 `.axiom-manager-install.lock` 或 Git 目录中的 `axiom-manager.lock`。安装器更新关键文件时先备份并采用临时文件替换，失败时尝试恢复已修改文件。

## 开发与验证

本工具仓库使用源码脚本，等价命令为 `python scripts/manage_project.py ...`，项目验证配置位于 [.axiom-manager/config.json](.axiom-manager/config.json)。

```powershell
python -m unittest discover -s tests -v
python scripts/manage_project.py layout --verbose
python scripts/manage_project.py check
python scripts/install_rules.py --help
python scripts/manage_project.py --help
```

测试在临时目录创建仓库，覆盖规则安装与卸载、保护现有内容、文件规则初始化、新文件出处、命名与位置检查、特殊任务归属、中文提交、版本和锁文件同步、失败恢复及本地裸仓库推送。AGENTS.md 约束读取它的编码助手，不是文件监控服务；手工或其他工具修改文件时不会触发后台提交。

## 规范依据与许可

安装形式参考 [Axiom-reporter](https://github.com/1993zlorange/Axiom-reporter)，本项目脚本独立实现。版本依据 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)，提交依据 [约定式提交中文规范](https://www.conventionalcommits.org/zh-hans/v1.0.0/)。中文说明、标题长度、`perf` 发补丁和 0.x 不兼容升级次版本是本工具的具体约定。

公开项目参考：[Google Angular](https://angular.dev/reference/releases)、[Angular 提交指南](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md)、[Microsoft .NET](https://learn.microsoft.com/en-us/dotnet/core/versions/)、[Ant Design](https://ant.design/components/changelog/)、[腾讯 TDesign](https://github.com/Tencent/tdesign-vue-next/blob/develop/CONTRIBUTING.md)。这些规则属于对应项目，不代表各公司所有内部项目。

MIT，见 [LICENSE](LICENSE)。
