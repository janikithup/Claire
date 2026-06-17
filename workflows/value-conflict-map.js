export const meta = {
  name: 'value-conflict-map',
  description: 'Four Sonnet workers each apply one normative frame to the same policy, institution, or plan. By default the frames are fixed (market efficiency / collective resilience / state control / procedural fairness); a caller may instead supply their own four frames, each as a bare label or as a { label, description, core_values } object so the custom frame carries real substance for its worker. Each scores how well the object serves their frame and names the value it violates or satisfies. Opus synthesises a pairwise conflict matrix — which frame pairs are zero-sum, pseudo-compatible, or orthogonal — and names contested design choices where frames most sharply diverge.',
  whenToUse: 'When you need to understand why stakeholders disagree about a policy or plan at the level of values rather than facts. Use to map normative conflict before designing consultation processes, anticipate objections from different value positions, or diagnose why a "compromise" satisfies nobody. Pass args.object (the policy/plan text) and optionally args.context (background on the domain). To swap in your own normative frames, pass args.frames (exactly 4): each frame may be a bare string label, or an object { label, description, core_values } so the custom frame carries real substance for its worker to reason from. Returns frame_scores, a pairwise conflict matrix, the dominant_frame, and contested_dimensions.',
  phases: [
    { title: 'Frame workers', detail: 'Four Sonnet workers in parallel — one per normative frame — each applies their frame to score the object and name contested choices' },
    { title: 'Synthesis', detail: 'Opus synthesises a pairwise conflict matrix, dominant frame, and contested dimensions aggregated from worker outputs' }
  ]
}

// args: {
//   object: string — the policy, plan, institution, or scenario to evaluate
//   context?: string — optional background on the domain or decision context
//   frames?: (string | { label: string, description?: string, core_values?: string })[]
//       — optional override of the four canonical frames (must be exactly 4 if provided).
//       Each entry may be a bare string label (degrades to label-only, as before), OR an
//       object carrying { label, description (what the frame holds), core_values (the values
//       it prioritises) } so the custom frame gives its worker real substance to reason from.
//       Mixed arrays are fine — some entries plain strings, some rich objects.
// }

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const object = _args.object || ''
const context = _args.context || null
const framesOverride = Array.isArray(_args.frames) && _args.frames.length > 0 ? _args.frames : null

if (!object) {
  log('Missing required args. Pass: args.object (string — the policy, plan, or scenario to evaluate)')
  return { error: 'missing_args' }
}

if (framesOverride && framesOverride.length !== 4) {
  log('If providing args.frames, exactly 4 frames are required')
  return { error: 'invalid_args' }
}

// Each custom frame is either a bare string label or an object carrying at least a label.
const frameEntryUsable = (f) =>
  (typeof f === 'string' && f.trim().length > 0) ||
  (f && typeof f === 'object' && typeof f.label === 'string' && f.label.trim().length > 0)

if (framesOverride && !framesOverride.every(frameEntryUsable)) {
  log('Each custom frame must be a non-empty string label, or an object with a non-empty label (plus optional description and core_values)')
  return { error: 'invalid_args' }
}

// ── Canonical frames ──────────────────────────────────────────────────────────

const CANONICAL_FRAMES = [
  {
    key: 'market-efficiency',
    label: 'Market Efficiency',
    description: 'Value axis: allocative efficiency, price signals, competition, private initiative. Criteria: does the object allocate resources to their highest-value use? Does it preserve or enhance market mechanisms, competition, and price discovery? Does it avoid distorting investment incentives?',
    core_value: 'efficient allocation through competitive market mechanisms'
  },
  {
    key: 'collective-resilience',
    label: 'Collective Resilience',
    description: 'Value axis: community capacity, mutual aid, distributed control, adaptive capacity. Criteria: does the object strengthen collective capacity to absorb shocks and respond together? Does it build shared control and interdependence rather than centralising risk or dependency?',
    core_value: 'shared capacity to respond to disruption together'
  },
  {
    key: 'state-control',
    label: 'State Control',
    description: 'Value axis: public authority, regulatory sovereignty, democratic accountability, universal access. Criteria: does the object preserve public oversight and democratic control? Does it deliver universal access and equity? Does it prevent private capture of essential public functions?',
    core_value: 'democratic sovereignty and universal provision'
  },
  {
    key: 'procedural-fairness',
    label: 'Procedural Fairness',
    description: 'Value axis: due process, inclusive voice, transparency, non-domination. Criteria: does the object ensure affected parties have meaningful input? Are decision rules transparent and consistently applied? Does it protect against arbitrary exercise of power?',
    core_value: 'fair process regardless of substantive outcome'
  }
]

// Normalise a custom frame to the worker-prompt shape { key, label, description, core_value }.
// A bare string degrades to label-only (description/core_value fall back to the label, as before).
// A rich object supplies its own description (what the frame holds) and core_values (the values
// it prioritises) so the worker has real substance to reason from instead of a bare label.
const normalizeFrame = (f, i) => {
  if (typeof f === 'string') {
    return { key: `frame-${i}`, label: f, description: f, core_value: f }
  }
  const label = f.label
  const description = (typeof f.description === 'string' && f.description.trim().length > 0) ? f.description : label
  const core_value = (typeof f.core_values === 'string' && f.core_values.trim().length > 0) ? f.core_values : label
  return { key: `frame-${i}`, label, description, core_value }
}

const ACTIVE_FRAMES = framesOverride
  ? framesOverride.map(normalizeFrame)
  : CANONICAL_FRAMES

// ── Schemas ───────────────────────────────────────────────────────────────────

const FRAME_SCORE_SCHEMA = {
  type: 'object',
  required: ['frame', 'score', 'reasoning', 'value_satisfied', 'value_violated', 'contested_choices'],
  properties: {
    frame: {
      type: 'string',
      description: 'The frame label — restate it exactly as given'
    },
    score: {
      type: 'string',
      enum: ['high', 'medium', 'low'],
      description: 'How well the object serves this frame overall. high = the design substantially advances this frame\'s core values. medium = mixed; some elements advance, others undermine. low = the design substantially conflicts with this frame\'s core values.'
    },
    reasoning: {
      type: 'string',
      description: '2-3 sentences grounding the score in specific features of the object — name specific design choices, not generic statements about the frame'
    },
    value_satisfied: {
      type: 'string',
      description: 'The specific value from this frame that the object most clearly advances. If score is low, name the value that would be satisfied by an alternative design. One sentence.'
    },
    value_violated: {
      type: 'string',
      description: 'The specific value from this frame that the object most clearly undermines. If score is high, name the residual tension that remains — no frame is perfectly served by any real design. One sentence.'
    },
    contested_choices: {
      type: 'array',
      minItems: 1,
      maxItems: 4,
      items: {
        type: 'string',
        description: 'A specific design choice in the object that this frame finds problematic or load-bearing. Named precisely enough that another frame could evaluate the same choice.'
      },
      description: '1-4 specific design choices where this frame\'s verdict most sharply diverges from a neutral reading. These become the raw material for contested_dimensions synthesis.'
    }
  }
}

const SYNTHESIS_SCHEMA = {
  type: 'object',
  required: ['pairs', 'dominant_frame', 'contested_dimensions'],
  properties: {
    pairs: {
      type: 'array',
      minItems: 1,
      maxItems: 6,
      items: {
        type: 'object',
        required: ['frame_a', 'frame_b', 'relationship', 'explanation'],
        properties: {
          frame_a: { type: 'string', description: 'First frame label' },
          frame_b: { type: 'string', description: 'Second frame label' },
          relationship: {
            type: 'string',
            enum: ['zero_sum', 'pseudo_compatible', 'orthogonal'],
            description: 'zero_sum: satisfying one necessarily harms the other — the design choices that serve frame A are the same choices that fail frame B. pseudo_compatible: shared surface vocabulary but divergent underlying values — apparent agreement that dissolves on contact with specifics. orthogonal: the frames evaluate different dimensions of the object and do not directly conflict on any single design choice.'
          },
          explanation: {
            type: 'string',
            description: 'One or two sentences naming a specific design choice in the object that generates this relationship — ground the verdict in something concrete, not a general statement about the two frames'
          }
        }
      },
      description: 'One entry per unordered pair of the frames provided (up to six pairs when all four frames are present). Match the count stated in the synthesis instruction.'
    },
    dominant_frame: {
      type: 'string',
      description: 'The frame whose values are most embedded in the specific design choices the object makes — not the highest-scored frame mechanically, but the one whose assumptions structure the design. Name the frame and in one sentence explain which design choice most clearly privileges it.'
    },
    contested_dimensions: {
      type: 'array',
      minItems: 2,
      maxItems: 4,
      items: {
        type: 'object',
        required: ['design_choice', 'frames_in_conflict', 'conflict_nature'],
        properties: {
          design_choice: {
            type: 'string',
            description: 'The specific design choice where frames diverge — drawn from the workers\' contested_choices and value_violated fields, not invented'
          },
          frames_in_conflict: {
            type: 'array',
            items: { type: 'string' },
            description: 'The frame labels most sharply opposed on this choice'
          },
          conflict_nature: {
            type: 'string',
            description: 'One sentence: what specifically each side wants on this design choice and why they cannot both be satisfied'
          }
        }
      },
      description: '2-4 specific design choices where frames most sharply diverge. Must be drawn from and cross-referenced against the workers\' contested_choices and value_violated fields — do not invent dimensions no worker named.'
    }
  }
}

// ── Stage 1: frame workers in parallel ───────────────────────────────────────
// Workers are isolated — constructed inside parallel(), no sibling results
// exist when any individual prompt is built.

phase('Frame workers')
log(`Running ${ACTIVE_FRAMES.length} frame workers in parallel`)

const contextBlock = context ? `\n\nDomain context: ${context}` : ''

const frameResults = await parallel(
  ACTIVE_FRAMES.map((frame) => () =>
    agent(
      `You are evaluating an object through one specific normative frame. This frame fully constrains your output — do not blend in reasoning from other frames.\n\n` +
      `FRAME: ${frame.label}\n` +
      `${frame.description}\n` +
      `Core value: ${frame.core_value}\n\n` +
      `You have not seen any other frame worker's output. Apply your frame independently.\n\n` +
      `OBJECT TO EVALUATE:\n${object}${contextBlock}\n\n` +
      `Working entirely inside this frame:\n\n` +
      `1. Score how well the object serves this frame (high/medium/low). Ground the score in specific features of the object — not generic statements about the frame.\n\n` +
      `2. Name the specific value from this frame that the object most clearly advances (value_satisfied). If your score is low, name the value that an alternative design would satisfy.\n\n` +
      `3. Name the specific value from this frame that the object most clearly undermines (value_violated). If your score is high, name the residual tension that remains — no frame is perfectly served by any real design.\n\n` +
      `4. List 1-4 specific design choices in the object that your frame finds most problematic or load-bearing (contested_choices). Name them precisely enough that another frame could evaluate the same choice.`,
      {
        label: `frame:${frame.key}`,
        phase: 'Frame workers',
        model: 'claude-sonnet-4-6',
        schema: FRAME_SCORE_SCHEMA
      }
    )
  )
)

const validFrames = frameResults.filter(Boolean)
log(`${validFrames.length} of ${ACTIVE_FRAMES.length} frame workers returned`)

if (validFrames.length < 2) {
  return { error: 'insufficient_frames', frame_scores: validFrames }
}

if (object.trim().split(/\s+/).length < 80) {
  log('Warning: object is short (< 80 words) — frame assessments may be underspecified')
}

// ── Stage 2: Opus synthesis ───────────────────────────────────────────────────

phase('Synthesis')

const synthesis = await agent(
  `You are synthesising four normative-frame assessments of the same object into a conflict map.\n\n` +
  `OBJECT:\n${object}${contextBlock}\n\n` +
  `FRAME ASSESSMENTS (${validFrames.length} frames, each applied independently):\n${JSON.stringify(validFrames, null, 2)}\n\n` +
  `SYNTHESIS DISCIPLINE:\n\n` +
  `1. CONFLICT MATRIX — for each of the ${validFrames.length * (validFrames.length - 1) / 2} unordered frame pairs (every pair among the ${validFrames.length} frames provided), classify the relationship as:\n` +
  `   zero_sum: the design choices that serve frame A are the same ones that fail frame B\n` +
  `   pseudo_compatible: shared vocabulary but divergent underlying values — apparent agreement that dissolves on specifics\n` +
  `   orthogonal: the frames evaluate different dimensions and do not directly conflict on any single design choice\n` +
  `   Heuristic prior: a pair leans zero_sum when one frame's value_violated names what another frame's value_satisfied names — but confirm this against a named design element in the object before classifying.\n\n` +
  `2. DOMINANT FRAME — which frame is most served by the current design? Not the highest-scored frame mechanically, but the one whose values are most embedded in the specific design choices the object makes. Name a specific design choice that makes this frame dominant.\n\n` +
  `3. CONTESTED DIMENSIONS — 2-4 specific design choices where frames most sharply diverge. These MUST be drawn from and cross-referenced against the workers' contested_choices and value_violated fields — do not invent dimensions no worker named. For each: name the choice, the frames in conflict, and in one sentence what each side wants and why they cannot both be satisfied.`,
  {
    label: 'synthesis',
    phase: 'Synthesis',
    model: 'claude-opus-4-8',
    schema: SYNTHESIS_SCHEMA
  }
)

if (!synthesis) {
  log('Synthesis failed — returning frame scores without conflict map')
  return { error: 'synthesis_failed', frame_scores: validFrames }
}

const zeroSumCount = synthesis.pairs?.filter(p => p.relationship === 'zero_sum').length || 0
log(`Dominant frame: ${synthesis.dominant_frame?.split(' ')[0] || 'unknown'} — ${zeroSumCount} zero-sum pairs`)

return {
  pairs: synthesis.pairs || [],
  dominant_frame: synthesis.dominant_frame,
  contested_dimensions: synthesis.contested_dimensions || [],
  frame_scores: validFrames
}
