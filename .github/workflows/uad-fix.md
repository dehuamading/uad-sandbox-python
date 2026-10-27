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
      attempt: {description: "第几次尝试（1|2），由 uad-gate/uad-verify 设置", required: false, default: "1"}
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
max-turns: 40
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
  - name: 尝试次数保护（同一问题 ≤2）
    run: 'case "${{ inputs.attempt }}" in 1|2|"") ;; *) echo "::error::尝试次数超过 2，停止"; exit 1;; esac'
  - name: 下载失败证据（只读）
    if: inputs.source_run_id != ''
    env: {GH_TOKEN: "${{ github.token }}"}
    run: |
      gh run download "${{ inputs.source_run_id }}" -R "${{ github.repository }}" -n uad-evidence -D .uad-evidence || echo "无证据工件"
      git rev-parse HEAD > .uad-evidence/base_sha 2>/dev/null || { mkdir -p .uad-evidence; git rev-parse HEAD > .uad-evidence/base_sha; }
  - name: 准备测试环境
    run: python3 -m pip install -q pytest && python3 -m pytest --version
jobs:
  uad_chain_verify:
    needs: [agent, detection, safe_outputs]
    if: always() && needs.agent.outputs.has_patch == 'true' && needs.detection.outputs.detection_success == 'true'
    runs-on: ubuntu-latest
    permissions: {actions: write}
    steps:
      - name: 触发确定性验证/回滚（uad-verify，不调用 AI）
        run: GH_TOKEN="${{ github.token }}" gh workflow run uad-verify.yml -R "${{ github.repository }}" --ref "${{ github.ref_name }}" -f fix_run_id="${{ github.run_id }}" -f attempt="${{ inputs.attempt || '1' }}" -f apply=true -f signature="${{ inputs.signature }}" -f track_issue="${{ inputs.track_issue }}"
safe-outputs:
  threat-detection:
    engine: false
    post-steps:
      - name: UAD 确定性威胁检测（写出 gh-aw 判定文件）
        id: detection_agentic_execution
        run: |
          B="https://raw.githubusercontent.com/dehuamading/universal-ai-devops/${{ vars.UAD_FRAMEWORK_REF || 'main' }}/tools"
          curl -sfL "$B/uad-guard.py" -o /tmp/uad-guard.py || rm -f /tmp/uad-guard.py
          curl -sfL "$B/uad-detect.sh" -o /tmp/uad-detect.sh
          bash /tmp/uad-detect.sh /tmp/uad-guard.py /tmp/gh-aw/threat-detection
  create-pull-request:
    draft: true
    base-branch: lab/rollback
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

模式：`${{ inputs.mode }}`；失败签名：`${{ inputs.signature }}`；相关 issue：`${{ inputs.issue_number }}`；跟踪 issue：`${{ inputs.track_issue }}`；本问题第 `${{ inputs.attempt }}` 次尝试（上限 2）。若为第 2 次，`.uad-evidence/failure-summary.json` 中是上一次补丁被回滚的原因，必须据此调整方案。

## 必须按顺序执行
1. 读取仓库根目录 `AGENTS.md`、`uad.config.yml`、`docs/business-rules.md`。在回答开头写一行：`已读取规则: AGENTS.md`，并复述 A/B/C 三个等级各一句话。
2. 加载并遵循技能：`uad-fix-loop`、`uad-classify-change`、`uad-report-zh`，以及 Superpowers 的 `systematic-debugging`、`test-driven-development`、`verification-before-completion`。每使用一个技能，写一行 `使用技能: <名称>`。
3. **fix 模式**：读取 `.uad-evidence/failure-summary.json` 和 `.uad-evidence/console.log`，基线提交在 `.uad-evidence/base_sha`。用 ``python -m pytest -q -m "not core and not full"``（A 级快速测试；C 级全量回归随后由 uad-verify 确定性执行） 复现。对**每个失败问题**分别：根因 → 分级 → A 级则按 uad-fix-loop 修复（最多 2 次尝试，失败则 `git reset --hard` 回到该问题的检查点并写明“已回退到 <sha>”）。
   - 有至少一个问题修复成功且 ``python -m pytest -q -m "not core and not full"``（A 级快速测试；C 级全量回归随后由 uad-verify 确定性执行） 中该问题相关的测试通过：调用 `create_pull_request`（中文标题与正文，使用 uad-report-zh 模板，写明基线提交、尝试次数、测试命令和结果、剩余未修复问题）。
   - 无法修复或属于 B 级的问题：调用 `create_issue`，标题写明“无法自动修复”或“需要批准”，正文用中文写根因、证据、尝试与回退记录、建议方案；并对跟踪 issue `add_comment` 一份摘要。
4. **request 模式**：读取 issue #${{ inputs.issue_number }}（用 GitHub 工具）。用 uad-classify-change 分级。B/C 级：**不写任何代码**，对该 issue `add_comment` 中文方案（影响范围、风险、需要用户批准的事项），并 `add_labels` 加 `needs-approval` 和 `uad-b-level`。若确实是 A 级，按 fix 模式处理。
5. 禁止删除、跳过或弱化测试；禁止修改 `docs/business-rules.md`；禁止把密钥写入任何输出。
6. 最后用中文总结：等级判断、根因、做了什么、测试证据、是否回退。

## 效率要求（硬性）
- LLM 调用上限 40 次。读文件尽量一次 `cat` 多个；技能文件每个只读一次。
- 修复验证通过后**立即**调用 `create_pull_request`（不要反复 stash/重跑测试）；失败或 B/C 级则立即调用 `create_issue`/`add_comment`。
- 结束前必须调用一个 safe-output 工具。
