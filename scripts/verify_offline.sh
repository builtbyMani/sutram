#!/usr/bin/env bash
# verify_offline.sh -- prove the demo stack is venue-network-proof.
#
# What this checks HERE (no Docker daemon in this environment):
#   1. docker-compose.yml parses (docker compose config, or python yaml fallback)
#   2. The API Dockerfile contains every bake step the offline demo needs
#      (tesseract, spacy model, MiniLM priming, CPU-only torch, offline env)
#   3. The web Dockerfile uses a production build (no next dev at demo time)
#
# What MUST still be run once on a Docker host (see below): the live
# network-cut test. This script prints that procedure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "[ok] $1"; }
bad()  { FAIL=$((FAIL+1)); echo "[FAIL] $1"; }

echo "== 1. compose file parses =="
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose config >/dev/null && ok "docker compose config valid" \
    || bad "docker compose config invalid"
else
  python3 -c "
import yaml, sys
cfg = yaml.safe_load(open('docker-compose.yml'))
assert 'api' in cfg['services'] and 'web' in cfg['services'], 'services missing'
api = cfg['services']['api']
assert api.get('healthcheck'), 'api healthcheck missing'
web = cfg['services']['web']
assert web.get('depends_on', {}).get('api', {}).get('condition') == 'service_healthy', 'web must wait for healthy api'
assert web.get('environment', {}).get('API_URL') == 'http://api:8000', 'API_URL must target compose service name'
print('compose structure ok (python yaml fallback; no docker daemon here)')
" && ok "compose structure valid (yaml fallback)" || bad "compose yaml invalid"
fi

echo "== 2. API Dockerfile bake steps =="
D=apps/api/Dockerfile
grep -q "tesseract-ocr" "$D" && ok "tesseract in API image" || bad "tesseract missing"
grep -q "spacy download en_core_web_sm" "$D" && ok "spaCy model baked" || bad "spaCy model not baked"
grep -q "all-MiniLM-L6-v2" "$D" && ok "MiniLM priming step present" || bad "MiniLM priming missing"
grep -q "download.pytorch.org/whl/cpu" "$D" && ok "torch from CPU index" || bad "torch CPU index missing"
grep -q "HF_HUB_OFFLINE=1" "$D" && ok "offline env set (no runtime hub fetch)" || bad "offline env missing"
grep -q "COPY seeds" "$D" && ok "demo case seeds baked into image" || bad "seeds not copied"

echo "== 3. Web Dockerfile =="
W=apps/web/Dockerfile
grep -q "npm run build" "$W" && ok "production build (no next dev)" || bad "web still uses dev server"
grep -q '"start"' "$W" && ok "production start command" || bad "web start command missing"

echo "== 4. Seeder contract =="
python3 apps/api/app/seeds/seed_demo.py --dry-run >/dev/null \
  && ok "seed_demo.py --dry-run works" || bad "seed_demo.py broken"
python3 - <<'EOF' && echo "[ok] manifest readable, 49 artifacts" || echo "[FAIL] manifest unreadable"
import json
m = json.load(open('apps/api/seeds/operation-ledger/manifest.json'))
assert len(m['artifacts']) == 49, len(m['artifacts'])
EOF

echo
echo "----------------------------------------"
echo "static checks: $PASS passed, $FAIL failed"
echo "----------------------------------------"
echo
cat <<'NOTE'
MANUAL STEP (needs a Docker host -- no daemon in this environment):
  1. docker compose up --build -d
  2. docker compose exec api python -m app.seeds.seed_demo
  3. Cut the venue network: docker network disconnect <net> <api-container>
     (or unplug / firewall the host)
  4. Upload a chat fixture via the UI -> entities must still extract
     (proves spaCy + MiniLM are baked, not downloaded)
  5. Reconnect, docker compose down when done.
Expected: every step works with zero network. If step 4 fails, a model is
being fetched at runtime -- find it with: docker compose exec api env | grep -i proxy
NOTE
exit $FAIL
