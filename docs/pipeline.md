# Graphe du pipeline AutoDev

Genere automatiquement depuis `src/agent_orchestrateur/graphe.py` : ne pas modifier a la main,
relancer `make graphe` apres toute modification du graphe.

- trait plein : enchainement inconditionnel
- pointilles : decision du routage (`ok` / `corriger` / `abandon` / `continuer`)

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	po(po)
	architect(architect)
	test_agent(test_agent)
	developer(developer)
	qa_backend(qa_backend)
	correction_backend(correction_backend)
	frontend(frontend)
	qa_frontend(qa_frontend)
	correction_frontend(correction_frontend)
	dockerization(dockerization)
	validation_docker(validation_docker)
	correction_docker(correction_docker)
	echec(echec)
	__end__([<p>__end__</p>]):::last
	__start__ --> po;
	architect -. &nbsp;abandon&nbsp; .-> echec;
	architect -. &nbsp;continuer&nbsp; .-> test_agent;
	correction_backend -. &nbsp;abandon&nbsp; .-> echec;
	correction_backend -. &nbsp;continuer&nbsp; .-> qa_backend;
	correction_docker -. &nbsp;abandon&nbsp; .-> echec;
	correction_docker -. &nbsp;continuer&nbsp; .-> validation_docker;
	correction_frontend -. &nbsp;abandon&nbsp; .-> echec;
	correction_frontend -. &nbsp;continuer&nbsp; .-> qa_frontend;
	developer -. &nbsp;abandon&nbsp; .-> echec;
	developer -. &nbsp;continuer&nbsp; .-> qa_backend;
	dockerization -. &nbsp;abandon&nbsp; .-> echec;
	dockerization -. &nbsp;continuer&nbsp; .-> validation_docker;
	frontend -. &nbsp;abandon&nbsp; .-> echec;
	frontend -. &nbsp;continuer&nbsp; .-> qa_frontend;
	po -. &nbsp;continuer&nbsp; .-> architect;
	po -. &nbsp;abandon&nbsp; .-> echec;
	qa_backend -. &nbsp;corriger&nbsp; .-> correction_backend;
	qa_backend -. &nbsp;abandon&nbsp; .-> echec;
	qa_backend -. &nbsp;ok&nbsp; .-> frontend;
	qa_frontend -. &nbsp;corriger&nbsp; .-> correction_frontend;
	qa_frontend -. &nbsp;ok&nbsp; .-> dockerization;
	qa_frontend -. &nbsp;abandon&nbsp; .-> echec;
	test_agent -. &nbsp;continuer&nbsp; .-> developer;
	test_agent -. &nbsp;abandon&nbsp; .-> echec;
	validation_docker -. &nbsp;ok&nbsp; .-> __end__;
	validation_docker -. &nbsp;corriger&nbsp; .-> correction_docker;
	validation_docker -. &nbsp;abandon&nbsp; .-> echec;
	echec --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
