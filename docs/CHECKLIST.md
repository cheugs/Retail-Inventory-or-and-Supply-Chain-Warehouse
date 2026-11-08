# Checklist qualité et acceptation (DE02)

[English version](en/CHECKLIST.md)

La checklist DE02 a été écrite pour une plateforme **temps réel** de transactions financières
(Kafka, Spark). Ce projet est un **entrepôt de données batch** pour le retail (Python, dbt, Airflow,
PostgreSQL). Chaque critère est donc traduit vers son équivalent batch, puis relié à sa preuve
dans le code. Quand un critère n'a pas de sens ici (par exemple le lag d'un consommateur Kafka),
cela est dit clairement, avec l'équivalent retenu.

Légende : **Oui** = fait et testé · **Adapté** = équivalent batch du critère · **Partiel** = fait en partie, limite expliquée

## Correspondance des notions temps réel vers batch

| Notion de la checklist (streaming) | Equivalent dans ce projet (batch) |
|---|---|
| Transaction | Ligne de ticket de caisse (`sale_line_id`), mais aussi relevé de stock, ligne de commande, livraison |
| Ingestion par Kafka | Fichiers journaliers déposés par les systèmes sources + manifeste, chargés par `retail_pipeline/ingest.py` |
| Traitement continu par Spark | Exécution quotidienne orchestrée par Airflow (`catchup`), modèles dbt incrémentaux |
| Temps d'événement / temps de traitement | `sold_at` (moment de la vente) / `_batch_date` et `_loaded_at` (moment où la ligne arrive) |
| Watermark pour les retards | Lignes retraitées : nouvelles depuis le dernier run, produits modifiés, produits inconnus, et fenêtre de 3 jours |
| Lag du consommateur Kafka | Retard d'arrivée des lignes (`arrival_delay_days`) et durée de chaque étape (`audit.pipeline_runs`) |
| Checkpoints | Etat incrémental = `max(_loaded_at)` des tables de faits ; chargement d'un jour = une transaction |
| Rejeu d'événements | Rechargement d'un jour, backfill Airflow, ou reconstruction complète depuis la couche raw (`replay`) |
| Indicateurs de fraude simulés | Indicateurs d'anomalie simulés : baisse de stock inexpliquée, prix de caisse anormal |

## 1. Exactitude fonctionnelle

| Critère | Statut | Preuve |
|---|---|---|
| Les transactions ont des attributs réalistes | Oui | `generate.py` : prix par catégorie, marge 30 à 90 %, saisonnalité semaine, promotions, remises. Test `test_sales_have_realistic_values` |
| Chaque transaction a un identifiant unique | Oui | `sale_line_id` ; test dbt `unique` sur `fct_sales.sale_line_id`, test `test_every_sale_line_counted_once` |
| Montants, devises et horodatages valides | Oui | Règles dans `stg_sales_checked.sql` (quantité > 0, prix >= 0, devise connue, horodatage lisible et pas dans le futur) |
| Les événements sont ingérés | Adapté | Fichiers chargés par COPY dans `raw.*`, journal dans `audit.load_log`, contrôle ligne à ligne contre le manifeste |
| Traitement continu | Adapté | DAG Airflow quotidien `retail_warehouse_daily` (voir section 3) |
| Agrégations mathématiquement justes | Oui | Test dbt `assert_mart_sales_matches_fact`, contrôle `revenue_mart_vs_fact` dans `reconcile.py` |
| PostgreSQL contient les résultats attendus | Oui | Tests d'intégration sur une vraie base (`tests/integration`) |
| Le tableau de bord correspond à la base | Oui | `test_dashboard_figures_match_the_database` (KPI, lignes, OTIF, API FastAPI) |

## 2. Qualité et intégrité des données

| Critère | Statut | Preuve |
|---|---|---|
| Champs obligatoires manquants détectés | Oui | Motifs `missing_sale_line_id`, `missing_store_id`, `missing_product_id`, `missing_key` ; colonne obligatoire absente : `SchemaError` |
| Montants invalides rejetés | Oui | `invalid_quantity`, `invalid_price` |
| Horodatages invalides gérés | Oui | `invalid_timestamp`, `future_timestamp`, `invalid_date` (macro `try_cast` + `pg_input_is_valid`) |
| Identifiants en double détectés | Oui | `duplicate_sale_line_id`, `duplicate_po_line_id`, `duplicate_delivery_id`, `replaced_by_newer_count` |
| Les doublons ne gonflent pas les montants | Oui | `test_duplicates_do_not_inflate_amounts`, ligne envoyée deux fois comptée une fois (`test_next_run_fixes_early_sale_and_late_price_change`) |
| Données invalides isolées des valides | Oui | Schéma `quarantine` (4 tables), avec le motif et la ligne brute |
| Transformations qui préservent l'intégrité | Oui | Test `assert_every_raw_sale_is_accounted_for` : raw = faits + quarantaine ; `assert_sales_amounts_are_consistent` |
| Règles qualité testées automatiquement | Oui | 48 tests dbt à chaque `dbt build`, plus les tests pytest |

## 3. Traitement des données en retard (équivalent du temps réel)

| Critère | Statut | Preuve |
|---|---|---|
| Traitement sans lancement manuel | Adapté | Airflow planifie un run par jour ; capteur `wait_for_source_files` |
| Temps d'événement distinct du temps de traitement | Oui | `sold_at` vs `_batch_date` / `_loaded_at` ; colonnes `arrival_delay_days`, `is_late_arrival` |
| Evénements dans le désordre gérés | Oui | Historique SCD2 reconstruit depuis toutes les lignes reçues, dans l'ordre de `updated_at` ; mise à jour catalogue en retard testée |
| Evénements en retard gérés (watermark) | Adapté | Filtre incrémental de `fct_sales` (nouvelles lignes, produits modifiés, produit inconnu, fenêtre `lookback_days`) ; `test_late_sale_lands_on_its_real_day` |
| Agrégations par fenêtre exactes | Adapté | Agrégations par jour et par mois (`mart_*`), vérifiées contre les faits |
| Latence mesurable | Adapté | Durée de chaque étape dans `audit.pipeline_runs` ; délai d'arrivée des lignes |
| Débit mesurable | Oui | `benchmarks/run_benchmark.py` (lignes/s) |
| Lag observable | Adapté | Pas de Kafka : on observe le retard des données (`arrival_delay_days`) et la fraîcheur (`loaded_at_field` des sources dbt) |

## 4. Fiabilité et tolérance aux pannes

| Critère | Statut | Preuve |
|---|---|---|
| Reprise après redémarrage | Oui | Chaque étape est idempotente : un run relancé reprend sans effet de bord |
| Les checkpoints conservent l'avancement | Adapté | Etat incrémental stocké dans les tables de faits ; Airflow garde l'état de chaque jour |
| Les échecs peuvent être relancés | Oui | `retries: 2` dans le DAG ; `test_crash_during_a_batch_rolls_back_everything` (relance réussie) |
| Un double traitement ne corrompt pas la base | Oui | Chargement : suppression puis insertion du lot ; faits : `delete+insert` sur la clé ; `test_reloading_a_day_is_idempotent` |
| Rejeu de l'historique possible | Oui | `python -m retail_pipeline.run replay` ; `test_full_replay_gives_the_same_result` |
| La reprise ne perd pas de données en silence | Oui | Un lot = une transaction (tout ou rien) + rapprochement avec le manifeste source |
| Changements de schéma maîtrisés | Oui | Colonne optionnelle absente = NULL, colonne inconnue ignorée et journalisée, colonne obligatoire absente = arrêt ; tests unitaires et d'intégration |
| Garanties de livraison documentées et testées | Oui | "Exactement une fois" au niveau du résultat : voir README section 8, tests d'idempotence et de doublons |

## 5. Architecture des données

| Critère | Statut | Preuve |
|---|---|---|
| Responsabilités claires | Oui | Générateur, ingestion, dbt, rapprochement, export, tableau de bord : un module chacun |
| Topics et partitions Kafka | Non applicable | Pas de Kafka. Equivalent : un fichier par entité et par jour, une table raw par entité, index sur `_batch_date` |
| Flux traçables | Oui | `_batch_date`, `_file_name`, `_row_number` gardés jusqu'à `fct_sales.source_file` et dans la quarantaine |
| Brut et transformé séparés | Oui | Schémas `raw`, `staging`, `marts`, `quarantine`, `audit` |
| Tables PostgreSQL bien structurées | Oui | Schéma en étoile : 3 faits, 4 dimensions, clés de substitution, tests de relations |
| Index justifiés | Oui | Commentaires dans `sql/01_raw_and_audit.sql` (rechargement par lot, filtre incrémental) |
| Transformations dbt modulaires | Oui | Couches staging / intermediate / marts, macros multi-bases |
| Architecture extensible | Oui | Cible Snowflake prévue dans `profiles.yml`, macros `adapter.dispatch`, nouvelle source = une entrée dans `ENTITIES` + un modèle staging |

## 6. Performance et passage à l'échelle

| Critère | Statut | Preuve |
|---|---|---|
| Au moins 10 000 transactions | Oui | Benchmark 10k et jeu de démo (environ 159 000 lignes de vente) |
| Testé avec 100 000 transactions | Oui | Benchmark 100k |
| Benchmark à 1 million tenté | Oui | Benchmark 1m (`benchmarks/results.md`) |
| Débit en lignes par seconde | Oui | Colonne "Rows/s" du benchmark |
| Latence mesurée | Adapté | Durée de l'ingestion, du `dbt build` et du rapprochement |
| Ressources surveillées | Partiel | Taille de la base et mémoire du conteneur PostgreSQL ; pas de suivi CPU détaillé |
| Goulots d'étranglement identifiés | Oui | Modèles dbt les plus lents (lus dans `run_results.json`) et analyse dans le README section 9 |
| Résultats documentés | Oui | README section 9, `benchmarks/results.md` |

## 7. Supervision et observabilité

| Critère | Statut | Preuve |
|---|---|---|
| Ingestion suivie | Oui | `audit.load_log` (lignes, colonnes inconnues, statut), page "Qualité et pipeline" |
| Echecs journalisés | Oui | `audit.pipeline_runs` (statut `failed` + message), logs Python et Airflow |
| Lag suivi | Adapté | Retard d'arrivée des lignes (graphique du tableau de bord) |
| Retards de traitement suivis | Oui | Durée moyenne par étape |
| Doublons comptés | Oui | Quarantaine, motif `duplicate_*` |
| Lignes invalides comptées | Oui | Quarantaine, par motif |
| Reprises traçables | Oui | Chaque essai a son `run_id` ; les lignes `failed` puis `success` restent visibles |
| Logs suffisants pour enquêter | Oui | Lot, fichier et numéro de ligne gardés pour chaque ligne ; écarts du rapprochement détaillés par jour |

## 8. Analyses métier (équivalent des analyses financières)

| Critère | Statut | Preuve |
|---|---|---|
| Volumes calculés | Oui | Unités vendues, lignes, commandes |
| Montants totaux calculés | Oui | Chiffre d'affaires, coût, marge (EUR) |
| Répartition par statut | Oui | Statut des lignes de commande (complète, partielle, en retard, ouverte) |
| Volumes par fenêtre de temps | Oui | Par jour, par jour de semaine, par mois |
| Différences de devises gérées | Oui | Magasins suisses en CHF, conversion au taux du jour (`test_amounts_are_converted_to_eur`) |
| Indicateurs d'activité suspecte simulés | Adapté | `mart_anomaly_indicators` : baisse de stock inexpliquée, écart de prix |
| Règles explicables | Oui | La règle est écrite dans la colonne `rule` de chaque ligne |
| Aucune prétention de détection réelle | Oui | Dit dans le modèle, le tableau de bord et le README |

## 9. Tests et validation

| Critère | Statut | Preuve |
|---|---|---|
| Tests unitaires | Oui | `tests/unit` (générateur, schéma des fichiers, fichiers du projet) |
| Tests d'intégration | Oui | `tests/integration` (vraie base PostgreSQL + dbt) |
| Tests de bout en bout | Oui | Génération -> ingestion -> dbt -> rapprochement -> tableau de bord ; étape CI `run all` |
| Doublons testés | Oui | `test_duplicates_do_not_inflate_amounts` |
| Données en retard testées | Oui | `test_late_sale_lands_on_its_real_day` |
| Désordre testé | Oui | Mise à jour de prix datée du jour 56 reçue le jour 58 |
| Panne de l'application testée | Oui | `test_crash_during_a_batch_rolls_back_everything` |
| Rejeu testé | Oui | `test_full_replay_gives_the_same_result` |
| Evolution de schéma testée | Oui | `test_schema_evolution_is_handled`, `test_file_with_missing_mandatory_column_is_refused` |
| Tableau de bord validé contre la base | Oui | `test_dashboard_figures_match_the_database` |

## 10. Qualité d'ingénierie

| Critère | Statut | Preuve |
|---|---|---|
| Code modulaire et maintenable | Oui | Un module par étape, code commenté en anglais |
| Configuration externalisée | Oui | `.env` / variables d'environnement, `vars` dbt |
| Pas de secret sur GitHub | Oui | `.env` ignoré, `.env.example` seulement ; test `test_no_password_written_in_config_files` |
| Services Docker reproductibles | Oui | `docker-compose.yml`, versions d'images fixées |
| CI qui lance les tests | Oui | `.github/workflows/ci.yml` (PostgreSQL de service) |
| README qui explique l'architecture | Oui | Sections 4 et 5 |
| Choix et compromis documentés | Oui | Section 8 |
| Limites reconnues | Oui | Section 14 |
| Reproductible par un autre développeur | Oui | Section 13 (Docker ou Python seul) |
