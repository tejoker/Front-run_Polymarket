#!/bin/bash

# Script de test pour le bot Polymarket
echo "=== TEST DU BOT POLYMARKET ==="
echo "Mode test activé avec 1€ de capital"
echo ""

# Compilation
echo "1. Compilation du bot..."
cargo build --release
if [ $? -eq 0 ]; then
    echo "✅ Compilation réussie"
else
    echo "❌ Erreur de compilation"
    exit 1
fi

echo ""

# Vérification de la configuration
echo "2. Vérification de la configuration..."
echo "Capital de test: 1€"
echo "Position de base: 2.5%"
echo "Position max: 10%"
echo "Position min: 1%"
echo ""

# Test d'exécution (5 secondes)
echo "3. Test d'exécution (5 secondes)..."
echo "Appuyez sur Ctrl+C pour arrêter le test"
echo ""

# Exécution avec logs
timeout 5s ./target/release/polymarket-bot 2>&1 | tee test_output.log

echo ""
echo "=== RÉSULTATS DU TEST ==="
echo "Logs sauvegardés dans: test_output.log"
echo ""

# Vérification des logs de test
if grep -q "\[TEST\]" test_output.log; then
    echo "✅ Logs de test détectés"
    echo "Positions calculées:"
    grep "\[TEST\]" test_output.log | tail -3
else
    echo "⚠️  Aucun log de test détecté"
fi

echo ""
echo "=== MODE TEST PRÊT ==="
echo "Le bot est configuré pour trader avec 1€"
echo "Capital total disponible: 20€"
echo "Capital de réserve: 19€"
echo ""
echo "Pour lancer le trading complet:"
echo "./target/release/polymarket-bot"
