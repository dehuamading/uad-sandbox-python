---
name: uad-fix
run-name: "uad-fix track#${{ inputs.track_issue }} ${{ inputs.mode }} ${{ inputs.signature }}"
description: UAD 自动修复（Pi + DeepSeek V4.1 Flash + Superpowers）。只能由 uad-gate 触发；只读运行，写操作仅草稿 PR / issue / 评论。
on:
  workflow_dispatch:
    inputs:
      mode: {description: "fix | request", required: true, default: fix}
      source_run_id: {description: "失败的测试 run id", required: false, default: ""}
      signature: {description: "失败签名", required: false, default: ""}
      issue_number: {description: "request 模式的 issue 编号", required: false, default: ""}
      track_issue: {description: "跟踪 issue 编号", required: false, default: ""}
  bots: ["github-actions[bot]"]
permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read
  copilot-requests: none
concurrency:
  group: uad-fix-${{ github.repository }}
  cancel-in-progress: false
models:
  default-ai-credits-pricing:
    input: 0.15
    output: 0.6
timeout-minutes: 15
max-turns: 20
max-tool-calls: 60
engine:
  id: pi
  model: deepseek/deepseek-flash
  model-provider: openai
  env:
    OPENAI_BASE_URL: https://api.deepseek.com/v1
    OPENAI_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    SUPERPOWERS_DISABLE_TELEMETRY: "1"
  extensions:
    - git:github.com/obra/superpowers@v7.0.1
    - git:github.com/dehuamading/universal-ai-devops@main
network:
  allowed: [defaults, node, python, api.deepseek.com]
tools:
  edit:
  bash: ["python", "python3", "pytest", "pip", "git", "cat", "ls", "grep", "head", "tail", "find", "wc", "diff"]
steps:
  - name: 下载失败证据（只读）
    if: inputs.source_run_id != ''
    env: {GH_TOKEN: "${{ github.token }}"}
    run: |
      gh run download "${{ inputs.source_run_id }}" -R "${{ github.repository }}" -n uad-evidence -D .uad-evidence || echo "无证据工件"
      git rev-parse HEAD > .uad-evidence/base_sha 2>/dev/null || { mkdir -p .uad-evidence; git rev-parse HEAD > .uad-evidence/base_sha; }
  - name: 准备测试环境
    run: python3 -m pip install -q pytest && python3 -m pytest --version
safe-outputs:
  threat-detection:
    engine: false
    post-steps:
      - name: UAD 确定性补丁守卫（替代 Copilot 威胁检测）
        run: |
          curl -sfL https://raw.githubusercontent.com/dehuamading/universal-ai-devops/main/tools/uad-guard.py -o /tmp/uad-guard.py
          shopt -s nullglob; P=(/tmp/gh-aw/threat-detection/*.patch)
          if [ ${#P[@]} -eq 0 ]; then echo "无补丁"; exit 0; fi
          python3 /tmp/uad-guard.py "${P[@]}"
  create-pull-request:
    draft: true
    title-prefix: "[uad-fix] "
    labels: [uad-fix]
    max: 1
    excluded-files: [".uad-evidence/**", ".uad-out/**"]
    fallback-as-issue: false
  create-issue:
    title-prefix: "[uad] "
    labels: [uad]
    max: 2
  add-comment:
    target: "*"
    max: 2
  add-labels:
    allowed: [needs-approval, uad-b-level, uad-failed, uad-fixed]
    target: "*"
    max: 3
---

# UAD 自动修复任务

你是在 GitHub Actions 中运行的自动修复智能体。**你对仓库只读**；你的修改只能通过 safe-outputs 变成草稿 PR。你不能、也不得尝试推送 main、合并 PR、修改 `.github/` 或权限。

模式：`${{ inputs.mode }}`；失败签名：`${{ inputs.signature }}`；相关 issue：`${{ inputs.issue_number }}`；跟踪 issue：`${{ inputs.track_issue }}`。

## 必须按顺序执行
1. 读取仓库根目录 `AGENTS.md`、`uad.config.yml`、`docs/business-rules.md`。在回答开头写一行：`已读取规则: AGENTS.md`，并复述 A/B/C 三个等级各一句话。
2. 加载并遵循技能：`uad-fix-loop`、`uad-classify-change`、`uad-report-zh`，以及 Superpowers 的 `systematic-debugging`、`test-driven-development`、`verification-before-completion`。每使用一个技能，写一行 `使用技能: <名称>`。
3. **fix 模式**：读取 `.uad-evidence/failure-summary.json` 和 `.uad-evidence/console.log`，基线提交在 `.uad-evidence/base_sha`。用 ``python -m pytest -q`` 复现。对**每个失败问题**分别：根因 → 分级 → A 级则按 uad-fix-loop 修复（最多 2 次尝试，失败则 `git reset --hard` 回到该问题的检查点并写明“已回退到 <sha>”）。
   - 有至少一个问题修复成功且 ``python -m pytest -q`` 中该问题相关的测试通过：调用 `create_pull_request`（中文标题与正文，使用 uad-report-zh 模板，写明基线提交、尝试次数、测试命令和结果、剩余未修复问题）。
   - 无法修复或属于 B 级的问题：调用 `create_issue`，标题写明“无法自动修复”或“需要批准”，正文用中文写根因、证据、尝试与回退记录、建议方案；并对跟踪 issue `add_comment` 一份摘要。
4. **request 模式**：读取 issue #${{ inputs.issue_number }}（用 GitHub 工具）。用 uad-classify-change 分级。B/C 级：**不写任何代码**，对该 issue `add_comment` 中文方案（影响范围、风险、需要用户批准的事项），并 `add_labels` 加 `needs-approval` 和 `uad-b-level`。若确实是 A 级，按 fix 模式处理。
5. 禁止删除、跳过或弱化测试；禁止修改 `docs/business-rules.md`；禁止把密钥写入任何输出。
6. 最后用中文总结：等级判断、根因、做了什么、测试证据、是否回退。
