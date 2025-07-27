# Formules de ROI pour l'Arbitrage Polymarket

## Vue d'ensemble

Ce document explique les deux formules de ROI (Return on Investment) implémentées dans le système de trading Polymarket pour détecter les opportunités d'arbitrage.

## Formule V1 : ROI Basique

### Principe

La formule V1 calcule le ROI basé sur la différence entre la valeur d'information (TRUE/FALSE) et la probabilité Polymarket, moins les frais.

### Formules

**Si information = TRUE (on parie sur YES) :**

```
ROI = 1 - p(a) - fee
```

**Si information = FALSE (on parie sur NO) :**

```
ROI = p(a) - fee
```

### Paramètres

- `p(a)` : Probabilité actuelle sur Polymarket (0.0 à 1.0)
- `fee` : Frais Polymarket (défaut 2% = 0.02)
- `information` : Valeur d'information (TRUE/FALSE)

### Exemple

```python
# Marché avec 70% de probabilité, information TRUE, frais 2%
ROI = 1 - 0.7 - 0.02 = 0.28 = 28%
```

## Formule V2 : ROI avec Facteur Temps

### Principe

La formule V2 introduit un facteur temps pour ajuster la probabilité future et ne s'applique que si le marché est ouvert.

### Formules

**Si information = TRUE (on parie sur YES) :**

```
ROI = 1(t) - p(a,t+ε) - fee
```

**Si information = FALSE (on parie sur NO) :**

```
ROI = p(a,t+ε) - fee
```

### Paramètres

- `p(a,t+ε)` : Probabilité ajustée par le facteur temps
- `time_factor` : Facteur d'ajustement temporel (défaut 1.0)
- `market_status` : Statut du marché ("open", "closed", "resolved")

### Calcul de la probabilité ajustée

```python
adjusted_probability = polymarket_probability * time_factor
adjusted_probability = max(0.0, min(1.0, adjusted_probability))  # Clamp à [0,1]
```

### Exemple

```python
# Marché avec 60% de probabilité, facteur temps 1.2, information TRUE
adjusted_prob = 0.6 * 1.2 = 0.72
ROI = 1 - 0.72 - 0.02 = 0.26 = 26%
```

## Implémentation dans le Code

### Fonctions Principales

1. **`calculate_potential_roi_v1()`** : Calcule le ROI V1
2. **`calculate_potential_roi_v2()`** : Calcule le ROI V2
3. **`calculate_potential_roi()`** : Calcule les deux versions et retourne un dictionnaire

### Utilisation

```python
# Calcul simple V1
roi_v1 = calculate_potential_roi_v1(True, 0.7, 0.02)

# Calcul V2 avec facteur temps
roi_v2 = calculate_potential_roi_v2(True, 0.7, 0.02, 1.1, "open")

# Calcul complet avec les deux versions
roi_data = calculate_potential_roi(
    relevance_score=0.8,
    information_value=True,
    polymarket_probability=0.7,
    polymarket_fee=0.02,
    time_factor=1.1,
    market_status="open",
    use_v2=True
)
```

## Estimation des Paramètres

### Valeur d'Information

La fonction `estimate_information_value()` détermine si l'information suggère TRUE ou FALSE basé sur :

- Score de pertinence
- Analyse des sources
- Mots-clés dans l'URL

### Probabilité Polymarket

La fonction `estimate_polymarket_probability()` estime la probabilité actuelle basée sur :

- Score de pertinence
- Niveau de confiance
- Heuristiques de marché

## Interprétation des Résultats

### ROI Positif

- Indique une opportunité d'arbitrage
- Plus le ROI est élevé, plus l'opportunité est attractive
- ROI V2 généralement plus précis avec le facteur temps

### ROI Négatif ou Nul

- Pas d'opportunité d'arbitrage
- Marché déjà efficacement valorisé
- Frais trop élevés par rapport au potentiel

### Comparaison V1 vs V2

- V2 prend en compte l'évolution temporelle
- V2 plus conservateur avec les marchés fermés
- V2 généralement plus précis pour les stratégies à long terme

## Recommandations d'Utilisation

1. **Utiliser V2 comme formule principale** pour une meilleure précision
2. **Comparer V1 et V2** pour comprendre l'impact du facteur temps
3. **Seuil minimum** : ROI > 5% pour considérer une opportunité
4. **Surveillance continue** : Les probabilités évoluent avec le temps
5. **Gestion des risques** : Diversifier sur plusieurs marchés

## Intégration dans le Système

Les nouvelles formules sont intégrées dans :

- `generate_trading_signals()` : Génération des signaux
- `backtest_strategy()` : Analyse des performances
- `create_performance_report()` : Rapports détaillés
- `display_created_data()` : Affichage des données

Chaque signal contient maintenant :

- `roi_v1` : ROI calculé avec la formule V1
- `roi_v2` : ROI calculé avec la formule V2
- `information_value` : Valeur d'information estimée
- `polymarket_probability` : Probabilité Polymarket estimée
