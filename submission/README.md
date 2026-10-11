# Team No. 28 Submission Package

Deadline supplied by the team: 11 October 2026, exact time not supplied.
This is a prepared local package, **not confirmation of portal submission**.
The [current Phase 2 checklist](phase2-checklist.json) maps the supplied slides
to implemented functions, verified evidence and unimplemented failure examples.
The [requirements audit](requirements-audit.json) distinguishes fresh live
checks from retained evidence and remaining human steps. The latest three-fault
run is summarized in [runtime audit](runtime-audit.json), with an independently
verified [current workflow](current-workflow.json).

## Five Deliverables

| Deliverable | File / Link |
| --- | --- |
| Source and setup | [Day-2 review branch](https://github.com/saurabhshreni-cmyk/bosch-chaos-hackathon/tree/day2-submission), [README](../README.md) |
| Captioned demo, under 3 minutes | [demo.webm](demo.webm), [captions](demo.vtt), [recording provenance](demo.json) |
| One-page architecture | [architecture.pdf](architecture.pdf), [HTML source](architecture.html) |
| Ranked findings and recommended fixes | [findings.md](findings.md), [comparison measurements](comparison.json) |
| Team details, tools and models | [team-form.json](team-form.json) |

Real retained execution evidence: [docs/evidence/day2](../docs/evidence/day2).
The updated demo records the current dashboard, automatic discovery, a real
combined failure and STOP recovery. Its execution provenance is in demo.json.
See [automatic discovery](../docs/automatic-discovery.md) for measured failures,
potential risks, registered executable tests and non-executable proposals.
The dated audits above retain their original verification results; the current
packaged execution IDs and media checks are recorded separately below.
The exact AI, combined-failure and validation run IDs are in [manifest.json](manifest.json).
The [clean-start evidence](clean-start.json) records fresh deployment and the
customer → vehicle → maintenance → completion workflow, without clearing the
existing garage. [Verification](verification.json) records automated checks.

## Demonstrate To The Instructor

1. Open Pitstop at http://localhost:7005 and the dashboard at http://127.0.0.1:7010.
2. Select the completed AI run listed in the manifest. Show Dependencies,
   AI ranking, three experiment results and Evidence & findings.
3. Play the captioned video: it shows a real live combined failure and manual
   STOP recovery, then real AI findings from the completed suite.
4. Show the before/after comparison. Workshop fallback became faster, but its
   availability under delay decreased. Do not describe this as an improvement
   in every resilience dimension.
5. Open the one-page architecture and all five deliverable files.

## Final Human Steps

The team must review the findings, confirm the official submission URL and
deadline time, fill any portal-specific fields and upload/link all five items.
Check the uploaded video plays and the instructor has access to the repository
branch and documents. Merge through team review if the portal expects `main`.
No external submission has been made by the agent.
Latest local changes still need team review and publishing to the shared branch.

AI rationale is untrusted: the small model sometimes confuses experiment
descriptions. The validated tool ID, not the prose, determines the bounded
fault mechanism. Reports flag model findings as hypotheses. Scores are
transparent read-probe heuristics, not AI-certified SLAs. Legacy transitive
NuGet packages still produce vulnerability warnings; sandbox use only.
