#!/bin/bash
# Test authentication setup

echo "=================================================="
echo "🔐 Testing Token Authentication"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if containers are running
echo "1️⃣  Checking containers..."
if docker ps | grep -q ink_annotation_tool; then
    echo -e "${GREEN}✅ ink_annotation_tool is running${NC}"
else
    echo -e "${RED}❌ ink_annotation_tool is NOT running${NC}"
    echo "Start with: cd Docker && docker compose up -d"
    exit 1
fi

if docker ps | grep -q ink_annotation_redis; then
    echo -e "${GREEN}✅ ink_annotation_redis is running${NC}"
else
    echo -e "${RED}❌ ink_annotation_redis is NOT running${NC}"
    exit 1
fi

echo ""
echo "2️⃣  Checking authentication configuration..."

# Check if auth is enabled in container
AUTH_ENABLED=$(docker exec ink_annotation_tool python -c "import sys; sys.path.insert(0, '/main_app/app'); from auth_middleware import auth_manager; print(auth_manager.enabled)" 2>/dev/null)

if [ "$AUTH_ENABLED" = "True" ]; then
    echo -e "${GREEN}✅ Authentication is ENABLED${NC}"
else
    echo -e "${YELLOW}⚠️  Authentication is DISABLED${NC}"
fi

# Check number of tokens
NUM_TOKENS=$(docker exec ink_annotation_tool python -c "import sys; sys.path.insert(0, '/main_app/app'); from auth_middleware import auth_manager; print(len(auth_manager.tokens))" 2>/dev/null)
echo -e "${GREEN}✅ Loaded $NUM_TOKENS user token(s)${NC}"

echo ""
echo "3️⃣  Extracting your access token..."

# Get token from .env
TOKEN=$(grep "USER_TOKENS=" /local/data/magicscan/dev_sam/ink_annotation_tool/app/.env | cut -d'=' -f2 | cut -d':' -f2 | cut -d',' -f1)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}❌ No token found in .env${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Token found${NC}"

echo ""
echo "=================================================="
echo "📋 Your Access URLs"
echo "=================================================="
echo ""
echo "✅ Valid Token (should work):"
echo -e "${GREEN}http://localhost:10333/annotation_tool?token=$TOKEN${NC}"
echo ""
echo "❌ No Token (should show error):"
echo -e "${YELLOW}http://localhost:10333/annotation_tool${NC}"
echo ""
echo "❌ Invalid Token (should show error):"
echo -e "${YELLOW}http://localhost:10333/annotation_tool?token=invalid-token-123${NC}"
echo ""

echo "=================================================="
echo "🔍 Server Status"
echo "=================================================="
echo ""

# Check if Panel server is responding
if curl -s http://localhost:10333/annotation_tool > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Panel server is responding on port 10333${NC}"
else
    echo -e "${RED}❌ Panel server is NOT responding${NC}"
fi

if curl -s http://localhost:10444 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ DZI server is responding on port 10444${NC}"
else
    echo -e "${RED}❌ DZI server is NOT responding${NC}"
fi

echo ""
echo "=================================================="
echo "📊 Redis Status"
echo "=================================================="
echo ""

# Check Redis
REDIS_PING=$(docker exec ink_annotation_redis redis-cli PING 2>/dev/null)
if [ "$REDIS_PING" = "PONG" ]; then
    echo -e "${GREEN}✅ Redis is responding${NC}"
    
    # Count sessions
    SESSION_COUNT=$(docker exec ink_annotation_redis redis-cli KEYS "session:*" 2>/dev/null | wc -l)
    echo -e "${GREEN}   Active sessions: $SESSION_COUNT${NC}"
else
    echo -e "${RED}❌ Redis is NOT responding${NC}"
fi

echo ""
echo "=================================================="
echo "✅ Test Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Copy the 'Valid Token' URL above"
echo "2. Open it in your browser"
echo "3. You should see the annotation tool"
echo ""
echo "View logs: docker logs -f ink_annotation_tool"
echo "Full docs: AUTH_SETUP.md"
echo "=================================================="
