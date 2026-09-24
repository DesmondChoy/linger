"""Offline validation of retained iteration-6 outputs; never invokes a provider."""
import json
from pathlib import Path

from src.linger.agents.librarian.models import (
    LibrarianBoundaryInferenceInput,
    boundary_candidate_inventory_errors,
)

BASE = Path(__file__).resolve().parent
results = []
for suite in (4, 9, 10, 11):
    path = BASE / 'iteration-06-0b927fa3' / f'suite-{suite}.json'
    for scene in json.loads(path.read_text())['scenes']:
        for exchange in scene['agent_exchanges']:
            raw = exchange.get('input_prompt', '')
            if not isinstance(raw, str) or 'full_work_candidates' not in raw:
                continue
            request = LibrarianBoundaryInferenceInput.model_validate_json(raw)
            for message in exchange.get('model_messages', []):
                for part in message.get('parts', []):
                    candidate = part.get('args')
                    if isinstance(candidate, str):
                        try:
                            candidate = json.loads(candidate)
                        except ValueError:
                            continue
                    if not isinstance(candidate, dict) or candidate.get('outcome') != 'candidate':
                        continue
                    for anchor in candidate.get('supporting_evidence', []):
                        anchor['source_excerpt'] = anchor.pop('exact_quote')
                    results.append({
                        'suite': suite,
                        'scene_id': scene['scene_id'],
                        'candidate_chapter': candidate.get('chapter_number'),
                        'errors': boundary_candidate_inventory_errors(candidate, request),
                    })
print(json.dumps({'kind': 'offline_saved_output_probe_not_live_rerun', 'results': results}, indent=2))
