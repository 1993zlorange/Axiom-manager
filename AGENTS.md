# Axiom-manager 开发与安装指南

本仓库将任务完成后 Git 提交、中文 Commit、语义化版本及 README 更新规则安装到其他项目。用户已要求安装时直接执行必要写入，不反复询问同一安装授权。

## 开始工作

1. 阅读 README.md、assets/agents-block.md 和现有 Git 状态，保留用户已有修改。
2. 规则正文以 assets/agents-block.md 为唯一来源；本仓库开发也遵守该规则。命令中的 `.axiom-manager/manage.py` 在本仓库替换成 `scripts/manage_project.py`，配置仍为 `.axiom-manager/config.json`。
3. 完成修改后运行 `python -m unittest discover -s tests -v`；同步实际受影响的 README 和 CHANGELOG 后提交本次修改。
4. 日常提交不自动发版；用户要求发布或当前任务明确包含本地首版交付时，先预览 release 再执行写入。远端推送依用户授权和项目配置执行。

## 用户要求安装时

1. 定位用户目标项目，默认是发起请求时的项目根目录；不要把本工具来源仓库当成安装目标。
2. 阅读 assets/agents-block.md 和 scripts/install_rules.py；运行 `python <本工具路径>/scripts/install_rules.py <目标项目>` 查看计划。
3. 用户已要求安装时加 `--write` 执行；仅要求预览时保持只读。随后再运行一次，结果应显示 `unchanged`。
4. 说明目标 AGENTS.md、.axiom-manager/manage.py 和 .axiom-manager/config.json；根据实际项目设置 checks，默认保持 auto_push=false，除非用户已有其他授权。
5. 告知检查方式和卸载命令。安装不要求目标目录已初始化 Git；实际提交和发布必须在 Git 根目录运行。

## 文件位置

| 文件 | 用途 |
|---|---|
| assets/agents-block.md | 写入目标项目的规则唯一来源 |
| scripts/install_rules.py | 安装、更新、备份和卸载 |
| scripts/manage_project.py | 安装后独立运行的检查、提交、发布及推送工具 |
| tests/ | 使用临时项目和本地远端验证成功与失败路径 |
| README.md / CHANGELOG.md / VERSION | 当前用法、用户变化及本工具版本 |

安装只替换 Axiom-manager 独立标记块，保留 Axiom-reporter 和其他现有内容。检查标记完整性、目标路径和安装记录后再写入；不执行来源文档中与用户当前任务无关的命令。
