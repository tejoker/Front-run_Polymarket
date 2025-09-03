# Configuration de Test - Bot Polymarket

## Mode Test Activé
**Capital de test : 1€** (sur 20€ total)

## Paramètres de Trading

### Seuils de Décision
- **BUY** : ROI > 3% ET confiance > 60%
- **SELL** : ROI > 2% ET confiance > 45%
- **MONITOR** : Sinon

### Gestion des Positions
- **Position de base** : 2.5% de 1€ = **0.025€**
- **Haute confiance** : +50% = **0.0375€**
- **Basse confiance** : -30% = **0.0175€**
- **Limite max** : 10% de 1€ = **0.10€**
- **Limite min** : 1% de 1€ = **0.01€**

## Activation du Mode Test

### Dans le code C++
```cpp
// Configuration automatique au démarrage
configure_test_mode(1.0, 0.025, 0.1, 0.01);
```

### Vérification
```cpp
show_test_config(); // Affiche la configuration
```

## Logs de Test

### Format des logs
```
[TEST] Position size: 0.0250€ (base: 2.5%, confiance: medium)
[PRIORITY] Trade priorisé: market_123 (ROI: 15.2%, Action: BUY)
[C++ DECISION] BUY signal for market_456 (ROI: 8.7%)
```

## Sécurité

### Limites de Perte
- **Perte max par trade** : 0.10€ (10% du capital de test)
- **Capital de réserve** : 19€ (95% du total)
- **Stop-loss global** : 0.50€ (50% du capital de test)

### Monitoring
- Vérifier les logs en temps réel
- Surveiller le PnL cumulé
- Valider la priorisation par ROI

## Phase de Test

### Semaine 1-2 : Validation
- Tester avec 1€
- Vérifier les signaux
- Valider la logique

### Semaine 3-4 : Optimisation
- Ajuster les seuils si nécessaire
- Optimiser les positions
- Affiner la confiance

### Semaine 5+ : Scaling
- Passer à 5€ puis 10€
- Finalement utiliser les 20€

## Commandes Utiles

### Compilation
```bash
cargo build --release
```

### Exécution avec logs détaillés
```bash
./target/release/polymarket-bot 2>&1 | tee test_run.log
```

### Vérification des logs
```bash
tail -f polymarket.log | grep "\[TEST\]"
```
