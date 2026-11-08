# Connecter Power BI à l'entrepôt

[English version](en/POWERBI.md)

Le schéma `marts` est prévu pour être lu directement par Power BI : un schéma en étoile avec des
clés de substitution, déjà nettoyé et testé. Ce dépôt ne contient pas de fichier `.pbix` (format
binaire, difficile à relire dans Git) ; ce guide décrit le modèle à reproduire.

## 1. Connexion

1. Power BI Desktop > **Obtenir les données** > **Base de données PostgreSQL**.
2. Serveur : `localhost:5433`, base : `retail_dw` (valeurs du fichier `.env`).
3. Mode **Import** (les données changent une fois par jour).
4. Sélectionner dans le schéma `marts` : `fct_sales`, `fct_inventory_daily`, `fct_purchase_order_lines`,
   `dim_product`, `dim_store`, `dim_supplier`, `dim_date`.

## 2. Relations (vue Modèle)

| Table de faits | Colonne | Dimension | Colonne | Cardinalité |
|---|---|---|---|---|
| fct_sales | date_key | dim_date | date_key | plusieurs à un |
| fct_sales | product_key | dim_product | product_key | plusieurs à un |
| fct_sales | store_key | dim_store | store_key | plusieurs à un |
| fct_inventory_daily | date_key | dim_date | date_key | plusieurs à un |
| fct_inventory_daily | product_key | dim_product | product_key | plusieurs à un |
| fct_inventory_daily | store_key | dim_store | store_key | plusieurs à un |
| fct_purchase_order_lines | order_date_key | dim_date | date_key | plusieurs à un |
| fct_purchase_order_lines | supplier_key | dim_supplier | supplier_key | plusieurs à un |
| fct_purchase_order_lines | product_key | dim_product | product_key | plusieurs à un |

Filtrage dans un seul sens (de la dimension vers le fait). `dim_product` contient une ligne par
**version** du produit (SCD type 2) : pour filtrer "le produit" sans tenir compte des versions,
utiliser la colonne `product_id`.

## 3. Mesures DAX

```DAX
Chiffre d'affaires = SUM ( fct_sales[net_amount_eur] )
Coût des ventes    = SUM ( fct_sales[cost_amount_eur] )
Taux de marge      = DIVIDE ( [Chiffre d'affaires] - [Coût des ventes], [Chiffre d'affaires] )

Taux de rupture =
DIVIDE (
    CALCULATE ( COUNTROWS ( fct_inventory_daily ), fct_inventory_daily[is_stockout] = TRUE () ),
    COUNTROWS ( fct_inventory_daily )
)

Stock moyen (EUR) =
AVERAGEX ( VALUES ( dim_date[date_day] ), CALCULATE ( SUM ( fct_inventory_daily[on_hand_value_eur] ) ) )

Rotation annualisée =
DIVIDE ( [Coût des ventes], [Stock moyen (EUR)] ) * DIVIDE ( 365, DISTINCTCOUNT ( fct_inventory_daily[snapshot_date] ) )

OTIF =
CALCULATE (
    AVERAGEX ( fct_purchase_order_lines, IF ( fct_purchase_order_lines[is_otif], 1, 0 ) ),
    fct_purchase_order_lines[is_evaluable] = TRUE ()
)
```

Ces mesures donnent les mêmes valeurs que le tableau de bord web (mêmes définitions que
`dashboard/queries.py`).

## 4. Pages proposées

1. **Ruptures** : taux de rupture par jour (courbe), par catégorie et par magasin (barres), top produits (tableau).
2. **Fournisseurs** : OTIF par fournisseur (barres), délai promis contre délai réel, statut des commandes.
3. **Rotation** : rotation annualisée et jours de stock par catégorie, valeur du stock par jour.
