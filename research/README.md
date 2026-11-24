# Paper in Motion study workflow

The corpus includes CLIFF and LoRA for development and four held-out papers. The paper manifest lists the public sources and the expected local PDF names. Download the documents into `research/pdfs/` and have reviewers check the content checklist, independent calculation checkpoints and reference answers against the exact editions and supplements. For another corpus copy `papers.json` and pass `--corpus path/to/papers.json` before the command. To include supplementary PDFs add a `supplements` list of up to three paths per paper.

## A/B/C experiments

All conditions share the same paper, language, audience, output length, model, style, validation and video renderer.

| Condition | Process |
| --- | --- |
| A | Directly plan a complete explanation, concrete example and animation from the paper evidence. |
| B | Create a source-linked method record before planning and include a concrete comparative example. |
| C | Share computed example states from the executor with the storyboard and narration after method planning. |

Run the commands below from the project directory. The default held-out plan crosses four papers, three conditions and two runs for 24 attempts. The seed fixes order. Additional runs require a separate output directory.

```sh
.venv/bin/python scripts/research.py plan --output research/outputs/plan.json
.venv/bin/python scripts/research.py run --live --max-jobs 1 --output research/outputs/pilot
.venv/bin/python scripts/research.py run --live --output research/outputs/heldout
```

Use `--live` when ready to submit requests through the running local server and incur model usage. Use the same output directory to resume monitoring submitted runs. The ledger records accepted job IDs, terminal failures, completion, runtime and measurable usage. The server writes normal video and project exports per job. Supply current rates per million tokens to get a labelled estimate, for example via `--rates local-rates.json`. The rate keys are `currency`, `prompt_tokens`, `completion_tokens`, `speech_input_tokens` and `speech_output_tokens`. Omitted token usage or rates remain unknown and the estimate is marked partial. Actual provider charges are obtained from the account.

## Review and measurements

Use the checklist and reference answers in the corpus, and score each paper version before examining other versions. Record each judge's observations in separate JSONL rows. Example shape for one observation:

```json
{"attempt_id":"resnet-A-1","judge":"human","judge_id":"R01","mechanism_depth":2,"checked_claims":6,"supported_claims":5,"coverage":{"background":1,"baseline":1,"innovation":0.5,"process":1,"results":0},"checked_checkpoints":2,"correct_checkpoints":2,"checked_presentations":2,"correctly_presented_results":1,"sampled_frames":12,"defect_frames":1,"required_key_events":4,"matched_key_events":3,"median_absolute_offset_ms":180,"clarity":4,"visual_appeal":3,"manual_edits":1,"manual_edit_minutes":4.5}
```

The numbers above demonstrate the file format. For review, count supported claims only after comparing to paper evidence. Score mechanism as 0 for absent or incorrect, 1 for stating the change and outcome and 2 for explaining intermediate operations. Score each coverage item 0, 0.5 or 1. Inspect video frames for clipping, illegible text, overlapping objects or export defects. Compare visible values to the separate calculation checkpoints. Annotate spoken events by listening before measuring their absolute timing offset against the visual event. Score clarity, readability, pacing and appeal separately from 1 to 5. The opt-in model judge uses the configured Bailian model with paper excerpts and sampled frames. It writes the same rating schema with `"judge":"model"`, including model and rubric versions. The summary compares each model metric against human scores on the same attempts and reports mean bias and mean absolute error.

Per-job `evaluation.json` includes source location counts, independent numerical checks for supported example templates, stream and duration checks and scheduled cue checks. A source location score measures whether the cited content can be located. Human or model judges assess factual support. Timing is scored only where there is an independently annotated reference.

```sh
.venv/bin/python scripts/research.py sample-frames --job data/JOB_ID --count 12 --output research/outputs/FOLDER
.venv/bin/python scripts/research.py judge --live --job data/JOB_ID --paper-id resnet --attempt-id resnet-A-1 --output research/outputs/ratings.jsonl
.venv/bin/python scripts/research.py summarize --attempts research/outputs/heldout/attempts.jsonl --ratings research/outputs/ratings.jsonl --output research/outputs/summary.json
```

## Viewer study

Recruit 18–24 viewers with basic machine-learning knowledge. Assign anonymous IDs. Each watches two different papers, one A and one C, with paper-condition roles, viewing order and available versions balanced. Generate assignments after collecting completed attempts:

```sh
.venv/bin/python scripts/research.py study --participants 24 --attempts research/outputs/heldout/attempts.jsonl --output research/outputs/assignments.json
.venv/bin/python scripts/research.py score-study --assignments research/outputs/assignments.json --scores research/outputs/viewer-scores.jsonl --output research/outputs/viewer-summary.json
```

Share only the assigned clips and unlabeled questions with viewers. Keep phase and condition metadata in the assignment file for the study coordinator. The six held-out questions mix mechanism, new input and changed-condition tasks. Score each response 0 for missing or incorrect, 1 for partially correct and 2 for correct reasoning or result. In recorded scores use records such as `{"participant_id":"P01","attempt_id":"resnet-A-1","scorer":"R01","answers":[2,1,2,0,1,2],"clarity":4,"readability":5,"pacing":4}`. Put the primary scorer's record first and a second scorer's record for a reviewed subset. Summary reports paired comprehension separately from experience and records second-scorer agreement.

## Feedback and adaptation

Compare the original and revised artifact with the same checklist and independent reference values. Generate a focused revision proposal from the local evaluation and optional reviewer notes. Review the proposals before submitting an edit from the workbench. The mechanical comparison records resolved, persistent and introduced findings plus measured token deltas. Record human or model findings separately, including supporting evidence and affected stages.

```sh
.venv/bin/python scripts/research.py feedback-plan --evaluation data/ORIGINAL/evaluation.json --ratings research/outputs/ratings.jsonl --attempt-id resnet-A-1 --output research/outputs/proposed-revision.json
.venv/bin/python scripts/research.py compare-revision --before data/ORIGINAL/evaluation.json --after data/REVISED/evaluation.json --output research/outputs/revision.json
```
 Keep training examples limited to team-verified corrections from development papers.

```sh
.venv/bin/python scripts/research.py adaptation-data --corrections research/outputs/verified-corrections.jsonl --output research/outputs/understanding-sft.jsonl
```

Each source correction contains `paper_id`, stage `understanding` or `mechanism_plan`, `verified: true`, an anonymous `verified_by`, original and revised JSON records, original model input, and `source_evidence` as a list of physical PDF page and quote objects. The export validates reviewer status and the development split. When PDFs are present the corpus rejects identical documents assigned to multiple IDs. Review the development corpus for alternate editions of held-out papers before training.

The JSONL is ready for a compatible managed LoRA training job once verified corrections have been collected. Use a separate experimental endpoint for the adapted and unadapted checkpoints of the same open-weight model. Freeze the held-out set and use identical production, feedback and viewer protocols. Report effect sizes, sample counts and added cost separately. No human participation, fine-tuning, or full 24-attempt batch is recorded by the repository. Generated timelines and study instrument files are preparation artifacts.
