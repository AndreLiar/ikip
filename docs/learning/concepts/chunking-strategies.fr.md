# Concept (FR) — Les stratégies de chunking

_Version française détaillée, compagnon du concept anglais [chunking.md](./chunking.md). Décision : [ADR 0019](../../adr/0019-structure-aware-chunking.md). Cadre la Story 3.1 (Epic 3)._

> Le **chunking est LA décision qui fait ou défait un RAG.** Mal découper = mauvaise récupération, **peu importe la qualité des embeddings**. D'où l'intérêt d'explorer les stratégies avant de coder.

## Le problème que le chunking résout

On ne peut pas embedder un manuel de 100 pages en **un seul vecteur** (il « moyennerait » tout → inutile). Ni **une phrase isolée** (pas assez de contexte). Il faut des **morceaux de la bonne taille** : assez gros pour avoir du sens, assez petits pour être **précis et citables**.

## Les 5 stratégies principales

### 1. Fixed-size (taille fixe)
Découper tous les **N tokens** (ex. 512), avec un chevauchement (**overlap**).
- ✅ Simple, prévisible, rapide
- ❌ **Coupe au milieu des phrases/tableaux** → un chunk peut finir « …le code défaut E » / « 42 nécessite… ». Casse le sens.

### 2. Sentence/paragraph-based (par phrase/paragraphe)
Découper aux **frontières naturelles** (phrases, paragraphes).
- ✅ Respecte le sens, pas de coupure brutale
- ❌ **Tailles très inégales** ; un paragraphe peut être trop long ou trop court

### 3. Structure-aware / document-based (par structure) ⭐
Utiliser la **structure du document** : sections, titres (`3.2 Fault Handling`), tableaux. Un chunk = une section (ou un sous-découpage d'une section trop longue).
- ✅ **Garde les sections cohérentes** → une procédure reste entière
- ✅ **Citations naturelles** (« page 142, section 3.2 ») — crucial pour IKIP
- ❌ Dépend de la qualité de l'extraction de structure (mais on l'a déjà avec `iter_blocks` de la Story 2.4 !)

### 4. Semantic chunking (sémantique)
Découper là où le **sens change** : on embedde phrase par phrase, et on coupe quand deux phrases consécutives sont trop différentes.
- ✅ Frontières « intelligentes » basées sur le sens
- ❌ **Coûte des embeddings à l'avance** (lent, cher), complexe, moins déterministe

### 5. Hierarchical / parent-child (hiérarchique)
Petits chunks pour la **recherche** (précis), mais on renvoie le **parent** (plus gros) au LLM pour le **contexte**.
- ✅ Précision ET contexte
- ❌ Plus complexe à implémenter et stocker

## Pour IKIP concrètement

Les contraintes pointent fort vers **la structure** :
- **Citations précises obligatoires** (FR16) → il faut garder page/section → structure-aware
- **Manuels industriels = très structurés** (sections numérotées, tableaux de codes défaut)
- **La structure est déjà extraite** (`iter_blocks` : heading/paragraph de la Story 2.4)
- **Version-aware** : chaque chunk doit remonter à `document_version` (FR14)

La Story 3.1 dit littéralement « **structure-aware AND semantic** » — d'où un **hybride pragmatique** :

> **Structure d'abord** (découper par section/heading), **puis** si une section dépasse la taille max, la **sous-découper** par frontières de phrase/paragraphe avec un petit **overlap**. Chaque chunk garde sa **section** + sa **page**.

C'est le meilleur compromis : **cohérence structurelle + tailles contrôlées + citabilité**, sans le coût du semantic-chunking pur (qui demande des embeddings **avant même** d'embedder — circulaire et cher).

## Tableau de décision

| Stratégie | Cohérence | Citable | Coût | Complexité | Fit IKIP |
|---|---|---|---|---|---|
| Fixed-size | ❌ | moyen | $ | simple | ✘ coupe le sens |
| Sentence/para | ✅ | moyen | $ | simple | ~ tailles inégales |
| **Structure-aware (+ sous-découpe)** | ✅✅ | ✅✅ | $ | moyen | ⭐ **recommandé** |
| Semantic | ✅✅ | moyen | $$$ | complexe | ✘ cher/circulaire |
| Hierarchical | ✅✅ | ✅ | $$ | complexe | 🔮 extension future |

## La décision (actée)

**Structure-aware avec sous-découpe bornée** pour le MVP (réutilise `iter_blocks`, garde page/section, tailles contrôlées). Le **hierarchical (parent-child)** est une excellente **extension post-MVP** si la qualité de récupération le demande.

> Enregistrement de décision complet (contexte, conséquences, alternatives, revisit) : [ADR 0019](../../adr/0019-structure-aware-chunking.md). Implémentation : `services/document-processing/src/ikip_docproc/chunking.py` (Story 3.1).

## À retenir
1. **Structure d'abord**, sous-découpe seulement si la section est trop longue.
2. Garder les **sections/tableaux/procédures entières** — ne pas couper en plein milieu.
3. **Overlap** aux frontières de sous-découpe pour le contexte.
4. Tailler en **tokens**, pas en caractères.
5. Chaque chunk **remonte** à document/version/page/section (citations).

## Voir aussi
- Concept anglais (plus concis) : [chunking.md](./chunking.md) · pourquoi le RAG : [why-rag.md](./why-rag.md) · structure du texte : [data-validation.md](./data-validation.md) (`iter_blocks`).
- Décision : [ADR 0019](../../adr/0019-structure-aware-chunking.md).
