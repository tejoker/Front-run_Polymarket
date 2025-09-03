# Bot Polymarket - Documentation

## Vue d'ensemble
Bot de trading automatisé pour les marchés de prédiction Polymarket, optimisé pour le HFT (High Frequency Trading) avec **priorisation automatique par ROI** et **exécution automatique de 1€** sur le meilleur trade.

## Architecture
- **Backend C++** : Moteur de trading ultra-optimisé (latence < 100ns)
- **Frontend Rust** : Interface et gestion des données
- **Base SQLite** : Stockage des opportunités et signaux (à optimiser)
- **API Polymarket** : Récupération des marchés en temps réel

## Fonctionnement

### 0. Système Automatique de Priorisation
- **Détection automatique** : Le bot scanne tous les marchés en continu
- **Calcul ROI en temps réel** : Chaque opportunité est évaluée instantanément
- **Priorisation automatique** : Tri par ROI décroissant (meilleur en premier)
- **Exécution automatique** : 1€ placé automatiquement sur le trade prioritaire
- **Résolution des conflits** : En cas de timing identique, le ROI le plus élevé gagne

### 1. Collecte de Données
- **Marchés Polymarket** : Récupération via API GraphQL
- **Sources d'information** : Monitoring de sources (Fed, SEC, médias)
- **Mots-clés** : Détection automatique de termes pertinents

### 2. Détection d'Opportunités
- **Analyse de pertinence** : Score basé sur la correspondance mots-clés/sources
- **Calcul ROI réaliste** : Formule intégrant frais, slippage et coûts fixes
- **Seuils de confiance** : High/Medium/Low selon la pertinence
- **Priorisation automatique** : Tri par ROI décroissant

### 3. Génération de Signaux
- **Décision automatique** :
  - ROI > 2% ET confiance > 40% → BUY
  - ROI > 1.5% ET confiance > 35% → SELL
  - Sinon → MONITOR
- **Priorisation automatique** : Sélectionne toujours le ROI le plus élevé
- **Exécution automatique** : 1€ direct sur le meilleur trade
- **Système simplifié** : Plus de calculs complexes, juste le meilleur ROI

### 4. Gestion des Positions
- **Taille fixe** : 1€ direct sur le meilleur trade
- **Priorisation automatique** : ROI le plus élevé gagne automatiquement
- **Exécution immédiate** : Trade automatique sans intervention manuelle
- **Simplicité** : Un seul trade à la fois, montant fixe de 1€
- **Conflits résolus** : En cas de timing identique, toujours le ROI le plus élevé

## Optimisations HFT

### Latence
- **Cache ROI** : Évite les recalculs (latence < 1μs)
- **Tables précalculées** : Lookup instantané
- **Décisions ultra-rapides** : < 100ns
- **Priorisation automatique** : Sélection instantanée du meilleur ROI

### Mémoire
- **Pré-allocation** : Vecteurs réservés
- **Nettoyage automatique** : Évite la fragmentation
- **Cache intelligent** : Gestion de taille automatique

## Configuration

### Paramètres Globaux
```cpp
GLOBAL_FEE = 0.03;           // 3% frais Polymarket
GLOBAL_CATCHUP_SPEED = 0.8;  // 80%/sec rattrapage
GLOBAL_ACTION_TIME = 0.025;   // 25ms latence HFT
GLOBAL_FIXED_COST = 0.0005;  // Coûts fixes réduits
```

### Sources Surveillées
- Federal Reserve, SEC, BEA, NBER
- Maison Blanche, Fox News, CNN
- Coinbase, Ethereum Foundation

## Logs et Monitoring

### Format des Logs
```
🚀 [EXECUTION] Trade automatique exécuté!
   Market: market_123
   Action: BUY
   ROI: 65.8%
   Montant: 1€
[PRIORITY] Trade priorisé: market_123 (ROI: 65.8%, Action: BUY)
[SUCCÈS] 5 opportunités de trading trouvées
```

### Métriques
- Nombre d'opportunités détectées
- Signaux générés
- **Trades automatiques exécutés**
- **ROI du trade prioritaire**
- PnL total
- Temps de réaction
- **Efficacité de la priorisation**

## Sécurité et Validation

### Vérifications
- **Montant fixe** : 1€ par trade
- Market ID valide
- **ROI prioritaire** : Sélection automatique du meilleur
- **Confiance minimale** : Respect des seuils de sécurité

### Gestion d'Erreurs
- Timeout API (5s)
- Retry automatique
- Fallback sur cache local

## Utilisation

### Compilation
```bash
cargo build --release
```

### Exécution
```bash
./target/release/polymarket-bot
```

### Variables d'Environnement
```bash
cp env.example .env
# Configurer les clés API et paramètres
```

## Performance

### Métriques Cibles
- **Latence totale** : < 100ms
- **Throughput** : 100+ marchés/sec
- **Précision ROI** : ±0.1%
- **Uptime** : 99.9%
- **Priorisation automatique** : < 10ms
- **Exécution automatique** : < 50ms

### Monitoring
- **Logs temps réel** avec exécutions automatiques
- **Métriques de performance** et priorisation
- **Alertes automatiques** pour trades exécutés
- **Dashboard de trading** avec ROI prioritaire
- **Suivi des conflits résolus** automatiquement

