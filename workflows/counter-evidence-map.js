export const meta = {
  name: 'counter-evidence-map',
  description: 'Given a claimed conclusion and a body of evidence or literature, systematically identifies evidence that actively disconfirms the conclusion — not just weak support, but genuine empirical or logical counter-evidence that, if accepted, makes the conclusion less credible or false. Returns a ranked map of counter-evidence by severity, with adversarial annotation distinguishing genuine disconfirmation from false disconfirmations (strawmen, scope mismatches, methodology flaws). Distinct from assumption-stress-test (which flips named assumptions, not finds disconfirmation in evidence), adversarial-review (which attacks a plan, not a claim from within evidence), and differential-diagnosis (which eliminates hypotheses via cross-examination).',
  whenToUse: 'When you have a stated conclusion and one or more source texts, and you want to know what evidence in those sources cuts against the conclusion rather than what supports it. The conclusion should be a testable claim with a stated scope. Pass source_texts as an array of {label, text} objects. Optional stated_scope narrows the domain of applicability the conclusion is asserted for — workers will flag when counter-evidence applies within vs. outside that scope. Before the fan-out, a fidelity guard validates that the extracted testable claim did not soften or scope-shift the input conclusion; if it did, the original conclusion text is used downstream, and a conclusion_fidelity object in the return reports what happened.',
  phases: [
    { title: 'Extract conclusion', detail: 'Haiku extracts the conclusion as a precise testable claim and captures any stated scope, self-checking that the restatement did not soften or scope-shift the input; a fidelity guard reverts to the verbatim input conclusion if drift was flagged, so every downstream worker hunts against the true target' },
    { title: 'Hunt counter-evidence', detail: 'Sonnet workers in parallel — one per source — search each source for passages that directly or indirectly contradict the conclusion, reduce its probability, or establish conditions under which it fails' },
    { title: 'Annotate', detail: 'Adversarial Sonnet annotators in parallel — one per source — check whether each piece of counter-evidence genuinely contradicts the conclusion or is a false disconfirmation (strawman, scope mismatch, methodology flaw)' },
    { title: 'Synthesise map', detail: 'Opus receives all counter-evidence with annotations, builds the counter-evidence registry ranked by severity, names the most threatening finding, characterises the dominant disconfirmation pattern, and assesses whether the conclusion survives' }
  ]
}

// args: {
//   conclusion: required — string; the claimed conclusion to map counter-evidence against
//   source_texts: required — array of {label: string, text: string}
//   stated_scope?: string — optional; the domain, population, or conditions the conclusion is asserted for
//   context?: string — optional domain background
// }

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const conclusion = _args.conclusion || ''
const sourceTexts = _args.source_texts
const statedScope = _args.stated_scope || null
const context = _args.context || null

if (!conclusion || conclusion.length < 10 || !sourceTexts || !sourceTexts.length) {
  log('Missing required args: conclusion (string) and source_texts (array of {label, text})')
  return { error: 'missing_args', required: 'conclusion and source_texts' }
}

const contextBlock = context ? `\n\nDOMAIN CONTEXT: ${context}` : ''
const scopeBlock = statedScope ? `\n\nSTATED SCOPE: ${statedScope}` : ''

// ── Schemas ────────────────────────────────────────────────────────────────────

const CONCLUSION_SCHEMA = {
  type: 'object',
  required: ['testable_claim', 'implied_scope'],
  properties: {
    testable_claim: {
      type: 'string',
      description: 'The conclusion restated as a precise, testable claim — what would have to be true for the conclusion to hold? One sentence.'
    },
    implied_scope: {
      type: 'string',
      description: 'The domain, population, or conditions the conclusion is implicitly asserted for — drawn from the conclusion text and stated_scope if provided. One sentence.'
    },
    key_empirical_assumptions: {
      type: 'array',
      items: { type: 'string' },
      description: 'Up to three empirical assumptions the conclusion rests on — these help workers identify mechanism-failure counter-evidence.'
    },
    fidelity_ok: {
      type: 'boolean',
      description: 'TRUE only if your testable_claim preserves the input conclusion exactly in strength and scope — no hedging words added (e.g. "may", "in some cases", "tends to"), no quantifier weakened (all→most, always→often), no domain narrowed or broadened. FALSE if your restatement softened the assertion or shifted its scope in any way. When in doubt, return FALSE.'
    },
    fidelity_note: {
      type: 'string',
      description: 'If fidelity_ok is FALSE, one sentence naming exactly what changed between the input conclusion and your restatement (which word softened, which scope shifted). Empty string if fidelity_ok is TRUE.'
    }
  }
}

const COUNTER_PASSAGE_SCHEMA = {
  type: 'object',
  required: ['passage', 'counter_type', 'severity', 'reasoning'],
  properties: {
    passage: {
      type: 'string',
      description: 'Verbatim passage from the source.'
    },
    counter_type: {
      type: 'string',
      enum: ['direct_contradiction', 'scope_violation', 'mechanism_failure', 'confounding_evidence', 'null_result'],
      description: 'direct_contradiction: passage asserts the opposite of the conclusion. scope_violation: passage shows the conclusion does not hold in a relevant domain or population. mechanism_failure: passage shows a mechanism the conclusion relies on does not operate as assumed. confounding_evidence: passage identifies a factor that could explain the phenomenon without the conclusion being true. null_result: passage reports that no effect or relationship was found where the conclusion would predict one.'
    },
    severity: {
      type: 'integer',
      minimum: 1,
      maximum: 3,
      description: '3: if accepted, makes the conclusion false or very unlikely. 2: significantly reduces the conclusion\'s credibility or narrows its scope substantially. 1: weakens the conclusion at the margins — the conclusion could still hold with some qualification.'
    },
    reasoning: {
      type: 'string',
      description: 'Two sentences: (1) how this passage contradicts or undermines the conclusion; (2) what specific aspect of the conclusion it challenges.'
    }
  }
}

const WORKER_SCHEMA = {
  type: 'object',
  required: ['source_label', 'counter_evidence_passages', 'has_supporting_evidence', 'net_contribution'],
  properties: {
    source_label: { type: 'string' },
    counter_evidence_passages: {
      type: 'array',
      items: COUNTER_PASSAGE_SCHEMA,
      description: 'All passages found that bear against the conclusion. Empty array if none found.'
    },
    has_supporting_evidence: {
      type: 'boolean',
      description: 'True if this source also contains passages that support the conclusion.'
    },
    net_contribution: {
      type: 'string',
      enum: ['disconfirming', 'mixed', 'supporting', 'neutral'],
      description: 'Overall evidential direction of this source with respect to the conclusion.'
    }
  }
}

const PASSAGE_VERDICT_SCHEMA = {
  type: 'object',
  required: ['passage_index', 'annotation_verdict', 'annotation_note'],
  properties: {
    passage_index: {
      type: 'integer',
      description: 'The 0-based index of the passage in the numbered list provided — copy it exactly. This is how your verdict is matched back to the passage; do NOT renumber.'
    },
    annotation_verdict: {
      type: 'string',
      enum: ['genuine', 'false_disconfirmation', 'contested'],
      description: 'genuine: this passage genuinely counter-evidences the conclusion as stated. false_disconfirmation: the passage does not actually contradict the conclusion when properly understood. contested: reasonable interpretive disagreement — could be genuine or false disconfirmation depending on how the conclusion is read.'
    },
    false_disconfirmation_type: {
      type: ['string', 'null'],
      enum: ['strawman', 'scope_mismatch', 'methodology_flaw', 'conflation', null],
      description: 'strawman: addresses a weaker or different claim than the conclusion. scope_mismatch: passage applies to a domain outside the conclusion\'s scope. methodology_flaw: the study design is flawed in ways that undermine the counter-evidence. conflation: confuses correlation/causation or two distinct phenomena. Null if annotation_verdict is genuine.'
    },
    annotation_note: {
      type: 'string',
      description: 'Two sentences explaining why the verdict is genuine or false — specific to this passage and conclusion.'
    }
  }
}

const ANNOTATOR_SCHEMA = {
  type: 'object',
  required: ['source_label', 'passage_verdicts'],
  properties: {
    source_label: { type: 'string' },
    passage_verdicts: {
      type: 'array',
      items: PASSAGE_VERDICT_SCHEMA
    }
  }
}

const REGISTRY_ENTRY_SCHEMA = {
  type: 'object',
  required: ['source_label', 'passage', 'counter_type', 'severity', 'reasoning', 'annotation_verdict'],
  properties: {
    source_label: { type: 'string' },
    passage: { type: 'string' },
    counter_type: { type: 'string' },
    severity: { type: 'integer', minimum: 1, maximum: 3 },
    reasoning: { type: 'string' },
    annotation_verdict: { type: 'string', enum: ['genuine', 'false_disconfirmation', 'contested'] },
    false_disconfirmation_type: { type: ['string', 'null'] },
    annotation_note: { type: ['string', 'null'] }
  }
}

const MAP_SCHEMA = {
  type: 'object',
  required: ['counter_evidence_registry', 'dominant_disconfirmation_pattern', 'most_threatening_finding', 'conclusion_survivability', 'false_disconfirmation_count', 'synthesis_note', 'extraction_integrity_flag', 'evidence_grounding'],
  properties: {
    counter_evidence_registry: {
      type: 'array',
      items: REGISTRY_ENTRY_SCHEMA,
      description: 'All genuine and contested counter-evidence passages, ranked by severity (3 first). False disconfirmations excluded from the registry body but counted in synthesis_note.'
    },
    dominant_disconfirmation_pattern: {
      type: 'string',
      description: 'One sentence: what type of counter-evidence is most prevalent — direct contradictions, scope violations, mechanism failures, confounds, or null results?'
    },
    most_threatening_finding: {
      type: ['string', 'null'],
      description: 'One to two sentences: the single piece of evidence that, if accepted, does the most damage to the conclusion — and why. Null if no genuine counter-evidence was found.'
    },
    conclusion_survivability: {
      type: 'object',
      required: ['survives', 'confidence', 'qualifying_conditions'],
      properties: {
        survives: {
          type: 'boolean',
          description: 'True if the conclusion plausibly holds given the counter-evidence found; false if one or more severity-3 genuine findings make it untenable.'
        },
        confidence: {
          type: 'string',
          enum: ['high', 'medium', 'low'],
          description: 'How confident is this survivability assessment?'
        },
        qualifying_conditions: {
          type: 'array',
          items: { type: 'string' },
          description: 'Scope conditions under which the conclusion survives despite the counter-evidence — e.g. "holds only when X"; empty if survives=false.'
        }
      }
    },
    false_disconfirmation_count: {
      type: 'integer',
      description: 'Count of passages initially identified as counter-evidence but annotated as false disconfirmations.'
    },
    synthesis_note: {
      type: 'string',
      description: 'Two to three sentences summarising what the counter-evidence map reveals about the conclusion\'s evidentiary standing.'
    },
    extraction_integrity_flag: {
      type: 'array',
      items: { type: 'string' },
      description: 'List any passages where the worker verdict or annotator verdict seems poorly calibrated. Empty array [] if all verdicts are well-grounded.'
    },
    evidence_grounding: {
      type: 'string',
      enum: ['evidenced', 'mixed', 'prior-derived'],
      description: 'evidenced: counter-evidence is grounded in direct passages from the submitted sources. mixed: some passage-grounded, some inferential. prior-derived: workers largely reasoned from domain knowledge rather than submitted source content.'
    }
  }
}

// ── Stage 0: Haiku — extract precise testable claim ───────────────────────────

phase('Extract conclusion')
log('Extracting testable conclusion form...')

const conclusionExtraction = await agent(
  `You are executing as a subagent with a defined brief. Skip: AskUserQuestion, EnterPlanMode, spawn_task. Return structured output only.

TASK: Extract the following conclusion as a precise testable claim — WITHOUT softening it or shifting its scope. The whole analysis downstream hunts counter-evidence against your restatement, so if you weaken the claim or narrow its domain, every later step chases the wrong target.

CONCLUSION: "${conclusion}"${scopeBlock}${contextBlock}

1. Restate as a testable_claim: one sentence, precise and falsifiable. Preserve the input conclusion's strength and scope EXACTLY — do not add hedges ("may", "tends to", "in some cases"), do not weaken quantifiers (all→most, always→often), do not narrow or broaden the domain. Make it testable by sharpening wording, never by softening the assertion.
2. Name the implied_scope: the domain, population, or conditions it is asserted for.
3. List up to three key empirical assumptions the conclusion rests on — these help identify mechanism-failure counter-evidence.
4. Self-check fidelity: set fidelity_ok TRUE only if your testable_claim preserves the input's strength and scope exactly; FALSE if anything softened or shifted, with a one-sentence fidelity_note naming what changed. When in doubt, return FALSE.`,
  { model: 'claude-haiku-4-5-20251001', schema: CONCLUSION_SCHEMA }
)

const testableClaim = (conclusionExtraction && conclusionExtraction.testable_claim)
  ? conclusionExtraction.testable_claim
  : conclusion

const impliedScope = (conclusionExtraction && conclusionExtraction.implied_scope)
  ? conclusionExtraction.implied_scope
  : (statedScope || 'not specified')

const keyAssumptions = (conclusionExtraction && conclusionExtraction.key_empirical_assumptions)
  ? conclusionExtraction.key_empirical_assumptions
  : []

const assumptionsBlock = keyAssumptions.length
  ? `\n\nKEY EMPIRICAL ASSUMPTIONS THE CONCLUSION RESTS ON:\n${keyAssumptions.map((a, i) => `${i + 1}. ${a}`).join('\n')}`
  : ''

// ── Fidelity guard: the restated claim must not soften or scope-shift the input ─
// If the extractor flagged drift (or no extraction came back), fall back to the
// original conclusion text so downstream workers hunt against the true target,
// not a weakened paraphrase. Recorded in the return as conclusion_fidelity.
const extractionReturned = !!(conclusionExtraction && conclusionExtraction.testable_claim)
const extractorFlaggedDrift = !!(conclusionExtraction && conclusionExtraction.fidelity_ok === false)
const fidelityNote = (conclusionExtraction && conclusionExtraction.fidelity_note) || ''

let huntClaim = testableClaim
let fidelityStatus
if (!extractionReturned) {
  // Extraction failed entirely — testableClaim already equals the original conclusion.
  fidelityStatus = 'extraction_failed_used_original'
} else if (extractorFlaggedDrift) {
  // Extractor admitted softening/scope-shift — revert to the verbatim input.
  huntClaim = conclusion
  fidelityStatus = 'drift_flagged_reverted_to_original'
  log(`Conclusion fidelity check FAILED — restated claim drifted from input; reverting to original. ${fidelityNote ? 'Reason: ' + fidelityNote : ''}`)
} else {
  fidelityStatus = 'preserved'
}

const conclusionFidelity = {
  status: fidelityStatus,
  used_claim: huntClaim,
  restated_claim: extractionReturned ? testableClaim : null,
  original_conclusion: conclusion,
  note: fidelityNote,
}

// ── Stage 1: Sonnet workers — one per source ──────────────────────────────────

phase('Hunt counter-evidence')
log(`Dispatching ${sourceTexts.length} counter-evidence hunters...`)

const workerResults = await parallel(sourceTexts.map(source => () =>
  agent(
    `You are executing as a subagent with a defined brief. Skip: AskUserQuestion, EnterPlanMode, spawn_task. Return structured output only.

TASK: Hunt for counter-evidence. Search this source for passages that directly or indirectly contradict the conclusion, reduce its probability, or establish conditions under which it fails.

CONCLUSION: "${huntClaim}"
SCOPE: ${impliedScope}${assumptionsBlock}${contextBlock}

SOURCE (${source.label}):
${source.text}

INSTRUCTIONS:
1. Read the source carefully looking for passages that bear AGAINST the conclusion.
2. For each counter-evidence passage found, return it verbatim and classify:
   - counter_type: direct_contradiction | scope_violation | mechanism_failure | confounding_evidence | null_result
   - severity 1-3: 3 = makes conclusion false if accepted; 2 = significantly weakens it; 1 = marginal weakening
   - reasoning: (1) how it contradicts the conclusion; (2) what aspect it challenges
3. Note whether the source also contains supporting evidence (has_supporting_evidence).
4. Assess net_contribution: disconfirming | mixed | supporting | neutral.

Do not hunt for passages that support the conclusion — only counter-evidence. Return an empty array if no counter-evidence is found.`,
    { model: 'claude-sonnet-4-6', schema: WORKER_SCHEMA }
  )
))

const cleanWorkers = workerResults.filter(Boolean)
if (!cleanWorkers.length) {
  return { error: 'worker_stage_failed', stage: 'counter_evidence_hunt' }
}

// Filter to sources that found something
const sourcesWithFindings = cleanWorkers.filter(w => w.counter_evidence_passages && w.counter_evidence_passages.length > 0)
log(`Found counter-evidence in ${sourcesWithFindings.length} of ${sourceTexts.length} sources`)

// ── Stage 2: Sonnet adversarial annotators — one per source with findings ─────

phase('Annotate')

let annotatorResults = []
if (sourcesWithFindings.length > 0) {
  log(`Dispatching ${sourcesWithFindings.length} false-disconfirmation checkers...`)

  annotatorResults = await parallel(sourcesWithFindings.map(worker => () => {
    const sourceText = sourceTexts.find(s => s.label === worker.source_label)
    return agent(
      `You are executing as a subagent with a defined brief. Skip: AskUserQuestion, EnterPlanMode, spawn_task. Return structured output only.

TASK: Check for false disconfirmations. A worker has identified passages in this source as counter-evidence against a conclusion. Your job is to challenge that classification — are these passages genuinely disconfirming, or are they false disconfirmations?

CONCLUSION: "${huntClaim}"
SCOPE: ${impliedScope}${contextBlock}

PASSAGES IDENTIFIED AS COUNTER-EVIDENCE (numbered — return the passage_index [N] for each verdict):
${worker.counter_evidence_passages.map((p, i) => `[${i}] (${p.counter_type}, severity ${p.severity}): ${p.passage}`).join('\n\n')}

${sourceText ? `ORIGINAL SOURCE (${worker.source_label}):\n${sourceText.text}` : ''}

Return exactly one verdict per passage above — use its passage_index (the [N] number, 0-based). Verdicts:
- genuine: the passage genuinely counter-evidences the conclusion as stated
- false_disconfirmation: it does not actually contradict the conclusion when properly understood:
  - strawman: addresses a weaker or different claim
  - scope_mismatch: applies to a domain outside the conclusion's stated scope
  - methodology_flaw: study design is flawed in ways that undermine the finding
  - conflation: confuses correlation/causation or distinct phenomena
- contested: reasonable interpretive disagreement

Be adversarial — your job is to FIND false disconfirmations, not confirm the worker's findings. But be honest: if a passage genuinely contradicts the conclusion, say so. If you have tool access and the passage cites a specific named source, verify the citation exists before accepting it as genuine counter-evidence.`,
      { model: 'claude-sonnet-4-6', schema: ANNOTATOR_SCHEMA }
    )
  }))
}

const cleanAnnotators = annotatorResults.filter(Boolean)

// Build annotation lookup: source_label → passage_verdicts
const annotationMap = {}
for (const ann of cleanAnnotators) {
  if (ann && ann.source_label) {
    annotationMap[ann.source_label] = ann.passage_verdicts || []
  }
}

// Enrich worker findings with annotation verdicts
const enrichedFindings = cleanWorkers.map(worker => {
  const annotations = annotationMap[worker.source_label] || []
  return {
    ...worker,
    counter_evidence_passages: (worker.counter_evidence_passages || []).map((p, idx) => {
      const matchingAnnotation = annotations.find(a => a.passage_index === idx)
      return {
        ...p,
        annotation_verdict: matchingAnnotation ? matchingAnnotation.annotation_verdict : 'genuine',
        false_disconfirmation_type: matchingAnnotation ? matchingAnnotation.false_disconfirmation_type : null,
        annotation_note: matchingAnnotation
          ? matchingAnnotation.annotation_note
          : 'NOT ANNOTATED — no verdict returned for this passage index; treated as genuine pending review. Flag in extraction_integrity_flag if this passage is load-bearing.',
      }
    })
  }
})

// ── Stage 3: Opus — counter-evidence map ──────────────────────────────────────

phase('Synthesise map')
log('Synthesising counter-evidence map...')

const synthesisPrompt =
  'You are executing as a subagent with a defined brief. Skip: AskUserQuestion, EnterPlanMode, spawn_task. Return structured output only.\n\n' +
  'REQUIRED FIELDS IN YOUR STRUCTURED RESPONSE (all must be populated before submitting):\n' +
  '  extraction_integrity_flag — array of strings; empty array [] if all verdicts are well-grounded.\n' +
  '  evidence_grounding — one of: evidenced | mixed | prior-derived.\n\n' +
  'TASK: Synthesise counter-evidence findings into a ranked map.\n\n' +
  `CONCLUSION: "${huntClaim}"\nSCOPE: ${impliedScope}${contextBlock}\n\n` +
  'ENRICHED WORKER FINDINGS (with annotation verdicts):\n' +
  JSON.stringify(enrichedFindings, null, 2) + '\n\n' +
  'SYNTHESIS TASKS (execute in order):\n\n' +
  '1. BUILD COUNTER-EVIDENCE REGISTRY. Include only genuine and contested passages (exclude false_disconfirmation). For each entry: source_label, passage, counter_type, severity, reasoning, annotation_verdict, false_disconfirmation_type, annotation_note. Sort by severity descending (3 first).\n\n' +
  '2. DOMINANT DISCONFIRMATION PATTERN. One sentence: what type of counter-evidence dominates — direct contradictions, scope violations, mechanism failures, confounds, or null results?\n\n' +
  '3. MOST THREATENING FINDING. One to two sentences: the single passage that does the most damage to the conclusion if accepted, and why. Null if registry is empty.\n\n' +
  '4. CONCLUSION SURVIVABILITY. Does the conclusion survive the counter-evidence? survives (bool), confidence (high/medium/low), qualifying_conditions (scope restrictions under which it holds despite the evidence). Rules by annotation_verdict: a severity-3 finding with annotation_verdict "genuine" forces survives=false. A severity-3 finding with annotation_verdict "contested" does NOT by itself force survives=false — instead cap confidence at "medium" and name the contested finding in qualifying_conditions (the conclusion survives only if the contested reading resolves in its favour). Passages annotated "false_disconfirmation" never affect survivability and are excluded from this judgment.\n\n' +
  '5. FALSE DISCONFIRMATION COUNT. Count of passages annotated as false_disconfirmation across all sources.\n\n' +
  '6. SYNTHESIS NOTE. Two to three sentences on what the counter-evidence map reveals about the conclusion\'s evidentiary standing.\n\n' +
  '7. EXTRACTION_INTEGRITY_FLAG. List any passages where worker or annotator calibration seems off. Empty array [] if all verdicts are well-grounded.\n\n' +
  '8. EVIDENCE_GROUNDING. "evidenced" if counter-evidence is grounded in direct source passages; "mixed" if some passage-grounded and some inferential; "prior-derived" if workers largely reasoned from domain knowledge.'

const synthesis = await agent(synthesisPrompt, { model: 'claude-opus-4-8', schema: MAP_SCHEMA })

if (!synthesis) {
  return { error: 'synthesis_failed', enrichedFindings }
}

return {
  ...synthesis,
  conclusion: huntClaim,
  scope: impliedScope,
  source_count: sourceTexts.length,
  conclusion_fidelity: conclusionFidelity,
}
