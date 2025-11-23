From the e2e tests and other tests that the STAR input to both the outreach generation, cover letter generation and the CV generation is not working properly.

One dimension (Dimension A) of it is the lack of full information in the STAR records, which I am working on in parallel.

The other dimension (Dimension B) is the reading, understanding and full in-depth understanding of what a STAR record is what it represents and how it should by ingested by the LLM for it's full meaning.


Explanation of STARs and guardrails about how should the LLM should read them:

A STAR is simply the fully informated representation of a bullet point under the professional experience section of the CV.
It stands for Situation Task Action Result and optionally (Impact) which correspondes to a sellable, impactful work that the candidate did at that company where they were faced with the corresponding Situation (S). They were expected or required to perform a Task (T), which means the company expectation that they had. Tasks usually correspond to responsibilities in a Job Description. Then the user took an Action (A) which means the action that they did to respond to the situation and the task. R stands for Result which is (often preferred quantitative or qualitative) result that it achieved. This result could be in increase in revenue or a decrease in costs or both. It could be qualititative and multi-dimensional e.g. good architecture can reduce cloud costs as well as make onboarding easier. 

There can be more than one STARs at a company. There could be around 20 to 30 STARs for one experience at a particular company. The intention is that the system will either read all STARs and pick the most important ones or compress their meaning without loosing it and give it to the LLMs as system context to generate outreach, write CV etc.

Here is what the entire schema of a single STAR represents.

1. ID: b7e9df84-84b3-4957-93f1-7f1adfe5588c: Is the unqiue ID of a STAR record mainly in order to differentiate it from other and to uniquely identify it.
2. Company: The company name is the name of the company I am working at or I worked at.
3. ROLE TITLE: The title fo the role I am working for. Can we official vs role based hats that I wear.
4. PERIOD: Is the period in which I am working for this role.
5. DOMAIN AREAS: Are the domains that this role touches.
6. BACKGROUND CONTEXT: Tells the complete background context and often explains the whole story, this usually tells the story in a verbose way of the entire STAR. The intention of this is to bring nuance to this STAR and depth so that the LLM can later read the whole context and by super accurate and tailored in representing the STAR for the job.
7. SITUATION: Is one or a list of situtations that in a combination led to a problem or a pain-point that was needed to be solved.
8. TASK: Is one or more Tasks that I had to do, or objectively and expectations that I had to fulfill in order to fulfill the responsbilities of the job in an above satisfactory way.
9. ACTIONS: Are a list of actions that I took to tackle the task at hand solve it.
10. RESULTS: Are a list of results that were the outcome of this situation. They could be short term, mid-term or long-term. They could be multi-dimensional as well. e.g. there could a revenue increase as well risk reduction as well as easier onboarding.
11. IMPACT SUMMARY: Explains the impact I made at the organization, department level.
12. CONDENSED VERSION: is the version of the entire STAR that contains meaningful information for a single dimensional match but might miss depth and nuance.
13. ATS KEYWORDS: are the keywords for that STAR, that should be put on the CV and can optionally be also used to match and score a job description.
14. CATEGORIES: are vertical slices and buzzwords within a tech role that this STAR touches e.g. front-end, backend, data, observability etc.
15. HARD SKILLS: are a list of technical skills that I have used for this STAR in decreasing order of importance
16. SOFT SKILLS:  are a list of soft skills, people and communication skills that I have used for this STAR in decreasing order of importance
17. METRICS: Direct retelling of the results in metrics for adding more nuance
18. METADATA: is database related metadata about the STAR as well.


I am open to:
- Having a better mechnanism to represent the STAR records for the purposes that the LLM has to do less work, also more importantly that the LLM can understand it full depth.
- How to fit the STARs better in the system for good quality generation.
- How to make the STARs ingestion flexible so that as I add more STARs the system gradually improves.
- How to design the bigger picture related to STARs for the best results and the intention that I want to achieve.
