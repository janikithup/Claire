export const meta = {
  name: 'adversarial-review',
  description: 'Minimum-context failure-mode attacker — receives a plan or decision and returns up to three concrete failure modes, classified structural or minor. Optionally accepts attack_dimensions to run one attacker per named dimension (legal / empirical / implementation, etc.) so multi-component plans get per-dimension scrutiny instead of one flattened attack surface; results merge into the same return shape.',
  whenToUse: 'Any time you need a quick adversarial check on a plan, decision, proposed approach, or deliverable before committing. Pass the plan text and any fixed constraints. The attacker receives no producer reasoning — intentionally starved of context so it finds genuine failure modes, not polite concerns. Use before finalising a recommendation, before sending a deliverable, or as a standalone sense-check. For a multi-component plan whose failure modes split across distinct axes, pass attack_dimensions as an array of labels (e.g. ["legal", "empirical", "implementation"]) — one attacker runs per dimension with its own finding cap, then all findings merge.',
  phases: [
    { title: 'Attack', detail: 'Sonnet attacker challenges the plan with minimum context (one attacker per dimension when attack_dimensions is set)' }
  ]
}

// args: { plan, constraints?, focus?, attack_dimensions? }
// plan: the plan, decision, or text to attack
// constraints: optional array of strings — fixed constraints that cannot be violated
// focus: optional string — specific failure dimension to focus on (default: general)
// attack_dimensions: optional array of strings — dimension labels (e.g. legal / empirical / implementation).
//   When present, one attacker runs per dimension, each capped at 3 findings, and the results merge into
//   failure_modes (each tagged with its dimension). When absent, behavior is the current single attacker.

// args may arrive as: an object {plan,...}; a JSON-stringified object; or — the friendly,
// commonly-advertised default — the bare plan text as a string. Tolerate all three: a string
// that is not a JSON object is taken as the plan itself, so a prose brief never crashes the run.
let _args = {}
if (typeof args === 'string') {
  try {
    const parsed = JSON.parse(args)
    _args = (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : { plan: args }
  } catch (e) {
    _args = { plan: args }
  }
} else if (args && typeof args === 'object') {
  _args = args
}
const plan = _args.plan || ''
const constraints = _args.constraints || []
const focus = _args.focus || null
const attackDimensions = Array.isArray(_args.attack_dimensions)
  ? _args.attack_dimensions.filter(d => typeof d === 'string' && d.trim())
  : []

if (!plan) {
  log('No plan provided — pass args.plan as the text to attack')
  return { failure_modes: [] }
}

const FAILMODES_SCHEMA = {
  type: 'object',
  required: ['failure_modes'],
  properties: {
    failure_modes: {
      type: 'array',
      maxItems: 3,
      items: {
        type: 'object',
        required: ['description', 'severity'],
        properties: {
          description: {
            type: 'string',
            description: 'What specifically breaks and how — name the mechanism, not a vague concern'
          },
          severity: {
            type: 'string',
            enum: ['structural', 'minor'],
            description: 'structural = plan needs reshaping to survive this; minor = worth noting but not blocking'
          },
          corrective_note: {
            type: 'string',
            description: 'Optional one-sentence corrective suggestion'
          },
          dimension: {
            type: 'string',
            description: 'Optional — the attack dimension this failure mode belongs to (set on merge when attack_dimensions is used)'
          }
        }
      }
    }
  }
}

const constraintBlock = constraints.length > 0
  ? `\n\nFixed constraints (cannot be violated):\n${constraints.map((c, i) => `${i + 1}. ${c}`).join('\n')}`
  : ''

const focusBlock = focus ? `\n\nFocus: ${focus}` : ''

const buildPrompt = (dimensionBlock) =>
  `You are a minimum-context adversarial reviewer. Your job is to find failure modes — not to be constructive, not to praise, not to hedge. Find what breaks.\n\n` +
  `List up to three most likely failure modes of this plan. For each: (1) name what specifically fails and how (mechanism, not vibe); (2) classify as structural (the plan needs reshaping) or minor (notable but not blocking); (3) optionally, one corrective sentence.\n\n` +
  `You have no context beyond what is written below. Do not infer producer intent. Do not give credit for unstated assumptions.\n\n` +
  `Plan:\n${plan}${constraintBlock}${focusBlock}${dimensionBlock}`

phase('Attack')

let modes
if (attackDimensions.length > 0) {
  const results = await parallel(
    attackDimensions.map(dim => () => agent(
      buildPrompt(`\n\nAttack dimension: ${dim}\nConfine your failure modes to this dimension only. Up to three for this dimension.`),
      {
        label: `attacker-${dim}`,
        phase: 'Attack',
        model: 'claude-sonnet-4-6',
        schema: FAILMODES_SCHEMA
      }
    ))
  )
  modes = results.flatMap((r, i) =>
    r ? (r.failure_modes || []).map(m => ({ ...m, dimension: attackDimensions[i] })) : []
  )
} else {
  const result = await agent(
    buildPrompt(''),
    {
      label: 'attacker',
      phase: 'Attack',
      model: 'claude-sonnet-4-6',
      schema: FAILMODES_SCHEMA
    }
  )
  modes = result?.failure_modes || []
}

const structural = modes.filter(m => m.severity === 'structural').length
const minor = modes.filter(m => m.severity === 'minor').length
log(`${modes.length} failure modes: ${structural} structural, ${minor} minor`)

return { failure_modes: modes }
