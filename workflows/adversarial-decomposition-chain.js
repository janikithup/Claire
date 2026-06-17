export const meta = {
  name: 'adversarial-decomposition-chain',
  description: 'Sequential four-stage role-chain that locates exactly where two defensible readings of the same source material are genuinely incompatible. Stage 1: Sonnet extracts the strongest-case argument for position A as a typed claim list with verbatim anchors and confidence ratings. Stage 2: Sonnet constructs the best steel-man of position B from the same source, isolated from Stage 1. Stage 3: Sonnet receives BOTH claim lists (not the source) and classifies each conflict by type (logical-incompatibility / scope-difference / terminological / normative-priority) and resolvability — the source_anchor and claim type fields are the inter-stage contract that makes this possible without re-reading the source. Stage 4: Opus renders a verdict: most decision-relevant incompatibility, load-bearing classification, and what evidence would resolve it.',
  whenToUse: 'When a single body of source material genuinely supports two defensible but conflicting readings — policy documents, ambiguous empirical findings, contested institutional mandates — and you need to know whether the conflict is resolvable by definition or is a real logical incompatibility requiring new evidence. Returns a conflict classification table and a decision-relevant verdict. Not useful when the readings are already clearly specified as independent arguments; see debate-panel for that case.',
  phases: [
    { title: 'Extract-A', detail: 'Sonnet extracts strongest-case argument for position A from source material as a typed claim list with verbatim anchors' },
    { title: 'Steelman-B', detail: 'Sonnet constructs the best steel-man of position B from the same source — isolated from Stage 1' },
    { title: 'Classify', detail: 'Sonnet receives both claim lists (not the source) and classifies each cross-position conflict by type and resolvability' },
    { title: 'Verdict', detail: 'Opus receives claim lists and conflict table; renders most decision-relevant incompatibility, load-bearing status, and resolution evidence' }
  ]
}

// args: {
//   source_material: string — the text both readings draw from (required)
//   position_a?: string — framing lens for the first reading (default: 'the strongest reading of the source')
//   position_b?: string — framing lens for the second reading (default: 'the strongest opposing reading')
//   context?: string — optional domain background
// }

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const sourceMaterial = _args.source_material || ''
const positionA = _args.position_a || 'the strongest reading of the source'
const positionB = _args.position_b || 'the strongest opposing reading of the same source'
const context = _args.context || null

if (!sourceMaterial || sourceMaterial.length < 20) {
  log('Missing required args. Pass: args.source_material (string, the text both readings draw from)')
  return { error: 'missing_args' }
}

const contextBlock = context ? `\n\nDomain context: ${context}` : ''

// ── Schemas ───────────────────────────────────────────────────────────────────
// Schema design rationale:
// - claim.type (factual/causal/interpretive/normative) lets Stage 3 classify
//   conflicts structurally without re-reading the source.
// - claim.source_anchor (verbatim phrase) provides provenance for Stage 3 and 4
//   without requiring source access.
// - claim.confidence (strong/plausible/inferential) lets the verdict weight
//   conflicts — two inferential claims in conflict is different from two strong ones.
// - conflict.both_load_bearing (bool) is computed from individual confidence ratings
//   and passed forward so Opus can prioritise without re-deriving it.

const CLAIM_LIST_SCHEMA = {
  type: 'object',
  required: ['position_label', 'claims'],
  properties: {
    position_label: {
      type: 'string',
      description: 'The position being argued — restate it clearly in one phrase'
    },
    claims: {
      type: 'array',
      minItems: 2,
      maxItems: 8,
      items: {
        type: 'object',
        required: ['id', 'text', 'type', 'source_anchor', 'confidence', 'load_bearing'],
        properties: {
          id: {
            type: 'string',
            description: 'Short slug identifier, no spaces (e.g. "a1", "a2" for position A claims)'
          },
          text: {
            type: 'string',
            description: 'The claim as a complete, precise, self-contained assertion. One idea only. Must be grounded in the source material — do not add claims the source does not support.'
          },
          type: {
            type: 'string',
            enum: ['factual', 'causal', 'interpretive', 'normative'],
            description: 'factual: asserts a state of affairs or datum. causal: asserts X causes/explains Y. interpretive: asserts what a passage or finding means. normative: asserts a value, priority, or ought-claim.'
          },
          source_anchor: {
            type: 'string',
            description: 'A short verbatim phrase from the source material that grounds this claim. Must appear literally in the source_material input — not a paraphrase. This is the provenance link for downstream stages that do not re-read the source.'
          },
          confidence: {
            type: 'string',
            enum: ['strong', 'plausible', 'inferential'],
            description: 'strong: source directly and explicitly supports this claim. plausible: source is consistent with it but does not state it directly. inferential: requires a reasoning step beyond what the source states.'
          },
          load_bearing: {
            type: 'boolean',
            description: 'True if this claim is structurally necessary to the position — removing it would collapse the argument. False if it is supporting context only.'
          }
        }
      },
      description: 'The strongest-case claim list for this position, derived strictly from the source material. Ordered most to least load-bearing.'
    }
  }
}

const CLASSIFY_SCHEMA = {
  type: 'object',
  required: ['conflicts'],
  properties: {
    conflicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim_a_id', 'claim_b_id', 'conflict_type', 'description', 'resolvability', 'both_load_bearing'],
        properties: {
          claim_a_id: {
            type: 'string',
            description: 'The id of the claim from position A involved in this conflict'
          },
          claim_b_id: {
            type: 'string',
            description: 'The id of the claim from position B involved in this conflict'
          },
          conflict_type: {
            type: 'string',
            enum: ['logical_incompatibility', 'scope_difference', 'terminological', 'normative_priority'],
            description: 'logical_incompatibility: both claims cannot be true simultaneously — one entails the negation of the other. scope_difference: claims are compatible once their domains of application (time, population, conditions) are distinguished. terminological: claims use the same word with different meanings and would agree if disambiguated. normative_priority: both factual claims may be true but the readings disagree on which obligation or value takes precedence.'
          },
          description: {
            type: 'string',
            description: 'One sentence explaining what specifically conflicts and why it falls into this type. Ground in the claim texts and source_anchor fields — do not re-read the source.'
          },
          resolvability: {
            type: 'string',
            enum: ['source_resolvable', 'requires_external_evidence', 'definitional_only', 'normative_choice'],
            description: 'source_resolvable: a closer reading of the source material could resolve this conflict. requires_external_evidence: resolution needs data or evidence not in the source. definitional_only: conflict dissolves once a term is defined — no evidence needed. normative_choice: resolution requires an explicit value judgment or priority decision, not evidence.'
          },
          both_load_bearing: {
            type: 'boolean',
            description: 'True if BOTH claims in this conflict carry load_bearing:true in their respective claim lists. A conflict between two load-bearing claims is more decision-relevant than one where at least one is peripheral.'
          }
        }
      },
      description: 'All pairwise conflicts found between the two claim lists. Include only genuine conflicts — do not pad with non-conflicts. Empty array if no conflicts exist.'
    },
    no_conflict_note: {
      type: 'string',
      description: 'If no conflicts were found, one sentence explaining why the claim lists are compatible. Empty string if conflicts were found.'
    }
  }
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['incompatibilities', 'non_load_bearing_conflicts', 'most_decision_relevant', 'resolution_evidence', 'verdict_summary'],
  properties: {
    incompatibilities: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim_a_id', 'claim_b_id', 'load_bearing', 'decision_relevance', 'resolution_path'],
        properties: {
          claim_a_id: { type: 'string', description: 'Claim id from position A' },
          claim_b_id: { type: 'string', description: 'Claim id from position B' },
          load_bearing: {
            type: 'boolean',
            description: 'True if resolving this incompatibility in either direction materially changes what a decision-maker should do. Consider both_load_bearing from the conflict table as primary signal.'
          },
          decision_relevance: {
            type: 'string',
            description: 'One sentence on what decision changes if position A is right vs. position B on this specific conflict.'
          },
          resolution_path: {
            type: 'string',
            description: 'What specific evidence, specification, or test would determine which claim is correct. Name the type of source or observation needed — not "more research" but "empirical data on X from Y" or "explicit definition of term Z in the authoritative document."'
          }
        }
      },
      description: 'All logical_incompatibility and normative_priority conflicts, enriched with load-bearing status and resolution path.'
    },
    non_load_bearing_conflicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim_a_id', 'claim_b_id', 'conflict_type', 'resolution_note'],
        properties: {
          claim_a_id: { type: 'string' },
          claim_b_id: { type: 'string' },
          conflict_type: { type: 'string', enum: ['scope_difference', 'terminological'] },
          resolution_note: {
            type: 'string',
            description: 'One sentence on what specification or disambiguation dissolves this apparent conflict.'
          }
        }
      },
      description: 'Scope differences and terminological mismatches — apparent conflicts that dissolve once scope or terms are specified. No evidence required to resolve.'
    },
    most_decision_relevant: {
      type: 'string',
      description: 'The id-pair (format: "a1 vs b2") of the single most decision-relevant logical incompatibility or normative_priority conflict, or "none" if no such conflicts exist.'
    },
    resolution_evidence: {
      type: 'string',
      description: 'For the most decision-relevant conflict: what specific evidence, data, or decision would resolve it. Concrete — name the type of source or specification. "None needed — definitional only" if applicable.'
    },
    verdict_summary: {
      type: 'string',
      description: 'Two sentences: (1) whether the two positions are genuinely incompatible or apparently incompatible once scope/terminology is resolved; (2) what the most load-bearing unresolved incompatibility implies for any decision relying on this source material.'
    }
  }
}

// ── Stages 1 + 2: Extract arguments in parallel (structurally independent reads of the same source) ──
// Stage 2 isolation: the steel-man agent builds from the source on its own terms — it has not seen Stage 1's output.

const [claimsA, claimsB] = await parallel([
  () => agent(
    `You are extracting the strongest-case argument for a specific reading of source material.${contextBlock}\n\n` +
    `SOURCE MATERIAL:\n${sourceMaterial}\n\n` +
    `POSITION TO ARGUE: ${positionA}\n\n` +
    `EXTRACTION RULES:\n` +
    `1. Build the strongest possible case for this position using ONLY the source material provided. Do not add claims the source cannot support.\n` +
    `2. Each claim must be atomic — one idea only, precisely stated. Must be independently checkable against a source.\n` +
    `3. Type each claim: factual (state of affairs), causal (X explains Y), interpretive (what a passage means), normative (value or ought-claim).\n` +
    `4. For source_anchor: copy a verbatim phrase from the source that grounds this claim. This is a machine-readable provenance link — it must appear literally in the source text, not paraphrased.\n` +
    `5. Rate confidence: strong (source directly states it), plausible (consistent but not explicit), inferential (requires a reasoning step).\n` +
    `6. Mark load_bearing: true only for claims that are structurally necessary — the argument collapses without them.\n` +
    `7. Order claims most to least load-bearing. Assign ids with prefix "a" (a1, a2, ...).`,
    {
      label: 'extract-a',
      phase: 'Extract-A',
      model: 'claude-sonnet-4-6',
      schema: CLAIM_LIST_SCHEMA
    }
  ),
  () => agent(
    `You are constructing the strongest possible steel-man of a position using source material.${contextBlock}\n\n` +
    `SOURCE MATERIAL:\n${sourceMaterial}\n\n` +
    `POSITION TO STEEL-MAN: ${positionB}\n\n` +
    `STEEL-MAN RULES:\n` +
    `1. Build the most defensible version of this position using ONLY the source material. A steel-man is the best form of the opposing argument — not a straw man.\n` +
    `2. You have not seen the position A argument. Build from the source on its own terms.\n` +
    `3. Each claim must be atomic — one idea only, precisely stated.\n` +
    `4. Type each claim: factual, causal, interpretive, or normative.\n` +
    `5. For source_anchor: copy a verbatim phrase from the source. Must appear literally in the source text.\n` +
    `6. Rate confidence: strong / plausible / inferential.\n` +
    `7. Mark load_bearing: true only for structurally necessary claims.\n` +
    `8. Order claims most to least load-bearing. Assign ids with prefix "b" (b1, b2, ...).`,
    {
      label: 'steelman-b',
      phase: 'Steelman-B',
      model: 'claude-sonnet-4-6',
      schema: CLAIM_LIST_SCHEMA
    }
  )
])

if (!claimsA || !claimsA.claims || claimsA.claims.length === 0) {
  log('Position A extraction failed or returned zero claims — aborting')
  return { error: 'extraction_a_failed' }
}

if (!claimsB || !claimsB.claims || claimsB.claims.length === 0) {
  log('Position B steel-man failed or returned zero claims — aborting')
  return { error: 'steelman_b_failed', claims_a: claimsA }
}

log(`Position A: "${claimsA.position_label}" — ${claimsA.claims.length} claims (${claimsA.claims.filter(c => c.load_bearing).length} load-bearing)`)
log(`Position B: "${claimsB.position_label}" — ${claimsB.claims.length} claims (${claimsB.claims.filter(c => c.load_bearing).length} load-bearing)`)

// ── Stage 3: Classify conflicts (no source re-read) ──────────────────────────
// Stage 3 receives claim lists only. The source_anchor fields provide provenance
// without requiring source access. The type and load_bearing fields supply the
// structural information needed for conflict classification.

phase('Classify')

const classification = await agent(
  `You are classifying conflicts between two claim lists extracted from the same source material.\n` +
  `IMPORTANT: You do not have access to the source — reason only from claim texts, types, source_anchor phrases, and load_bearing flags provided.${contextBlock}\n\n` +
  `POSITION A — "${claimsA.position_label}":\n${JSON.stringify(claimsA.claims, null, 2)}\n\n` +
  `POSITION B — "${claimsB.position_label}":\n${JSON.stringify(claimsB.claims, null, 2)}\n\n` +
  `CLASSIFICATION RULES:\n` +
  `1. Compare every A-claim against every B-claim. Identify all pairs in genuine tension.\n` +
  `2. Classify each conflict:\n` +
  `   - logical_incompatibility: both cannot be true simultaneously — one entails the negation of the other.\n` +
  `   - scope_difference: compatible once domains of application (time, population, conditions) are distinguished.\n` +
  `   - terminological: same word used with different meanings — agreement follows from disambiguation.\n` +
  `   - normative_priority: both factual claims may be true but the readings disagree on which obligation or value takes precedence.\n` +
  `3. For each conflict: one sentence explaining what specifically conflicts and why it falls into that type. Ground in claim text — not source text.\n` +
  `4. Classify resolvability: source_resolvable (closer reading of source settles it), requires_external_evidence, definitional_only (term definition suffices), normative_choice (value judgment required).\n` +
  `5. Set both_load_bearing: true when both claims in the conflict carry load_bearing:true.\n` +
  `6. Do not pad — only list genuine conflicts. Leave the array empty if none exist.`,
  {
    label: 'classify',
    phase: 'Classify',
    model: 'claude-sonnet-4-6',
    schema: CLASSIFY_SCHEMA
  }
)

if (!classification) {
  log('Classification failed — returning claim lists without conflict analysis')
  return { error: 'classification_failed', claims_a: claimsA, claims_b: claimsB }
}

const logicalConflicts = classification.conflicts.filter(
  c => c.conflict_type === 'logical_incompatibility' || c.conflict_type === 'normative_priority'
)
const apparentConflicts = classification.conflicts.filter(
  c => c.conflict_type === 'scope_difference' || c.conflict_type === 'terminological'
)
log(`${classification.conflicts.length} conflicts: ${logicalConflicts.length} genuine (logical/normative), ${apparentConflicts.length} apparent (scope/terminological)`)

if (logicalConflicts.length === 0) {
  log('No logical incompatibilities or normative conflicts — positions are compatible or differ only in scope/framing')
  return {
    verdict_summary: classification.no_conflict_note || 'No genuine incompatibilities detected — the two positions are compatible given the source material.',
    incompatibilities: [],
    non_load_bearing_conflicts: classification.conflicts,
    most_decision_relevant: 'none',
    resolution_evidence: 'None needed — no logical incompatibilities detected.',
    claims_a: claimsA,
    claims_b: claimsB,
    all_conflicts: classification.conflicts
  }
}

// ── Stage 4: Opus verdict ─────────────────────────────────────────────────────
// Opus receives both claim lists and the full conflict table.
// No source access. The source_anchor fields, claim types, confidence ratings,
// and both_load_bearing flags are the full inter-stage contract.

phase('Verdict')

const verdict = await agent(
  `You are rendering a structured verdict on the genuinely incompatible readings of a shared source.\n` +
  `You do not have access to the source material — reason from claim lists and conflict table only.${contextBlock}\n\n` +
  `REQUIRED FIELDS IN YOUR STRUCTURED RESPONSE — populate every one before you submit: ` +
  `incompatibilities — array of the logical_incompatibility/normative_priority conflicts, each with load_bearing, decision_relevance, and a concrete resolution_path; ` +
  `non_load_bearing_conflicts — array of scope_difference/terminological conflicts with a resolution_note each (empty array if none); ` +
  `most_decision_relevant — the single most consequential id-pair (e.g. "a1 vs b2"), or "none"; ` +
  `resolution_evidence — the specific evidence/data/decision that resolves the most decision-relevant conflict; ` +
  `verdict_summary — two sentences: genuinely vs. apparently incompatible, and the decision implication of the most load-bearing incompatibility. ` +
  `(Do not omit a field; if a field legitimately has no content, return its explicit empty/null value, never drop the key.)\n\n` +
  `POSITION A — "${claimsA.position_label}":\n${JSON.stringify(claimsA.claims, null, 2)}\n\n` +
  `POSITION B — "${claimsB.position_label}":\n${JSON.stringify(claimsB.claims, null, 2)}\n\n` +
  `CONFLICT TABLE (${classification.conflicts.length} total):\n${JSON.stringify(classification.conflicts, null, 2)}\n\n` +
  `VERDICT STEPS:\n\n` +
  `1. INCOMPATIBILITIES. For each logical_incompatibility and normative_priority conflict: determine load_bearing (does resolving it change what a decision-maker should do?). Write one sentence on what decision changes if A is right vs. B. Name a concrete resolution_path — "empirical data on X from Y" or "explicit definition of term Z," not "more research."\n\n` +
  `2. NON-LOAD-BEARING CONFLICTS. For scope_difference and terminological conflicts: note what specification or disambiguation dissolves them.\n\n` +
  `3. MOST DECISION-RELEVANT. The single id-pair most consequential for a decision relying on this source. Weight: both_load_bearing conflicts first; logical_incompatibility over normative_priority where confidence ratings are comparable.\n\n` +
  `4. RESOLUTION EVIDENCE. For the most decision-relevant conflict: what specific evidence, data, or decision resolves it. Concrete.\n\n` +
  `5. VERDICT SUMMARY. Two sentences: (1) are the positions genuinely incompatible or apparently incompatible once scope/terminology resolves? (2) what does the most load-bearing incompatibility imply for decision-making?`,
  {
    label: 'verdict',
    phase: 'Verdict',
    model: 'claude-opus-4-8',
    schema: VERDICT_SCHEMA
  }
)

if (!verdict) {
  log('Verdict failed — returning classification without structured verdict')
  return {
    error: 'verdict_failed',
    claims_a: claimsA,
    claims_b: claimsB,
    all_conflicts: classification.conflicts
  }
}

const loadBearingCount = verdict.incompatibilities.filter(i => i.load_bearing).length
log(`Verdict: ${loadBearingCount}/${verdict.incompatibilities.length} load-bearing incompatibilities | most decision-relevant: ${verdict.most_decision_relevant}`)

return {
  verdict_summary: verdict.verdict_summary,
  most_decision_relevant: verdict.most_decision_relevant,
  resolution_evidence: verdict.resolution_evidence,
  incompatibilities: verdict.incompatibilities,
  non_load_bearing_conflicts: verdict.non_load_bearing_conflicts || [],
  claims_a: claimsA,
  claims_b: claimsB,
  all_classified_conflicts: classification.conflicts
}
