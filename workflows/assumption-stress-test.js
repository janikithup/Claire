export const meta = {
  name: 'assumption-stress-test',
  description: 'Sensitivity analysis over the assumptions a scenario or argument depends on. Haiku extracts assumptions (typed causal/empirical/normative) and atomic sub-claims; a flip-precision gate validates each; Sonnet workers score every sub-claim under one flipped assumption (shared substrate for commensurable aggregation); Opus synthesises a load-bearing/sensitive/robust/under-resolved ranking with damage-ratios. Returns a sensitivity ranking table, scenario verdict, and full worker arrays for auditability.',
  whenToUse: 'When you need to know which beliefs a scenario or argument depends on most critically — before committing to a plan, before presenting an argument to a skeptical audience, or after a debate-panel returns a major unresolved objection. Pass the scenario text and optionally a list of pre-identified assumptions; if absent, Haiku auto-extracts them. Returns which assumptions are load-bearing (if wrong, the scenario collapses), sensitive (weakens if wrong), robust (stable regardless), or under-resolved (plausible damage but insufficient grounding).',
  phases: [
    { title: 'Extract', detail: 'Haiku extracts assumptions (typed causal/empirical/normative) and sub-claims; flip-precision gate validates single-variable isolation' },
    { title: 'Stress', detail: 'Sonnet workers — one per assumption — score every sub-claim under their counterfactual; returns commensurable sub_claim_scores arrays over a shared substrate' },
    { title: 'Synthesise', detail: 'Opus computes damage_ratios, tiers assumptions (load-bearing/sensitive/robust/under-resolved), runs bounded interaction scan, produces sensitivity ranking + scenario verdict' }
  ]
}

// args: {
//   scenario: string — the scenario, argument, or plan under test
//   assumptions?: Array<{id, label, base_state, flipped_state, type?}> — caller-supplied; if absent, Haiku extracts
//     id: short slug, no spaces
//     label: one-sentence name
//     base_state: world when this holds (one sentence)
//     flipped_state: single-variable negation of base_state
//     type?: 'causal' | 'empirical' | 'normative'
//   sub_claims?: string[] — atomic propositions the argument rests on; if absent, Haiku extracts
//   outcome_anchor?: string — what the scenario is trying to achieve; if absent, Haiku infers
// }

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const scenario = _args.scenario || ''
const callerAssumptions = Array.isArray(_args.assumptions) && _args.assumptions.length > 0 ? _args.assumptions : null
const callerSubClaims = Array.isArray(_args.sub_claims) && _args.sub_claims.length > 0 ? _args.sub_claims : null
const callerOutcomeAnchor = _args.outcome_anchor || null

if (!scenario || scenario.length < 20) {
  log('Missing required args. Pass: args.scenario (string, the argument/plan to stress-test)')
  return { error: 'missing_args' }
}

// ── Schemas ───────────────────────────────────────────────────────────────────

const EXTRACTION_SCHEMA = {
  type: 'object',
  required: ['assumptions', 'sub_claims', 'outcome_anchor'],
  properties: {
    assumptions: {
      type: 'array',
      minItems: 1,
      maxItems: 8,
      items: {
        type: 'object',
        required: ['id', 'label', 'base_state', 'flipped_state', 'type'],
        properties: {
          id: { type: 'string', description: 'Short slug, no spaces, no special characters (e.g. "budget-fixed", "vendor-available")' },
          label: { type: 'string', description: 'One-sentence name of the assumption as-stated' },
          base_state: { type: 'string', description: 'The world when this assumption holds — one sentence' },
          flipped_state: {
            type: 'string',
            description: 'A MINIMAL single-variable negation. Change exactly one thing. "X is not available" not "the context fundamentally changes." If base_state is "the vendor delivers on time", flipped_state is "the vendor does not deliver on time" — not "the vendor obstructs and conditions change."'
          },
          type: {
            type: 'string',
            enum: ['causal', 'empirical', 'normative'],
            description: 'causal: a mechanism claim (X causes Y). empirical: a factual claim about the world. normative: a value or priority claim.'
          }
        }
      },
      description: 'Up to 8 assumptions ranked by apparent centrality (most load-bearing first); truncate at 8. Each is exactly one variable.'
    },
    sub_claims: {
      type: 'array',
      minItems: 2,
      maxItems: 8,
      items: { type: 'string', description: 'One atomic proposition — one sentence, no conjunctions. Must be traceable to the scenario text.' },
      description: '2-8 atomic propositions the scenario rests on. Do not add claims not present in the scenario text.'
    },
    outcome_anchor: {
      type: 'string',
      description: 'What would count as success for this scenario — what the scenario is trying to achieve. One sentence.'
    }
  }
}

const WORKER_SCHEMA = {
  type: 'object',
  required: ['assumption_id', 'sub_claim_scores', 'confidence', 'confidence_reasoning'],
  properties: {
    assumption_id: { type: 'string', description: 'Copy the assumption id exactly as given' },
    sub_claim_scores: {
      type: 'array',
      items: {
        type: 'object',
        required: ['sub_claim_index', 'direction'],
        properties: {
          sub_claim_index: { type: 'number', description: 'Zero-based index into the sub_claims array' },
          direction: {
            type: 'string',
            enum: ['unchanged', 'weakens', 'strengthens', 'collapses', 'reverses'],
            description: 'unchanged: no effect on this sub-claim. weakens: supporting evidence diminishes but claim still holds. strengthens: supporting evidence increases. collapses: sub-claim no longer holds. reverses: sub-claim holds in the opposite direction.'
          },
          note: {
            type: 'string',
            description: 'Required when direction ≠ unchanged. One sentence naming the specific causal mechanism. Anti-self-grading: if this note reads correctly with a different scenario substituted, it is too generic — rewrite it against the scenario text. Empty string when direction = unchanged.'
          }
        }
      },
      description: 'One entry per sub-claim. Score EVERY sub-claim — do not skip any.'
    },
    confidence: {
      type: 'string',
      enum: ['high', 'medium', 'low'],
      description: 'high: the causal chain is clear and supported by the scenario text. medium: plausible but uncertain. low: speculative — the mechanism is not grounded in the scenario text.'
    },
    confidence_reasoning: { type: 'string', description: 'One sentence on why you chose this confidence level' },
    coupling_note: {
      type: 'string',
      description: 'Fire ONLY when you cannot assess your flip without implicitly changing a held-fixed assumption — name which assumption and why. Empty string if clean.'
    }
  }
}

const SYNTHESIS_SCHEMA = {
  type: 'object',
  required: ['headline', 'sensitivity_ranking', 'scenario_verdict'],
  properties: {
    headline: {
      type: 'string',
      description: 'Two sentences: (1) which single assumption, if wrong, most threatens the scenario and why; (2) what the overall sensitivity pattern implies for decision-making.'
    },
    sensitivity_ranking: {
      type: 'array',
      items: {
        type: 'object',
        required: ['assumption_id', 'label', 'tier', 'damage_ratio', 'collapse_count', 'reverse_count', 'confidence', 'provisional', 'provenance'],
        properties: {
          assumption_id: { type: 'string' },
          label: { type: 'string' },
          tier: {
            type: 'string',
            enum: ['load-bearing', 'sensitive', 'robust', 'under-resolved'],
            description: 'load-bearing: damage_ratio ≥ 0.30 OR any reversal, AND confidence high/medium. sensitive: any weakens/strengthens but no collapses/reverses, or below load-bearing ratio. robust: zero sub-claims change direction. under-resolved: high damage_ratio but confidence low — plausible but ungrounded, never promote to load-bearing.'
          },
          damage_ratio: { type: 'number', description: 'Fraction of sub-claims scoring collapses or reverses' },
          collapse_count: { type: 'number' },
          reverse_count: { type: 'number' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          provisional: { type: 'boolean', description: 'True when the worker filed a coupling_note — one-variable guarantee locally compromised' },
          provenance: { type: 'string', description: 'One sentence naming the worker finding that drove this tier' }
        }
      },
      description: 'All assumptions in order: load-bearing → sensitive → robust → under-resolved'
    },
    scenario_verdict: {
      type: 'string',
      enum: ['robust', 'fragile', 'structurally-dependent'],
      description: 'robust: zero load-bearing. fragile: 1-2 load-bearing. structurally-dependent: 3+ load-bearing.'
    },
    interaction_hypotheses: {
      type: 'array',
      maxItems: 2,
      items: {
        type: 'object',
        required: ['assumption_ids', 'hypothesis'],
        properties: {
          assumption_ids: { type: 'array', items: { type: 'string' }, description: 'The two assumption ids involved' },
          hypothesis: { type: 'string', description: 'One sentence on the joint effect inferred from mechanism texts. Mark explicitly as HYPOTHESIS — not a detected emergent effect.' }
        }
      },
      description: 'Up to 2 assumption-pairs flagged as potentially jointly load-bearing. Each is a hypothesis, not a detected fact.'
    },
    hedge: {
      type: 'string',
      description: 'Caveat block: provisional rankings (coupling-noted workers), interaction hypotheses, under-resolved candidates for a follow-up run with a sharper flip, assumptions or sub-claims the extraction may have missed.'
    }
  }
}

// ── Phase 1: Extraction ───────────────────────────────────────────────────────
phase('Extract')

let assumptions, subClaims, outcomeAnchor

if (callerAssumptions && callerSubClaims && callerOutcomeAnchor) {
  assumptions = callerAssumptions
  subClaims = callerSubClaims
  outcomeAnchor = callerOutcomeAnchor
  log('Using fully caller-supplied assumptions, sub-claims, and outcome anchor')
} else {
  const extractPromptParts = [
    `You are extracting assumptions and atomic sub-claims from a scenario for a sensitivity analysis.\n\n`,
    `SCENARIO:\n${scenario}\n\n`,
    callerOutcomeAnchor ? `Outcome anchor (caller-supplied — include verbatim): ${callerOutcomeAnchor}\n\n` : '',
    `EXTRACTION RULES:\n`,
    `1. Identify up to 8 assumptions the scenario depends on. Each is exactly one variable. Rank by centrality; truncate at 8.\n`,
    `2. Each flipped_state: write a MINIMAL single-variable negation. Change exactly one thing. Not "the context changes" but "X is not available."\n`,
    `3. Type each assumption: causal (mechanism), empirical (factual), normative (value/priority).\n`,
    `4. Identify 2-8 atomic sub-claims the scenario rests on. One sentence each, no conjunctions. Traceable to scenario text only.\n`,
    `5. Infer outcome_anchor: what success looks like for this scenario, one sentence.\n`,
    callerAssumptions ? `\nCaller-supplied assumptions (use these — do not re-extract):\n${JSON.stringify(callerAssumptions, null, 2)}\n` : '',
    callerSubClaims ? `\nCaller-supplied sub_claims (use these — do not re-extract):\n${JSON.stringify(callerSubClaims, null, 2)}\n` : ''
  ]

  const extractionResult = await agent(
    extractPromptParts.join(''),
    {
      label: 'extract',
      phase: 'Extract',
      model: 'claude-haiku-4-5-20251001',
      schema: EXTRACTION_SCHEMA
    }
  )

  if (!extractionResult) {
    return { error: 'extraction_failed' }
  }

  assumptions = callerAssumptions || extractionResult.assumptions
  subClaims = callerSubClaims || extractionResult.sub_claims
  outcomeAnchor = callerOutcomeAnchor || extractionResult.outcome_anchor
}

// Flip-precision gate: structural validation
const invalidIds = assumptions
  .filter(a => !a.id || !a.base_state || !a.flipped_state || a.flipped_state.trim() === a.base_state.trim())
  .map(a => a.id || '[missing id]')

if (invalidIds.length > 0) {
  log(`Precision gate dropped ${invalidIds.length} assumptions with missing or identical base/flipped states: ${invalidIds.join(', ')}`)
  assumptions = assumptions.filter(a => a.id && a.base_state && a.flipped_state && a.flipped_state.trim() !== a.base_state.trim())
}

// Dedup IDs
const seenIds = new Set()
assumptions = assumptions.filter(a => {
  if (seenIds.has(a.id)) return false
  seenIds.add(a.id)
  return true
})

if (assumptions.length === 0) {
  return { error: 'no_valid_assumptions', gate_failures: invalidIds }
}

log(`${assumptions.length} assumptions × ${subClaims.length} sub-claims in scope`)
log(`Outcome anchor: ${outcomeAnchor}`)

// ── Phase 2: Sonnet fan-out (one worker per assumption) ───────────────────────
phase('Stress')

const heldFixedLines = (activeId) =>
  assumptions
    .filter(a => a.id !== activeId)
    .map(a => `  - ${a.id} ("${a.label}"): HELD FIXED at "${a.base_state}"`)
    .join('\n')

const subClaimsBlock = subClaims.map((sc, i) => `  ${i}: ${sc}`).join('\n')

const workerResults = await parallel(
  assumptions.map((assumption) => () => agent(
    `You are a sensitivity analyst testing exactly one assumption in a scenario. Your job is to determine how each atomic sub-claim changes when this one assumption is flipped.\n\n` +
    `SCENARIO:\n${scenario}\n\n` +
    `OUTCOME ANCHOR: ${outcomeAnchor}\n\n` +
    `YOUR ACTIVE ASSUMPTION [FLIP THIS ONE]:\n` +
    `  id: ${assumption.id}\n` +
    `  label: ${assumption.label}\n` +
    `  base_state: "${assumption.base_state}"\n` +
    `  flipped_state: "${assumption.flipped_state}"\n` +
    `  type: ${assumption.type || 'unclassified'}\n\n` +
    `HELD-FIXED ASSUMPTIONS (treat as given facts — do not question or vary these):\n` +
    heldFixedLines(assumption.id) + '\n\n' +
    `SHARED SUB-CLAIMS (score EVERY one of these under your counterfactual):\n` +
    subClaimsBlock + '\n\n' +
    `ISOLATION RULE: You test exactly ONE variable. When "${assumption.base_state}" becomes "${assumption.flipped_state}" — what changes? Every other assumption is pinned at its base state. Do not test combinations.\n\n` +
    `SCORING RULES:\n` +
    `1. Score every sub-claim — provide one entry per index (0 to ${subClaims.length - 1}). Do not skip any.\n` +
    `2. direction: unchanged (flip has no effect), weakens (claim still holds but less strongly), strengthens (claim holds more strongly), collapses (claim no longer holds), reverses (claim holds in the opposite direction).\n` +
    `3. For every direction ≠ unchanged: write a note naming the specific causal mechanism grounded in the scenario text. If your note would read correctly with a different scenario substituted in, it is too generic — rewrite it.\n` +
    `4. coupling_note: if you genuinely cannot assess your flip without also changing a held-fixed assumption, name which one and why. Leave empty string if clean.`,
    {
      label: `stress:${assumption.id}`,
      phase: 'Stress',
      model: 'claude-sonnet-4-6',
      schema: WORKER_SCHEMA
    }
  ))
)

const validWorkers = workerResults.filter(Boolean)
log(`${validWorkers.length} of ${assumptions.length} workers returned`)

if (validWorkers.length === 0) {
  return { error: 'all_workers_failed' }
}

// ── Phase 3: Opus synthesis ───────────────────────────────────────────────────
phase('Synthesise')

const synthesis = await agent(
  `You are synthesising a sensitivity analysis over ${validWorkers.length} assumption stress tests.\n\n` +
  `SCENARIO:\n${scenario}\n\n` +
  `OUTCOME ANCHOR: ${outcomeAnchor}\n\n` +
  `ASSUMPTIONS TESTED (${assumptions.length} total):\n${JSON.stringify(assumptions, null, 2)}\n\n` +
  `SHARED SUB-CLAIMS (indexed 0 to ${subClaims.length - 1}):\n${subClaims.map((sc, i) => `${i}: ${sc}`).join('\n')}\n\n` +
  `WORKER RESULTS:\n${JSON.stringify(validWorkers, null, 2)}\n\n` +
  `REQUIRED FIELDS IN YOUR STRUCTURED RESPONSE (populate all before submitting):\n` +
  `  sensitivity_ranking — array, one row per assumption; EVERY row must include provenance (one sentence naming the specific worker finding that justifies the tier) and provisional (boolean — true when the assumption's coupling_note was filed).\n` +
  `  scenario_verdict — one of: robust | fragile | structurally-dependent.\n` +
  `  headline — the two-sentence summary from STEP 6.\n\n` +
  `SYNTHESIS STEPS (execute in order):\n\n` +
  `STEP 1 — NORMALISATION. For each worker, verify the flip genuinely contradicts base_state. Apply a softer test to normative-typed assumptions — a normative assumption cannot be falsified like a factual claim. Flag suspected partial flips in the hedge field.\n\n` +
  `STEP 2 — DAMAGE RATIO. For each assumption: damage_ratio = (sub-claims scored 'collapses' or 'reverses') / ${subClaims.length}. Tiers:\n` +
  `  load-bearing: damage_ratio ≥ 0.30 OR any sub-claim 'reverses', AND confidence high or medium\n` +
  `  sensitive: any sub-claim weakens/strengthens but nothing collapses/reverses, OR below 0.30 and no reversal\n` +
  `  robust: zero sub-claims change direction\n` +
  `  under-resolved: damage_ratio ≥ 0.30 but worker confidence is low — plausible but ungrounded; NEVER promote to load-bearing\n\n` +
  `STEP 3 — CONFIDENCE WEIGHTING. Low-confidence + high-damage → under-resolved (not load-bearing). A provisional assumption (coupling_note filed) → provisional = true in its ranking row.\n\n` +
  `STEP 4 — INTERACTION SCAN (bounded). Flag up to 2 assumption-pairs as potentially jointly load-bearing based ONLY on reading their mechanism notes. Label each pair's hypothesis explicitly as inferred from single-flip texts — not a detected emergent effect.\n\n` +
  `STEP 5 — SCENARIO VERDICT. robust: zero load-bearing. fragile: 1-2 load-bearing. structurally-dependent: 3+ load-bearing.\n\n` +
  `STEP 6 — HEADLINE. Two sentences: (1) the most threatening load-bearing assumption and why; (2) what the sensitivity pattern implies for decision-making.\n\n` +
  `STEP 7 — HEDGE BLOCK. Name: provisional rankings, interaction hypotheses, under-resolved candidates for a follow-up with a sharper flip, assumptions or sub-claims that may be missing from the analysis.`,
  {
    label: 'synthesise',
    phase: 'Synthesise',
    model: 'claude-opus-4-8',
    schema: SYNTHESIS_SCHEMA
  }
)

if (!synthesis) {
  log('Synthesis failed — returning worker results without ranking')
  return {
    error: 'synthesis_failed',
    assumptions,
    sub_claims: subClaims,
    outcome_anchor: outcomeAnchor,
    worker_results: validWorkers
  }
}

const loadBearing = synthesis.sensitivity_ranking?.filter(r => r.tier === 'load-bearing').length || 0
const robust = synthesis.sensitivity_ranking?.filter(r => r.tier === 'robust').length || 0
log(`Verdict: ${synthesis.scenario_verdict} — ${loadBearing} load-bearing, ${robust} robust of ${assumptions.length}`)

return {
  headline: synthesis.headline,
  scenario_verdict: synthesis.scenario_verdict,
  sensitivity_ranking: synthesis.sensitivity_ranking || [],
  interaction_hypotheses: synthesis.interaction_hypotheses || [],
  hedge: synthesis.hedge || '',
  assumptions,
  sub_claims: subClaims,
  outcome_anchor: outcomeAnchor,
  worker_results: validWorkers
}
