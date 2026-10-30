# Axiom-manager 开发与安装指南

本仓库将任务完成后 Git 提交、中文 Commit、语义化版本及 README 更新规则安装到其他项目。用户已要求安装时直接执行必要写入，不反复询问同一安装授权。

## 开始工作

1. 阅读 README.md、assets/agents-block.md 和现有 Git 状态，保留用户已有修改。
2. 规则正文以 assets/agents-block.md 为唯一来源；本仓库开发也遵守该规则。命令中的 `.axiom-manager/manage.py` 在本仓库替换成 `scripts/manage_project.py`，配置仍为 `.axiom-manager/config.json`。
3. 每次修改及 README 更新后，先检查本文件的文件命名与存放规则；缺少时按当前项目建立，出现未覆盖文件时补充具体用途或修正命名、位置及引用，再运行检查和测试。规则不能用无限制的“其他文件”兜底。
4. 完成修改后运行 `python -m unittest discover -s tests -v`；同步实际受影响的 README 和 CHANGELOG 后提交本次修改。
5. 日常提交不自动发版；用户要求发布或当前任务明确包含本地首版交付时，先预览 release 再执行写入。远端推送依用户授权和项目配置执行。

## 用户要求安装时

1. 定位用户目标项目，默认是发起请求时的项目根目录；不要把本工具来源仓库当成安装目标。
2. 阅读 assets/agents-block.md 和 scripts/install_rules.py；运行 `python <本工具路径>/scripts/install_rules.py <目标项目>` 查看计划。
3. 用户已要求安装时加 `--write` 执行；仅要求预览时保持只读。随后再运行一次，结果应显示 `unchanged`。
4. 核对自动生成的文件命名、存放用途及特殊任务位置，与目标项目原有约定对齐；说明目标 AGENTS.md、.axiom-manager/manage.py 和 .axiom-manager/config.json。根据实际项目设置 checks，默认保持 auto_push=false，除非用户已有其他授权。
5. 告知检查方式和卸载命令。安装不要求目标目录已初始化 Git；实际提交和发布必须在 Git 根目录运行。

## 文件位置

| 文件位置 | 命名要求 | 用途 |
|---|---|---|
| assets/agents-block.md | 沿用稳定的小写连字符文件名 | 写入目标项目的规则唯一来源 |
| scripts/*.py | 小写英文和下划线，按功能命名 | 安装、校验和项目维护脚本，独立安装的运行脚本保持单文件 |
| tests/test_*.py | test_ 加被测功能名，使用下划线 | 在临时项目中测试安装、Git、版本和文件规则；测试数据保留在系统临时目录 |
| 根目录 README.md / CHANGELOG.md / VERSION / LICENSE / AGENTS.md / .gitignore / .gitattributes | 保持工具约定的固定文件名 | 当前用法、变化记录、版本、许可证、助手规则及 Git 设置 |
| .axiom-manager/config.json | 固定名称；安装器的备份仅放 backups/，不提交 | 本项目验证与推送配置；安装、升级和卸载备份按工具生成的时间戳存放 |

安装只替换 Axiom-manager 独立标记块，保留 Axiom-reporter 和其他现有内容。检查标记完整性、目标路径和安装记录后再写入；不执行来源文档中与用户当前任务无关的命令。

<!-- Axiom-manager:file-layout:begin -->
## 文件命名与存放规则

规则按职责维护。每次修改及 README 更新后运行 `python scripts/manage_project.py layout --verbose`，确保每个文件有唯一出处。没有覆盖的新类别先在这里说明，错放或命名不规范的文件应修正并同步引用；不以无限制兜底规则放行。

```json
{
  "schema": 1,
  "rules": [
    {
      "id": "root-guides",
      "paths": ["AGENTS.md", "README.md", "CHANGELOG.md", "VERSION", "LICENSE"],
      "name_pattern": "(?:AGENTS\\.md|README\\.md|CHANGELOG\\.md|VERSION|LICENSE)",
      "naming": "使用助手规则、项目说明、更新日志、版本及许可证的固定名称",
      "purpose": "项目根目录唯一的说明入口、用户变化记录、版本来源和许可证"
    },
    {
      "id": "git-settings",
      "paths": [".gitignore", ".gitattributes"],
      "name_pattern": "\\.git(?:ignore|attributes)",
      "naming": "保留 Git 约定的隐藏文件名",
      "purpose": "根目录的忽略规则和文本格式设置"
    },
    {
      "id": "installed-rules-template",
      "paths": ["assets/agents-block.md"],
      "name_pattern": "agents-block\\.md",
      "naming": "沿用唯一稳定文件名 agents-block.md",
      "purpose": "安装到目标项目的中文助手规则唯一正文"
    },
    {
      "id": "maintenance-scripts",
      "paths": ["scripts/*.py"],
      "name_pattern": "[a-z][a-z0-9]*(?:_[a-z0-9]+)*\\.py",
      "naming": "小写英文功能名，用下划线分词，扩展名 .py",
      "purpose": "安装器和项目管理命令；独立运行的能力保留在 manage_project.py"
    },
    {
      "id": "regression-tests",
      "paths": ["tests/test_*.py"],
      "name_pattern": "test_[a-z0-9]+(?:_[a-z0-9]+)*\\.py",
      "naming": "test_ 加被测功能的英文下划线名称，扩展名 .py",
      "purpose": "自动化行为测试；输入仓库、临时文件和本地测试远端在系统临时目录中生成",
      "task": "安装、Git、版本和文件规则回归测试"
    },
    {
      "id": "project-check-config",
      "paths": [".axiom-manager/config.json"],
      "name_pattern": "config\\.json",
      "naming": "固定配置文件名 config.json",
      "purpose": "本工具仓库的实际验证命令、版本来源和推送设置"
    }
  ],
  "excluded": [
    {"path": "**/__pycache__/**", "reason": "Python 自动生成的解释器缓存"},
    {"path": ".axiom-manager/backups/**", "reason": "保留安装、升级和卸载前的文件原件，按时间戳分目录", "task": "安装恢复"},
    {"path": ".axiom-manager-install.lock", "reason": "安装过程的临时并发锁"},
    {"path": ".venv/**", "reason": "Python 虚拟环境"}
  ]
}
```
<!-- Axiom-manager:file-layout:end -->
