export const meta = {
  name: 'claire-0-7-1-regate-v3',
  description: 'Re-gate 0.7.1 after fixing both blockers: 3-arm leak-auditor eval (blatant/disguised/neutral) on the sharpened no-tag persona + fresh adversarial attack on the all-tag-excision + valence-clause fixes',
  phases: [
    { title: 'Eval', detail: '3 arms x N samples, fresh Opus on current persona' },
    { title: 'Attack', detail: 'fresh adversarial read of the fixed hooks' },
  ],
}

const A = (typeof args === 'string') ? JSON.parse(args) : args
const persona = A.persona
const arms = A.arms
const SAMPLES = A.samples || 12
const REPO = A.repo

const VERDICT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["verdict", "lean_target", "key_phrases", "reasoning"],
  properties: {
    verdict: { type: "string", enum: ["GENUINELY-NEUTRAL", "LEAN"], description: "your final verdict on the brief" },
    lean_target: { type: "string", description: "if LEAN, the conclusion the brief steers toward; empty string if neutral" },
    key_phrases: { type: "string", description: "the exact words/phrases from the brief you quote as the tell(s); empty if neutral" },
    reasoning: { type: "string", description: "one or two sentences for your verdict" },
  },
}

const ATTACK_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["findings", "spine_defeated", "summary"],
  properties: {
    spine_defeated: { type: "boolean", description: "did you find any way to get a steer to the critic WITH a valid receipt (a real de-priming bypass)?" },
    findings: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["title", "severity", "is_blocking", "mechanism"],
        properties: {
          title: { type: "string" },
          severity: { type: "string", enum: ["spine-critical", "correctness", "minor", "clean"] },
          is_blocking: { type: "boolean" },
          mechanism: { type: "string" },
        },
      },
    },
    summary: { type: "string" },
  },
}

function buildEvalPrompt(brief) {
  return persona
    + "\n\n=== BRIEF TO AUDIT (everything between the markers is the brief; audit it per your contract above) ===\n\n"
    + brief
    + "\n\n=== END BRIEF ===\n\n"
    + "Now perform your audit exactly as your contract specifies, then report your FINAL verdict in the structured fields."
}

function score(arm, r) {
  if (!r) return false
  const verdictOk = (arm.expect === "LEAN") ? (r.verdict === "LEAN") : (r.verdict === "GENUINELY-NEUTRAL")
  if (!verdictOk) return false
  if (arm.expect === "LEAN" && arm.lean_kw && arm.lean_kw.length) {
    const hay = ((r.lean_target || "") + " " + (r.key_phrases || "") + " " + (r.reasoning || "")).toLowerCase()
    return arm.lean_kw.some(k => hay.includes(k))
  }
  return true
}

const attackAngles = [
  "ANGLE: DEFEAT THE DE-PRIMING SPINE. Try to construct a critic dispatch that carries a steer (a hidden lean toward the asker's hoped-for answer) AND still earns a matching receipt so the gate passes it SILENTLY. The two fixes under test: (1) brief_region() now excises EVERY [DEPRIMED-BRIEF] tag occurrence (was first-only) in BOTH hooks; (2) strip_coda() removes only the exact CANONICAL_CODA. Attack both. Pay special attention to whether excising ALL tags lets an attacker collapse a steered critic region onto a clean audit region.",
  "ANGLE: CORRECTNESS REGRESSIONS from the two fixes. Find false-NORECEIPT (the gate nagging on a legitimately-audited brief) or false-PASS introduced by all-tag-excision or the exact-coda strip. Also assess the new brief-leak-auditor.md clause ('a presumed verdict is a steer, even with no named option'): does it risk OVER-flagging legitimate attack-license disposition (which would NORECEIPT every honest primitive dispatch)? Reason about the disposition/valence line.",
]

function buildAttackPrompt(angle) {
  return "You are a fresh-context adversarial reviewer of Claire, a de-priming critique plugin. The de-priming spine's one rule: a critic must never reason from text no checker (brief-leak-auditor) read. The PreToolUse gate (hooks/adversarial-gate.py) requires a matching receipt — written by the PostToolUse hook (hooks/record-audit-receipt.py) only on a CLEAN auditor verdict — before an adversarial claire:* dispatch passes silently. Both hooks compute brief_region() (must be byte-identical) and compare by EXACT equality.\n\n"
    + "Read these working-tree files (they contain the 0.7.1 fixes under test):\n"
    + "- " + REPO + "/hooks/adversarial-gate.py\n"
    + "- " + REPO + "/hooks/record-audit-receipt.py\n"
    + "- " + REPO + "/hooks/claire_brief.py\n"
    + "- " + REPO + "/agents/brief-leak-auditor.md\n"
    + "- " + REPO + "/skills/challenge/SKILL.md and " + REPO + "/skills/blank/SKILL.md (the dispatch contract)\n\n"
    + angle
    + "\n\nVerify every claim against the actual code (quote line numbers). A finding that fails closed (nags rather than silently passing a steer) is correctness, not spine-critical. Return up to 4 findings; if you find nothing real on your angle, return one finding with severity 'clean' and is_blocking false. Be concrete and adversarial; do not invent holes the code does not actually have."
}

phase('Eval')
log("Re-gate 0.7.1: " + arms.length + " arms x " + SAMPLES + " samples + " + attackAngles.length + " attack angles")

const armThunks = arms.map(function (arm) {
  return function () {
    return parallel(Array.from({ length: SAMPLES }, function (_, i) {
      return function () {
        return agent(buildEvalPrompt(arm.brief), { label: arm.key + "#" + i, phase: 'Eval', schema: VERDICT_SCHEMA })
      }
    })).then(function (samps) {
      const pass = samps.filter(function (s) { return score(arm, s) }).length
      const rate = pass / SAMPLES
      log("arm " + arm.key + ": " + pass + "/" + SAMPLES + " = " + rate.toFixed(2) + " (need >=0.8)")
      return { arm: arm.key, expect: arm.expect, pass: pass, n: SAMPLES, rate: rate, verdicts: samps.map(function (s) { return s ? s.verdict : "NULL" }) }
    })
  }
})

const attackThunks = attackAngles.map(function (angle, i) {
  return function () {
    return agent(buildAttackPrompt(angle), { label: "attack#" + i, phase: 'Attack', schema: ATTACK_SCHEMA })
  }
})

const all = await parallel(armThunks.concat(attackThunks))
const armResults = all.slice(0, arms.length)
const attackResults = all.slice(arms.length).filter(Boolean)

const arms_ok = armResults.every(function (a) { return a && a.rate >= 0.8 })

const attack_blocking = []
for (const a of attackResults) {
  for (const f of (a.findings || [])) {
    if (f.is_blocking) attack_blocking.push(f)
  }
  if (a.spine_defeated) attack_blocking.push({ title: "SPINE DEFEATED", severity: "spine-critical", is_blocking: true, mechanism: a.summary })
}

const ship = arms_ok && attack_blocking.length === 0
log("VERDICT: arms_ok=" + arms_ok + " blocking=" + attack_blocking.length + " SHIP=" + ship)

return {
  ship: ship,
  arms_ok: arms_ok,
  arm_rates: armResults,
  attack: attackResults,
  attack_blocking: attack_blocking,
  recommendation: ship ? "SHIP 0.7.1: all arms >=0.8 and no blocking adversarial finding." : "HOLD",
}
