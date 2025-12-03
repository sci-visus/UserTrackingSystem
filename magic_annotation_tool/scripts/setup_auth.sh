#!/bin/bash
# Quick setup script for token authentication

echo "=================================================="
echo "Token Authentication Quick Setup"
echo "=================================================="
echo ""

# Check if running from correct directory
if [ ! -d "Docker" ]; then
    echo "❌ Error: Run this script from ink_annotation_tool root directory"
    exit 1
fi

echo "1️⃣  Checking current configuration..."
if grep -q "ENABLE_TOKEN_AUTH=true" app/.env 2>/dev/null; then
    echo "✅ Token authentication is ENABLED"
else
    echo "⚠️  Token authentication is DISABLED"
    echo ""
    read -p "Enable authentication? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sed -i 's/ENABLE_TOKEN_AUTH=false/ENABLE_TOKEN_AUTH=true/' app/.env 2>/dev/null || echo "ENABLE_TOKEN_AUTH=true" >> app/.env
        sed -i 's/ENABLE_TOKEN_AUTH=false/ENABLE_TOKEN_AUTH=true/' Docker/.env 2>/dev/null || echo "ENABLE_TOKEN_AUTH=true" >> Docker/.env
        echo "✅ Authentication enabled"
    fi
fi

echo ""
echo "2️⃣  Current tokens:"
grep "USER_TOKENS=" app/.env 2>/dev/null || echo "No tokens found"

echo ""
echo "3️⃣  Generate new tokens?"
read -p "Generate tokens for how many users? (Enter number or 0 to skip): " num_users

if [ "$num_users" -gt 0 ] 2>/dev/null; then
    echo ""
    python3 scripts/generate_tokens.py -n "$num_users"
    echo ""
    echo "⚠️  Remember to update app/.env and Docker/.env with the generated USER_TOKENS line!"
fi

echo ""
echo "4️⃣  Restart containers?"
read -p "Restart to apply changes? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd Docker
    docker-compose down
    docker-compose up -d
    echo "✅ Containers restarted"
    cd ..
fi

echo ""
echo "=================================================="
echo "✅ Setup Complete!"
echo "=================================================="
echo ""
echo "📋 Next Steps:"
echo "1. Copy generated tokens to .env files (if generated)"
echo "2. Share access URLs with users"
echo "3. Monitor logs: docker logs -f ink_annotation_tool"
echo ""
echo "📖 Full documentation: AUTH_SETUP.md"
echo "=================================================="
