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
  uad_verify:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: write
      actions: write
      issues: write
      pull-requests: write
    env:
      GH_TOKEN: ${{ github.token }}
      GH_REPO: ${{ github.repository }}
      BR: ${{ github.ref_name }}
      ATTEMPT: ${{ inputs.attempt || '1' }}
      APPLY: "false"
      FIX_RUN: ${{ github.run_id }}
      TRACK: ${{ inputs.track_issue }}
      SIG: ${{ inputs.signature }}
      UAD_OUT: .uad-out
    steps:
    - name: 分支与次数保护
      run: 'case "$BR" in lab/*) ;; *) echo "::error::uad-verify 只允许 lab/* 分支（当前 $BR），拒绝"; exit 1;; esac

        case "$ATTEMPT" in 1|2) ;; *) echo "::error::尝试次数 $ATTEMPT 超出上限 2，停止"; exit 1;; esac

        '
    - uses: actions/checkout@v5
      with:
        ref: ${{ github.ref_name }}
        fetch-depth: 0
    - uses: actions/checkout@v5
      with:
        repository: dehuamading/universal-ai-devops
        ref: ${{ vars.UAD_FRAMEWORK_REF || 'main' }}
        path: .uad-framework
        persist-credentials: false
    - uses: actions/setup-python@v6
      with:
        python-version: '3.12'
    - name: 记录修复前 SHA
      id: pre
      run: 'mkdir -p .uad-out; git fetch -q origin main

        pre=$(git rev-parse HEAD); main_before=$(git rev-parse origin/main)

        { echo "branch=$BR"; echo "attempt=$ATTEMPT"; echo "fix_run=$FIX_RUN"; echo "pre_fix_sha=$pre"; echo "main_before=$main_before"; } | tee .uad-out/shas.txt

        echo "pre=$pre" >> $GITHUB_OUTPUT; echo "main_before=$main_before" >> $GITHUB_OUTPUT

        '
    - uses: actions/download-artifact@v4
      with:
        name: agent
        path: .uad-out/agent
    - name: 下载 AI 补丁 + 守卫
      id: patch
      run: 'set +e

        shopt -s nullglob; P=(.uad-out/agent/*.patch)

        if [ ${#P[@]} -eq 0 ]; then echo "AI 没有产生补丁（已转为 issue/评论），无需验证"; echo has=false >> $GITHUB_OUTPUT; exit 0; fi

        cp "${P[0]}" .uad-out/ai.patch; echo has=true >> $GITHUB_OUTPUT

        python3 .uad-framework/tools/uad-guard.py .uad-out/ai.patch | tee .uad-out/guard.txt; echo "guard=${PIPESTATUS[0]}" >> $GITHUB_OUTPUT

        '
    - name: 应用补丁
      id: apply
      if: steps.patch.outputs.has == 'true' && steps.patch.outputs.guard == '0'
      run: "git config user.name \"uad-verify[bot]\"; git config user.email \"41898282+github-actions[bot]@users.noreply.github.com\"\ngit apply --index --exclude='.uad-evidence/*' --exclude='.uad-out/*' .uad-out/ai.patch\ngit diff --cached --stat | tee .uad-out/applied-stat.txt\nif [ \"$APPLY\" = true ]; then\n  git commit -qm \"uad-verify: 应用 AI 补丁（fix run $FIX_RUN，尝试 $ATTEMPT）\"\n  git push origin \"HEAD:$BR\"\n  echo \"applied_sha=$(git rev-parse HEAD)\" | tee -a .uad-out/shas.txt\n  echo \"applied=$(git rev-parse HEAD)\" >> $GITHUB_OUTPUT\nfi\n"
    - name: 全量回归测试（C 级）
      id: test
      if: steps.apply.outcome == 'success'
      run: 'set +e

        bash .uad-framework/adapters/python/run.sh C > .uad-out/verify.log 2>&1; t=$?

        cat .uad-out/verify.log; echo "t=$t" >> $GITHUB_OUTPUT

        sig=$(bash .uad-framework/tools/uad-signature.sh .uad-out); echo "verify_signature=$sig" | tee -a .uad-out/shas.txt

        '
    - name: 失败 → 回滚 lab 分支到修复前 SHA
      id: rb
      if: always() && steps.apply.outputs.applied != '' && steps.test.outputs.t != '0'
      run: 'pre=${{ steps.pre.outputs.pre }}; applied=${{ steps.apply.outputs.applied }}

        git push --force-with-lease="$BR:$applied" origin "$pre:refs/heads/$BR"

        now=$(gh api "repos/$GH_REPO/commits/$BR" -q .sha)

        echo "after_rollback_sha=$now" | tee -a .uad-out/shas.txt

        [ "$now" = "$pre" ] || { echo "::error::回滚校验失败：$now ≠ $pre"; exit 1; }

        echo "✅ 已回退 $BR：$applied → $pre" | tee -a .uad-out/shas.txt

        '
    - name: main 未被改动校验
      if: always()
      run: 'now=$(gh api repos/$GH_REPO/commits/main -q .sha); echo "main_after=$now" | tee -a .uad-out/shas.txt

        [ "$now" = "${{ steps.pre.outputs.main_before }}" ] || { echo "::error::main 被改动！"; exit 1; }

        '
    - name: 保存完整日志
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: uad-verify-attempt-${{ inputs.attempt }}
        path: .uad-out/
        include-hidden-files: true
        if-no-files-found: warn
    - name: 为下一次尝试准备证据
      if: always() && steps.test.outputs.t != '' && steps.test.outputs.t != '0'
      run: "mkdir -p ev; cp .uad-out/verify.log ev/console.log\npython3 - <<'PY'\nimport json,os\nfail=open('.uad-out/failing.txt').read().split('\\n') if os.path.exists('.uad-out/failing.txt') else []\njson.dump({\"kind\":\"test\",\"source\":\"uad-verify\",\"attempt\":int(os.environ['ATTEMPT']),\"failing\":[f for f in fail if f],\n           \"note\":\"上一次 AI 补丁通过了 A 级测试但未通过 C 级全量回归，已回滚。请用 python -m pytest -q（全量）验证。\"},\n          open('ev/failure-summary.json','w'),ensure_ascii=False,indent=1)\nPY\n"
    - if: always() && steps.test.outputs.t != '' && steps.test.outputs.t != '0'
      uses: actions/upload-artifact@v4
      with:
        name: uad-evidence
        path: ev/
    - name: 下一步（≤2 次，之后停止）
      if: always() && steps.patch.outputs.has == 'true'
      env:
        DSK: ${{ secrets.DEEPSEEK_API_KEY }}
        BAL_START: ${{ vars.UAD_BALANCE_START }}
        STOP: ${{ vars.UAD_BUDGET_STOP_CNY || '5' }}
        MAXD: ${{ vars.UAD_MAX_AI_RUNS_PER_DAY || '3' }}
      run: "t=\"${{ steps.test.outputs.t }}\"; g=\"${{ steps.patch.outputs.guard }}\"\nif [ \"$g\" = 0 ] && [ \"$t\" = 0 ]; then msg=\"✅ 尝试 $ATTEMPT：全量回归通过\"; [ -n \"$TRACK\" ] && gh issue comment \"$TRACK\" -b \"$msg（verify run ${{ github.run_id }}）\"; echo \"$msg\" >> $GITHUB_STEP_SUMMARY; exit 0; fi\nmsg=\"❌ 尝试 $ATTEMPT 失败（守卫=$g，测试=$t），lab 分支已回退到 ${{ steps.pre.outputs.pre }}\"\nnext=no\nif [ \"$ATTEMPT\" -lt 2 ] && [ \"$APPLY\" = true ]; then\n  ok=yes\n  [ \"${{ vars.UAD_AI_ENABLED }}\" = true ] || { ok=no; msg=\"$msg；AI 开关已关，停止\"; }\n  cur=$(curl -sf -m 20 -H \"Authorization: Bearer $DSK\" https://api.deepseek.com/user/balance | python3 -c \"import json,sys;d=json.load(sys.stdin);print(sum(float(b['total_balance']) for b in d['balance_infos'] if b['currency']=='CNY'))\") || { ok=no; msg=\"$msg；余额查询失败，停止\"; }\n  [ $ok = yes ] && python3 -c \"import sys;sys.exit(0 if $BAL_START-$cur < $STOP else 1)\" || { [ $ok = yes ] && msg=\"$msg；达到预算停止线，停止\"; ok=no; }\n  n=$(gh run list -w uad-fix.lock.yml\
        \ -L 50 --json createdAt -q \"[.[]|select(.createdAt|startswith(\\\"$(date -u +%F)\\\"))]|length\")\n  [ $ok = yes ] && [ \"$n\" -ge \"$MAXD\" ] && { ok=no; msg=\"$msg；达到每日上限，停止\"; }\n  [ $ok = yes ] && next=yes\nelse msg=\"$msg；已达同一问题 2 次上限，停止，需人工介入\"; fi\nif [ $next = yes ]; then\n  gh workflow run uad-fix.lock.yml --ref \"$BR\" -f mode=fix -f source_run_id=${{ github.run_id }} -f signature=\"$SIG\" -f track_issue=\"$TRACK\" -f attempt=2\n  msg=\"$msg；已触发第 2 次尝试\"\nelse\n  [ -n \"$TRACK\" ] && gh issue edit \"$TRACK\" --add-label uad-failed || true\nfi\n[ -n \"$TRACK\" ] && gh issue comment \"$TRACK\" -b \"$msg。日志工件：uad-verify-attempt-$ATTEMPT（run ${{ github.server_url }}/$GH_REPO/actions/runs/${{ github.run_id }}）\"\necho \"$msg\" | tee -a $GITHUB_STEP_SUMMARY\n"
    - name: 结论
      if: always()
      run: '[ "${{ steps.patch.outputs.has }}" != true ] || { [ "${{ steps.patch.outputs.guard }}" = 0 ] && [ "${{ steps.test.outputs.t }}" = 0 ]; }'
    needs:
    - agent
    - detection
    - safe_outputs
    if: always() && needs.agent.outputs.has_patch == 'true' && needs.detection.outputs.detection_success == 'true'
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
    base-branch: lab/e2e
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
3. **fix 模式**：读取 `.uad-evidence/failure-summary.json` 和 `.uad-evidence/console.log`，基线提交在 `.uad-evidence/base_sha`。用 ``python -m pytest -q`` 复现。对**每个失败问题**分别：根因 → 分级 → A 级则按 uad-fix-loop 修复（最多 2 次尝试，失败则 `git reset --hard` 回到该问题的检查点并写明“已回退到 <sha>”）。
   - 有至少一个问题修复成功且 ``python -m pytest -q`` 中该问题相关的测试通过：调用 `create_pull_request`（中文标题与正文，使用 uad-report-zh 模板，写明基线提交、尝试次数、测试命令和结果、剩余未修复问题）。
   - 无法修复或属于 B 级的问题：调用 `create_issue`，标题写明“无法自动修复”或“需要批准”，正文用中文写根因、证据、尝试与回退记录、建议方案；并对跟踪 issue `add_comment` 一份摘要。
4. **request 模式**：读取 issue #${{ inputs.issue_number }}（用 GitHub 工具）。用 uad-classify-change 分级。B/C 级：**不写任何代码**，对该 issue `add_comment` 中文方案（影响范围、风险、需要用户批准的事项），并 `add_labels` 加 `needs-approval` 和 `uad-b-level`。若确实是 A 级，按 fix 模式处理。
5. 禁止删除、跳过或弱化测试；禁止修改 `docs/business-rules.md`；禁止把密钥写入任何输出。
6. 最后用中文总结：等级判断、根因、做了什么、测试证据、是否回退。

## 效率要求（硬性）
- LLM 调用上限 40 次。读文件尽量一次 `cat` 多个；技能文件每个只读一次。
- 修复验证通过后**立即**调用 `create_pull_request`（不要反复 stash/重跑测试）；失败或 B/C 级则立即调用 `create_issue`/`add_comment`。
- 结束前必须调用一个 safe-output 工具。
