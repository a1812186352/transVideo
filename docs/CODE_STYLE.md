# transVideo 代码规范

> 版本 v1.0.0 · 2026-07-14
> 覆盖：Python（后端/管线）· TypeScript + Vue（前端）· CSS
> 原则：≤10 条规则，全部可自动检查

---

## Python（后端 / 管线）

| # | 规则 | 工具 | 说明 |
|---|------|------|------|
| P1 | 行宽 ≤100 字符 | ruff | 历史风格一致（现有代码无超过 100 列的行） |
| P2 | 双引号字符串 | ruff | 与现有 docstring 和代码风格一致 |
| P3 | import 顺序：stdlib → 第三方 → 本地 | ruff (isort) | 本地包前缀：`backend`, `script`, `understanding`, `generation`, `processing` |
| P4 | 公共函数必须有 docstring | ruff (pydocstyle) | Google 风格 docstring；`__init__.py` 和信号处理文件豁免 |
| P5 | 禁止未使用的 import/变量 | ruff (F) | pyflakes 自动检测 |

**检查**：`ruff check backend/ script/ understanding/ processing/ generation/`

---

## TypeScript / Vue（前端）

| # | 规则 | 工具 | 说明 |
|---|------|------|------|
| T1 | 单引号、尾逗号、分号 | biome | 现有 frontend 代码风格 |
| T2 | 缩进 2 空格 | biome | Vue SFC 标准缩进 |
| T3 | `const` 优先于 `let`；禁止 `var` | biome | 不可变优先 |
| T4 | 模板字面量优先于字符串拼接 | biome | `\`text ${x}\`` 而非 `'text' + x` |

**检查**：`npx biome check frontend/src/`

---

## CSS（前端样式）

| # | 规则 | 工具 | 说明 |
|---|------|------|------|
| C1 | 使用 CSS 自定义属性（design tokens） | human review | 颜色/间距/圆角统一通过 `var(--name)` 引用，参考 `taste` skill 定义的 token 集 |

---

## 强制执行

| 层级 | 触发条件 | 命令 |
|------|----------|------|
| pre-commit | `git commit` 前 | `ruff check . && npx biome check frontend/src/` |
| CI | PR 提交 | 同上，exit code ≠ 0 则阻断合并 |
| editor | 保存时 | VS Code: ruff 插件 + biome 插件 |
