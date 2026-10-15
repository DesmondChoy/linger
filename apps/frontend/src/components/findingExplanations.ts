import type { RiskCode } from '../types'

/** What each Provenance finding means, in a sentence a reader can follow. */
export const FINDING_EXPLANATIONS: Record<RiskCode, string> = {
  unresolved_evidence: 'The draft cited evidence the turn never actually retrieved.',
  misattribution: 'The draft attributed something to the wrong source.',
  spoiler: 'The draft reached past the confirmed reading boundary.',
  uncited_web_claim: 'The draft made a web-sourced claim without citing the page.',
  unsupported_claim: 'The draft asserted something no retrieved evidence supports.',
  sensitive_content: 'The draft handled sensitive material outside policy.',
  emotional_policy_violation: 'The draft breached the emotional boundary contract.',
  prompt_injection: 'Retrieved content tried to steer the agent.',
  policy_override: 'The draft complied with an attempt to override its instructions.',
  harmful_content: 'The draft contained toxic, dangerous, or hateful content.',
  false_persona: 'The draft claimed a human self or fostered dependence on the companion.',
  professional_advice: 'The draft gave individualised medical, legal, financial, or therapeutic advice.',
  out_of_scope: 'The draft performed a task unrelated to reflecting on the reading.',
  instruction_disclosure: "The draft revealed or paraphrased the companion's own instructions or tooling.",
}
