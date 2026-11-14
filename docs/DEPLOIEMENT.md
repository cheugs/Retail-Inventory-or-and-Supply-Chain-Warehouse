# Mettre le tableau de bord en ligne (gratuit)

[English version](en/DEPLOYMENT.md)

Le tableau de bord en ligne est un **site statique** : du HTML, du CSS et du JavaScript qui lisent
`dashboard/static/data/snapshot.json`, une copie des résultats d'une vraie exécution du pipeline.
Il n'a donc besoin ni de base de données, ni de serveur Python. Conséquences :

- l'hébergement est gratuit sur plusieurs plateformes ;
- la page s'ouvre tout de suite (un site statique ne "s'endort" pas, contrairement à un service web gratuit) ;
- les chiffres sont ceux de la dernière exportation, pas des données en direct. La chaîne complète
  (PostgreSQL, Airflow, dbt) tourne en local avec Docker.

## Option 1 : GitHub Pages (utilisée pour la démo)

Adresse : https://cheugs.github.io/Retail-Inventory-or-and-Supply-Chain-Warehouse/

Rien à configurer : le workflow `.github/workflows/pages.yml` copie `dashboard/static` dans la
branche `gh-pages` à chaque push qui modifie le tableau de bord, et GitHub Pages sert cette branche.
Si le site n'apparaît pas : **Settings** > **Pages** > *Source* : **Deploy from a branch**,
branche `gh-pages`, dossier `/ (root)`.

## Option 2 : Render

Le fichier `render.yaml` à la racine décrit déjà le site.

1. Créer un compte gratuit sur https://render.com (connexion avec GitHub).
2. **New** > **Blueprint**, puis choisir le dépôt `Retail-Inventory-or-and-Supply-Chain-Warehouse`.
3. Render lit `render.yaml` et crée le service `retail-warehouse-dashboard` (type *Static Site*). Valider.
4. Après une minute, le site est disponible à une adresse du type
   `https://retail-warehouse-dashboard.onrender.com`.

Chaque `git push` sur `main` redéploie le site automatiquement.

Sans Blueprint : **New** > **Static Site**, dépôt, *Build Command* vide (ou `echo ok`),
*Publish Directory* `dashboard/static`.

Attention : choisir **Static Site**, pas *Web Service*. Un *Web Service* essaie de lancer une
application Python et échoue (il n'y a pas de serveur à démarrer pour la démo).

## Option 3 : Netlify ou Vercel

Importer le dépôt, laisser la commande de build vide et indiquer `dashboard/static` comme
dossier de publication.

## Mettre à jour les chiffres du site

```bash
python -m retail_pipeline.run all         # pipeline complet, écrit aussi le snapshot
git add dashboard/static/data/snapshot.json
git commit -m "Update dashboard snapshot"
git push
```

## Ce que voit un recruteur

Le site affiche dans la barre latérale la source des données ("snapshot JSON" en ligne,
"base en direct" en local) et la date de mise à jour. Le pied de page rappelle que les
données sont synthétiques.
