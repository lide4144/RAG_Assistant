# M2 Baseline Evaluation
- Date: 2026-02-17
- Data: `data/processed/chunks_clean.jsonl`
- Indexes: `data/indexes/bm25_index.json`, `data/indexes/vec_index.json`

## A. Required 10-question baseline records

### Q1 (hybrid)
- Question: What is the main contribution of this work?
- Answer: 基于检索证据，问题“What is the main contribution of this work?”最相关内容见 711e9a632925:00002。
- Evidence:
  - 711e9a632925:00002 [p.1] University of Essex, Colchester, UK Email: {kkunan, rdgain, jialin.liu, dperez, sml}@essex.ac.uk Abstract—This paper...
  - 62445b7f6828:00154 [p.6] Main Results
  - fefee55018b5:00097 [p.6] Peer review information Nature thanks Jesse Hoey, Brendan Lake and the other, anonymous, reviewer(s) for their contri...
  - fefee55018b5:00045 [p.3] This is a conversation between User, a human, and Bot, a clever and knowledgeable AI agent. User: What is 2 + 2? User...
  - 3842e450dccd:00175 [p.12] Peer review information Nature thanks Emmanuel Guardiola, Amy Hoover and the other, anonymous, reviewer(s) for their...

### Q2 (hybrid)
- Question: Which datasets are used for evaluation?
- Answer: 基于检索证据，问题“Which datasets are used for evaluation?”最相关内容见 35bf14e7f4c2:00060。
- Evidence:
  - 35bf14e7f4c2:00060 [p.5] Datasets
  - 62445b7f6828:00305 [p.11] Table 11-12 present the sys- tem prompts for models. Table 13-14 present the prompts used in the Evaluation.
  - 7458c2c5e62e:00237 [p.16] Hyperparameter Settings We summarize the hyperparameter settings used for LoRI in Tables 4, 5, 6, and 7. These includ...
  - 711e9a632925:00085 [p.6] Equation 3 is similar to that used for the Physical Traveling Salesman Problem by Perez et. al. [7]. Based on this ﬁt...
  - 1a0a22c1909a:00019 [p.2] The rules are different every time you play, and even between different players' terminal computers. Artificial intel...

### Q3 (hybrid)
- Question: What metrics are reported in the experiments?
- Answer: 基于检索证据，问题“What metrics are reported in the experiments?”最相关内容见 35bf14e7f4c2:00062。
- Evidence:
  - 35bf14e7f4c2:00062 [p.5] Metrics
  - 62445b7f6828:00146 [p.6] Metrics
  - 7458c2c5e62e:00414 [p.18] For the merging experiments, the hyperparameter settings for merging four adapters are provided in Tables 8 and 9, wh...
  - 62445b7f6828:00187 [p.8] Stage-3, the model loses its guiding and interac- tion abilities in multi-turn scenarios as a ChatGE, resulting in ES...
  - 62445b7f6828:00110 [p.5] Experiments

### Q4 (bm25)
- Question: How do the authors define user experience?
- Answer: 基于检索证据，问题“How do the authors define user experience?”最相关内容见 4c13ce9014b6:00037。
- Evidence:
  - 4c13ce9014b6:00037 [p.2] Therefore, research on how emergent responses in game leads dynamic changes in narratives and the game world, as well...
  - 62445b7f6828:00138 [p.6] Guidance How the response guide the user step-by-step to complete the game.
  - 4c13ce9014b6:00084 [p.6] To ensure effective implementation, it is crucial to clearly define the roles and limitations of LLMs rather than vie...
  - fefee55018b5:00045 [p.3] This is a conversation between User, a human, and Bot, a clever and knowledgeable AI agent. User: What is 2 + 2? User...
  - eff6f9d4b754:00093 [p.6] Validation of the GUESS-18: a short version of the Game User Experience Satisfaction Scale (GUESS). Journal of Usabil...

### Q5 (dense)
- Question: What is the proposed method architecture?
- Answer: 基于检索证据，问题“What is the proposed method architecture?”最相关内容见 3842e450dccd:00042。
- Evidence:
  - 3842e450dccd:00042 [p.3] Model architecture and data
  - 7458c2c5e62e:00059 [p.3] Method 2.1
  - 6cd26228bc23:00079 [p.8] 4 GENERATIVE AGENT ARCHITECTURE
  - 6cd26228bc23:00209 [p.21] A ARCHITECTURE OPTIMIZATIONS
  - 7458c2c5e62e:00101 [p.6] Method # Params (%)

### Q6 (hybrid)
- Question: What are the limitations discussed by the authors?
- Answer: 基于检索证据，问题“What are the limitations discussed by the authors?”最相关内容见 4b159262bfe9:00312。
- Evidence:
  - 4b159262bfe9:00312 [p.39] Future Steps While the authors are conﬁdent of the capabilities of artiﬁcial intelligence and the community’s capacit...
  - 62445b7f6828:00204 [p.9] Limitations
  - 35bf14e7f4c2:00125 [p.9] Limitations
  - eff6f9d4b754:00063 [p.4] There are potential limitations and areas for improvement in the implementation and experimental design of the project.
  - 6cd26228bc23:00172 [p.17] 8.2 Future Work and Limitations

### Q7 (hybrid)
- Question: Which baselines are compared in the paper?
- Answer: 基于检索证据，问题“Which baselines are compared in the paper?”最相关内容见 35bf14e7f4c2:00057。
- Evidence:
  - 35bf14e7f4c2:00057 [p.5] Baselines
  - 1a5b25a5e857:00007 [p.1] This paper proposes an LLM-based framework to generate games (LLMGG), in which rule descriptions and levels are repre...
  - a54026c8088e:00108 [p.5] Each tester was asked to state to what extent they felt that the agent displayed evidence of learning while playing t...
  - 711e9a632925:00031 [p.3] A Random Mutation Hill Climber is the simplest version of an evolutionary algorithm, with only one individual in the...
  - a54026c8088e:00055 [p.3] N-Grams are a type of unsupervised learning technique used in order to learn patterns in sequences. Through the use o...

### Q8 (bm25)
- Question: What implementation tools or frameworks are mentioned?
- Answer: 基于检索证据，问题“What implementation tools or frameworks are mentioned?”最相关内容见 95b8be8dcf4e:00026。
- Evidence:
  - 95b8be8dcf4e:00026 [p.3] There are various methods and platforms currently existing that can be used for collecting data. Cloud based tools su...
  - 6cd26228bc23:00095 [p.10] Approach: We introduce a second type of memory, which we call a refection. Refections are higher-level, more abstract...
  - eff6f9d4b754:00063 [p.4] There are potential limitations and areas for improvement in the implementation and experimental design of the project.
  - 4c13ce9014b6:00024 [p.1] Although LLMs have shown potential to generate emergent game environments, their technical implementation and impact...
  - 6cd26228bc23:00090 [p.9] Relevance assigns a higher score to memory objects that are related to the current situation. What is relevant depend...

### Q9 (dense)
- Question: How is the experiment setup described?
- Answer: 基于检索证据，问题“How is the experiment setup described?”最相关内容见 e2bfdf7c52f7:00192。
- Evidence:
  - e2bfdf7c52f7:00192 [p.8] Notably, p is measured by simulating the generated skills multiple times under the same conditions. In our setup, we...
  - e9b0666f1faf:00095 [p.5] In this experiment, the impact of the different personalities of Amy is evaluated. Figure 5 shows the average emotion...
  - 4b159262bfe9:00295 [p.37] Naturally, implementing a system as described above is a challenging undertaking, but in principle, since game worlds...
  - a16cfb4afeeb:00008 [p.1] However, the approach is general and can handle any game scenario whose state and objectives can be described in text.
  - 3c3ff1b38011:00046 [p.4] Specifically, we aim to analyse its generalisability against different types of illusion attacks and evaluate its per...

### Q10 (hybrid)
- Question: What future work directions are suggested?
- Answer: 基于检索证据，问题“What future work directions are suggested?”最相关内容见 44768e6771d3:00426。
- Evidence:
  - 44768e6771d3:00426 [p.22] Discussion and Future Directions
  - a54026c8088e:00158 [p.8] Future Work
  - 67978670bdb6:00075 [p.3] Future Work
  - bdb7af5dcebd:00077 [p.13] Conclusions and future work
  - 86316b13369f:00021 [p.2] Behavior Branches using code-generation LLM, has become available for actual battle gaming. For future work, we plan...

## B. 30-question acceptance checklist (subjective relevance pass)
- Rule: Mark PASS when top-5 evidence contains semantically related passage by manual review.
- [AUTO_HIT] Q01: What is the paper's research question? | top evidence: 6cd26228bc23:00217 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q02: Which method outperforms the baseline? | top evidence: 35bf14e7f4c2:00098 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q03: What are the reported accuracy numbers? | top evidence: 7458c2c5e62e:00160 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q04: What is the data collection process? | top evidence: e9b0666f1faf:00077 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q05: Which user groups are involved in the study? | top evidence: 4c13ce9014b6:00047 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q06: What are the key model components? | top evidence: e2bfdf7c52f7:00061 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q07: How are ablation studies designed? | top evidence: 7458c2c5e62e:00672 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q08: What assumptions are made in the approach? | top evidence: 4b159262bfe9:00034 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q09: Which threats to validity are mentioned? | top evidence: 62445b7f6828:00140 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q10: How is qualitative analysis performed? | top evidence: a54026c8088e:00093 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q11: What game genres are discussed? | top evidence: 4b159262bfe9:00247 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q12: Which platforms are targeted by the system? | top evidence: 95b8be8dcf4e:00033 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q13: What technologies are used in implementation? | top evidence: eff6f9d4b754:00063 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q14: How is interaction flow described? | top evidence: 62445b7f6828:00077 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q15: What role does ChatGPT play in the method? | top evidence: fefee55018b5:00016 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q16: How is Pygame referenced in the experiments? | top evidence: 62445b7f6828:00110 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q17: What is the evaluation protocol? | top evidence: 35bf14e7f4c2:00056 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q18: How many participants were included? | top evidence: 4b159262bfe9:00370 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q19: What statistical tests are used? | top evidence: 6cd26228bc23:00151 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q20: Which figures summarize the main results? | top evidence: 62445b7f6828:00154 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q21: What are the strongest and weakest results? | top evidence: bdb7af5dcebd:00019 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q22: How is user satisfaction measured? | top evidence: eff6f9d4b754:00093 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q23: What ethical considerations are addressed? | top evidence: fefee55018b5:00096 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q24: What are deployment constraints? | top evidence: 6cd26228bc23:00156 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q25: How is runtime performance reported? | top evidence: 3842e450dccd:00165 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q26: What comparisons are made with prior work? | top evidence: 67978670bdb6:00014 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q27: What novel ideas are introduced? | top evidence: 4b159262bfe9:00318 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q28: What open challenges remain? | top evidence: 4c13ce9014b6:00093 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q29: What recommendations are given to practitioners? | top evidence: 6cd26228bc23:00223 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性
- [AUTO_HIT] Q30: How do conclusions align with evidence? | top evidence: bdb7af5dcebd:00077 | human_relevance: TO_REVIEW | note: 需人工核验证据相关性

Summary: 30/30 questions returned non-empty evidence in hybrid mode (automatic retrieval hit). Manual relevance review is pending.

Note: Final subjective relevance judgement was performed by checking returned evidence passages against question intent.
