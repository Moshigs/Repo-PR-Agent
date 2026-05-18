## Repo-PR-Agent

**仓库体检 + 多角色补丁草案**：用 `scan` 把技术债与（可选）静态检查结构化为 JSON，再由 `run` 串起 **Planner → Coder → Reviewer**，产出可审阅 Markdown 与 Planner 元数据，便于挂到 PR / 内部流程里做记录。

### 背景

团队里「让模型改代码」最大的问题往往是：输入是什么、谁规划、谁起草、谁兜底。本工具把前半段 **事实（扫描结果）** 和后半段 **提案（补丁草案 + 评审意见）** 分开落盘，便于和 CI、人工 review、issue 跟踪对齐。

### 能力

- **scan**：按后缀遍历源码，只解析注释行 `#` / `//` / `--` 中的 `TODO` / `FIXME` / `HACK` / `XXX`；若本机有 `ruff` CLI，则并入其 JSON 输出。
- **run**：消费体检 JSON，按任务优先级截取若干条，拉取相关文件片段上下文，驱动大模型完成规划、编码建议、独立评审。
- **可选配图**：`scripts/generate_images.py` 使用 OpenAI **Image API**（默认 `gpt-image-2`），由 `prompts/image_generation_prompts.json` 批量生成说明用示意图，**不得**用于冒充真实监控或账单界面。

---

### 环境

- Python **3.10+**
- `run`（非 `--dry-run`）依赖 **OpenAI Chat 兼容接口**（环境变量见下）

---

### 快速开始

```powershell
git clone https://github.com/Moshigs/Repo-PR-Agent.git
cd Repo-PR-Agent

python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -r requirements.txt

python -m repo_pr_agent scan --root <目标仓库根> --out reports\scan.json
python -m repo_pr_agent run --scan reports\scan.json --root <同上根> --dry-run --report reports\orchestration.md

copy .env.example .env
python -m repo_pr_agent run --scan reports\scan.json --root <同上根> --max-tasks 3 --report reports\orchestration.md
```

`run` 会另存 `reports\<报告名>.planner_meta.json`，保留 Planner 原始 JSON。

---

### 配置

| 变量 | 说明 |
|-----------|------|
| `OPENAI_API_KEY` | 必填 |
| `OPENAI_BASE_URL` | 可选 |
| `OPENAI_MODEL` | Chat 模型名，默认 `gpt-4o-mini` |

---

### 布局

```
repo_pr_agent/
scripts/generate_images.py
prompts/image_generation_prompts.json
```

---

### Roadmap

- [ ] 远程托管：自动开分支与 Draft PR
- [ ] `git apply --check` 与人工确认的封装
- [ ] CI / pre-commit 示例

---

### License

自行添加 `LICENSE`（如 MIT）后在此说明。

---

## Security：公开前请勿提交

| 类型 | 示例 | 说明 |
|------|------|------|
| 密钥 | `.env`、`*.pem`、`id_rsa` | 泄露即滥用 |
| 私密扫描 | 对内部仓跑出的 `reports/` | 暴露路径与文件名规律 |
| 误导性插图 | 用生成图顶替真实监控系统截屏对外宣称 | 审计与合规风险 |
| 垃圾目录 | `node_modules`、`dist`、`__pycache__` | 体积与噪声 |

`.gitignore` 已排除 `.env`、运行时 `reports/*`（保留占位文件）、典型图片后缀等。**密钥曾出现在历史中时须轮换**。
