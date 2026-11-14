# Démo en ligne : données mises à jour chaque jour

[English version](en/DEPLOYMENT.md)

## Comment ça marche

```mermaid
flowchart LR
    GA["GitHub Actions<br/>chaque jour 05:30 UTC"] -->|"simule la journée d'hier<br/>ingest, dbt build, rapprochement"| N[("Neon<br/>PostgreSQL gratuit")]
    GA -->|"snapshot.json du jour"| GP["GitHub Pages<br/>tableau de bord statique"]
    N --> R["Render (optionnel)<br/>tableau de bord en direct"]
```

- **L'entreprise en ligne** est une version plus petite que la démo locale (4 magasins, 120 produits,
  10 fournisseurs), qui a "ouvert" le 1er septembre 2026. Chaque matin, le workflow
  `.github/workflows/daily-load.yml` simule la journée d'hier et la charge dans l'entrepôt hébergé sur
  **Neon**, avec exactement le même code que la version locale (`python -m retail_pipeline.run live-update`) :
  ingestion, `dbt build` avec ses 48 tests, rapprochement. L'historique grandit donc d'un jour par jour.
- **GitHub Pages** (https://cheugs.github.io/Retail-Inventory-or-and-Supply-Chain-Warehouse/) reçoit
  ensuite les chiffres du jour. La page s'ouvre tout de suite et la date "Mis à jour" change chaque jour.
- **Render** (optionnel) sert le même tableau de bord en lisant Neon en direct. Le plan gratuit se met en
  veille : le premier chargement peut prendre environ une minute.

La simulation repart toujours du 1er septembre avec la même graine aléatoire et le même horizon de
planification : les jours déjà chargés sont générés à l'identique, et seul le nouveau jour est chargé
(test `test_one_more_day_does_not_change_the_past`).

## A faire une seule fois

### 1. Créer la base Neon (gratuit, environ 3 minutes)

1. Créer un compte sur https://neon.tech (connexion avec GitHub possible).
2. **Create project** : nom `retail-warehouse`, PostgreSQL 16 ou plus, région Europe (Frankfurt).
3. Sur la page du projet, bouton **Connect** : copier la chaîne de connexion. Elle ressemble à
   `postgresql://utilisateur:motdepasse@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`.

Ne collez cette chaîne ni dans le code ni dans un fichier suivi par Git : elle contient le mot de passe.

### 2. Donner la chaîne à GitHub (secret)

1. Sur GitHub, dans le dépôt : **Settings** > **Secrets and variables** > **Actions** > **New repository secret**.
2. Nom : `NEON_DATABASE_URL`, valeur : la chaîne copiée. **Add secret**.
3. Onglet **Actions** > **Daily load (live demo)** > **Run workflow**. Le premier passage charge tout
   l'historique depuis le 1er septembre (environ 5 à 10 minutes) puis publie le tableau de bord.
   Ensuite, il tourne seul chaque matin.

### 3. (Optionnel) Tableau de bord en direct sur Render

1. Compte gratuit sur https://render.com (connexion avec GitHub).
2. **New** > **Blueprint**, choisir le dépôt. Render lit `render.yaml` (service `retail-warehouse-live`,
   construit avec le `Dockerfile` à la racine).
3. Render demande la valeur de `DATABASE_URL` : coller la même chaîne Neon. Valider.
4. Après quelques minutes, le site est disponible. Adresse de ce projet : https://retail-warehouse-live-8lnt.onrender.com La barre latérale affiche "base en direct".

Si la base ne répond pas, le serveur affiche le dernier snapshot enregistré au lieu d'une erreur.

## Limites du plan gratuit

- Neon : 0,5 Go de stockage. L'entreprise en ligne utilise environ 1 Mo par jour, soit environ 370 Mo
  après un an. Pour repartir de zéro : vider la base Neon et changer `SIM_START_DATE` dans
  `daily-load.yml`.
- Neon se met en pause sans activité : la première requête du matin le réveille (quelques secondes).
- Render se met en veille après 15 minutes sans visite.
- Les workflows planifiés de GitHub peuvent démarrer avec un peu de retard, et GitHub les désactive
  si le dépôt n'a aucune activité pendant 60 jours (un clic sur **Enable workflow** les relance).

## Mettre à jour la démo de référence (90 jours)

Les résultats du README (section 9) viennent du jeu de démo local de 90 jours. Le fichier
`dashboard/static/data/snapshot.json` du dépôt en est une copie ; il sert de secours tant que le
workflow quotidien n'a pas tourné.

```bash
python -m retail_pipeline.run all
git add dashboard/static/data/snapshot.json
git commit -m "Update reference snapshot"
git push
```
