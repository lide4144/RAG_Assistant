# M2.1 Policy Evaluation

## Ambiguous Scope Questions (rewrite/clarify)

| # | Question | scope_mode | scope_rule | query_used | Top paper | Evidence summary | Run |
|---|---|---|---|---|---|---|---|
| 1 | What does this paper contribute to game agents? | rewrite_scope | rewrite_for_cross_paper_summary | What does this paper contribute to game agents? cross paper summary | Demo Paper: A Game Agents Battle Driven by Free-Form Text Commands Using Code-Generation LLM and Behavior Branch | N/A | `runs/20260217_221313` |
| 2 | In this work, what method do the authors use? | clarify_scope | clarify_by_author_or_affiliation_intent | In this work, what method do the authors use? | N/A | N/A | `runs/20260217_221314` |
| 3 | 本文的主要实验结论是什么？ | rewrite_scope | rewrite_for_cross_paper_summary | 本文的主要实验结论是什么？ cross paper summary | Report from Dagstuhl Seminar 19511 | N/A | `runs/20260217_221314_01` |
| 4 | 这篇论文的方法有什么局限？ | rewrite_scope | rewrite_for_cross_paper_summary | 这篇论文的方法有什么局限？ cross paper summary | Report from Dagstuhl Seminar 19511 | N/A | `runs/20260217_221314_02` |
| 5 | Our method compared with baseline, what improved? | rewrite_scope | rewrite_for_cross_paper_summary | Our method compared with baseline, what improved? cross paper summary | JOURNAL OF LATEX CLASS FILES, VOL. 14, NO. 8, AUGUST 2015 | a16cfb4afeeb:00099 | `runs/20260217_221315` |

## Author/Affiliation Intent Conditional Release

| # | Question | scope_mode | scope_rule | Top paper | matched front_matter/reference evidence | Run |
|---|---|---|---|---|---|---|
| 1 | corresponding email affiliation university institute contact details | open | open_by_default_or_has_paper_clue | Experiential Co-Learning of Software-Developing Agents | 44768e6771d3:00015(front_matter), 44768e6771d3:00003(front_matter), 3c3ff1b38011:00008(front_matter) | `runs/20260217_221315_01` |
| 2 | front matter affiliation email contact information | open | open_by_default_or_has_paper_clue | GameOn 2016 D King | a54026c8088e:00184(front_matter), a54026c8088e:00186(front_matter) | `runs/20260217_221315_02` |
| 3 | which university and institute are listed for corresponding email | open | open_by_default_or_has_paper_clue | Report from Dagstuhl Seminar 19511 | 3c3ff1b38011:00008(front_matter), a54026c8088e:00184(front_matter), 44768e6771d3:00003(front_matter) | `runs/20260217_221316` |
| 4 | reference list validation citation source details | open | open_by_default_or_has_paper_clue | A Survey on Large Language Model Based Game Agents | eff6f9d4b754:00093(reference) | `runs/20260217_221316_02` |
| 5 | institutional affiliation and contact email in front matter | open | open_by_default_or_has_paper_clue | Demo Paper: A Game Agents Battle Driven by Free-Form Text Commands Using Code-Generation LLM and Behavior Branch | a54026c8088e:00184(front_matter), a54026c8088e:00186(front_matter) | `runs/20260217_221317` |
