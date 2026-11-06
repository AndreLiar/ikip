# Pourquoi LangGraph (et pas seulement LangChain) ?

_Version française de [`why-langgraph.md`](./why-langgraph.md). Document d'accompagnement de l'[ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md). Répond à : « Je comprends que LangChain fournit les briques AI — qu'apporte LangGraph ? »_

---

## Réponse en une phrase

> **LangChain fournit les briques. LangGraph est le contrôleur** qui décide *quelle* brique s'exécute ensuite, fait circuler l'état entre elles, gère les branches, les boucles, les points de reprise, et rend tout le chemin de décision inspectable.

LangChain = les composants (client LLM, retriever, templates de prompt, parsers de sortie, wrappers d'outils).
LangGraph = la **machine à états / le câblage** autour de ces composants.

Si le flux d'IKIP était une ligne droite — *récupérer → insérer dans le prompt → appeler le LLM → renvoyer* — une simple chaîne LangChain suffirait. Mais ce n'est pas le cas : le flux est plein de **décisions**, et c'est précisément le vide que LangGraph comble.

---

## Le flux n'est pas linéaire — il est plein de décisions

Une vraie requête IKIP : *« Panne sur cet équipement — trouve la procédure de maintenance applicable pour ce modèle et cette révision. »*

```
autoriser ? ──non──▶ 403 (stop)
   │oui
analyser → identifier le modèle / la révision de l'équipement
   │
récupération hybride (filtrée par ce modèle / cette révision)
   │
reclassement (rerank)
   │
preuve suffisante ? ──non──▶ ABSTENTION (« preuve insuffisante »)   ◀── branche critique de sécurité
   │oui
générer une réponse citée + afficher les avertissements de sécurité
```

Trois choses ici qu'une chaîne linéaire ne peut pas exprimer proprement :

1. **Un verrou** (`autoriser ?`) qui peut tout arrêter *avant toute récupération* — autorisation avant récupération (FR21).
2. **Une branche** (`preuve suffisante ?`) où un chemin répond et l'autre *refuse* — abstention (FR17), le comportement de sécurité le plus important du projet.
3. **Un état** qui s'accumule au fil des étapes : la requête → modèle/révision identifié → chunks récupérés → scores de rerank → verdict de suffisance → citations → trace.

---

## Important : LangGraph ne décide pas « par magie » — *c'est toi* qui déclares les décisions

Une idée reçue fréquente : LangGraph déciderait tout seul quand utiliser quelle brique. Non. **C'est toi** qui définis le graphe — les **nœuds** (les étapes) et les **arêtes conditionnelles** (les décisions) — et LangGraph exécute cette logique de façon fiable, avec l'état et la traçabilité.

Dans IKIP, *c'est toi* qui écris la règle :
> *« autoriser d'abord ; puis identifier l'équipement ; puis récupérer ; et **SI** la preuve est insuffisante **ALORS** s'abstenir, **SINON** générer une réponse citée. »*

Le rôle de LangGraph est d'exécuter cette logique déclarée de manière fiable — en faisant circuler l'**état** partagé entre les étapes, en prenant la branche que tu as spécifiée, en bouclant ou en reprenant si nécessaire, et en gardant tout le chemin **inspectable** (→ `QueryTrace`).

La formulation exacte :

> LangGraph est la **machine à états** qui enchaîne les briques LangChain selon des **décisions explicites que tu as définies**, en faisant circuler un **état** entre les étapes, et en gardant tout **traçable et reprenable**.

Répartition des rôles, dite simplement :
- **Brique LangChain** = fait le travail (parler au LLM, interroger le vector store, parser une sortie).
- **Graphe LangGraph** = décide la séquence : *« d'abord autoriser, puis identifier l'équipement, puis récupérer, et SI pas assez de preuves ALORS s'abstenir. »*

La vraie valeur n'est donc pas « ça connecte des briques » — c'est que **tes règles de décision + la mémoire de l'état + la traçabilité** deviennent des éléments de premier plan, testables, ce qui rend l'abstention et la sécurité *prouvables* (Story 5.3) plutôt que cachées dans le texte d'un prompt.

---

## Ce que LangGraph apporte concrètement à IKIP

| Capacité | Pourquoi IKIP en a besoin | Rattaché à |
|---|---|---|
| **État partagé explicite** | Chaque nœud lit/écrit un même objet State ; pas besoin de passer des dictionnaires à la main entre les étapes. | Flux cœur, Epic 3 |
| **Branches conditionnelles** | `autorisé ?`, `suffisant ?` → répondre vs **s'abstenir**. C'est *la* logique de sécurité. | FR17, FR21 · Story 3.5, 5.3 |
| **Boucles / reprises / auto-correction** | Si la récupération est faible, relancer avec des filtres assouplis ou re-ranker avant d'abandonner — un cycle, ce que les chaînes (DAG) ne permettent pas. | FR12, FR14 |
| **Checkpointing / reprise durable** | Sauvegarder l'état par nœud ; reprendre après une panne ; exécution durable et auditable. | NFR3 (fiabilité) |
| **Humain dans la boucle** | Mettre en pause pour qu'un technicien confirme l'identité de l'équipement avant de continuer — interruption/reprise native. | Limites de sécurité (brief §9) |
| **Observabilité au niveau du nœud** | Chaque nœud est une unité distincte et traçable → correspond directement à `QueryTrace` ; on voit exactement quel chemin une requête a pris et pourquoi elle s'est abstenue. | FR30 · Story 5.4 |

---

## « Je ne pourrais pas tout construire en Python pur (sans LangChain, sans LangGraph) ? »

**Si — et c'est la vérité honnête.** Rien ici n'a *besoin* de l'une ou l'autre bibliothèque :
- Une « brique AI » = un appel d'API LLM, une requête pgvector, un parsing JSON — du Python pur.
- L'orchestration = un `dict` d'état + des `if/else` + des boucles + `try/except` + du logging — du Python pur.

Ni LangChain ni LangGraph n'apportent une capacité que Python n'a pas. Ce sont des **frameworks, pas des super-pouvoirs.** La vraie question n'est donc pas *possible vs impossible* — c'est **build vs buy** : qu'acceptes-tu de réimplémenter et de maintenir toi-même ?

Si tu écris le graphe à la main en Python pur, voici ce que tu finis par réécrire — et ce que LangGraph fournit déjà :

| Fonctionnalité | En Python pur, tu dois… |
|---|---|
| **État persistant + checkpointing** | construire une couche qui sauvegarde l'état après chaque étape (ex. dans Postgres) |
| **Reprise après crash** (resume par `thread_id`) | coder la logique de « reprendre au bon nœud » |
| **Streaming** des étapes/tokens intermédiaires | gérer le streaming toi-même |
| **Human-in-the-loop** (pause → attente → reprise) | bâtir la plomberie pause/persist/reprise |
| **Graphe inspectable et standard** | ton `if/else` est un flux de contrôle *bespoke*, unique à ton code |
| **Intégration du traçage** (LangSmith, etc.) | instrumenter chaque étape à la main |

La valeur de LangGraph n'est donc **pas** « il permet des décisions » (le `if/else` le fait déjà) — c'est qu'il t'évite de **réimplémenter et maintenir** l'état durable, le checkpointing, le streaming et le human-in-the-loop, et qu'il te donne un **artefact graphe standard et inspectable** au lieu d'une tuyauterie maison.

**C'est un vrai arbitrage, dans les deux sens.** Le Python pur est un choix légitime — surtout tant que le flux reste simple — et le framework a de vrais coûts : une dépendance de plus, des abstractions à apprendre, et des versions qui bougent vite (LangChain/LangGraph changent souvent). Le framework ne « gagne sa place » que lorsque tu as réellement besoin de reprise durable, de streaming et de human-in-the-loop, et que tu ne veux pas être propriétaire de cette infra.

**Une raison honnête, propre à ce projet :** le brief d'IKIP fixe un *objectif d'apprentissage* explicite — maîtriser LangChain / LangGraph / Dagster, des outils standards de l'industrie. Pour un mémoire/portfolio, les *démontrer* est un but en soi. C'est une raison valable — mais **pédagogique/portfolio**, nommée comme telle, pas une nécessité technique.

Quel que soit ton choix, les garanties de sécurité viennent des tests, pas de l'outil : l'ensemble de tests d'abstention (Story 5.3, un verrou bloquant pour la release) et les verrous de régression prompt/graphe (Story 5.5) sont ce qui rend le comportement *prouvable* — LangGraph rend simplement cette structure plus facile à exprimer et à inspecter.

---

## Analogie

- **LangChain** = des briques Lego + moteurs + capteurs (les pièces).
- **LangGraph** = le contrôleur programmable + le schéma de câblage qui lit les capteurs et décide quel moteur actionner ensuite — et qui peut s'arrêter en toute sécurité quand une mesure dit *« pas assez de preuves »*.

---

## Comment les deux apparaissent dans les diagrammes

| Diagramme | LangGraph | LangChain |
|---|---|---|
| [Contexte système](./img/01_system_context.png) | sur l'étiquette du nœud RAG | sur la même étiquette |
| [Flux RAG](./img/03_rag_workflow.png) | la chaîne de nœuds (flux principal / trait plein) | dépendance de support (pointillés « uses integrations ») |

Le placement est voulu : **traits pleins = le flux orchestré (LangGraph) ; pointillés = la bibliothèque dont les nœuds dépendent (LangChain).**

---

## En résumé

LangChain intègre les modèles, les retrievers et les outils. LangGraph est le contrôleur **à états, conditionnel et auditable** qui transforme ces intégrations en un flux RAG fiable, testable et sûr. Tu *pourrais* tout construire à la main en Python pur — rien ici n'est exclusif aux frameworks — mais le graphe est l'endroit où la logique de décision, l'état et l'auditabilité sont les plus faciles à exprimer, tester et inspecter, et (pour ce projet) il démontre aussi un outil standard de l'industrie, ce qui est un objectif d'apprentissage affiché. C'est ça le vrai argument — build-vs-buy + pédagogie — et non que le `if/else` serait incapable.

> Enregistrement de décision : [ADR 0002 — Double orchestration](../adr/0002-dual-orchestration-dagster-langgraph.md). Voir son « Revisit When » : un système trivialement petit *pourrait* se réduire à LangChain seul ; ce sont les besoins d'abstention, d'autorisation et d'audit d'IKIP qui justifient le graphe.
