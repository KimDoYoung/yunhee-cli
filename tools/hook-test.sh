#!/usr/bin/env bash
# usage: tools/hook-test.sh — PreToolUse 훅 단위 시험
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
H="$DIR/hook_guard.py"
chmod +x "$H"

fail=0
t() {
  want=$1; shift
  got=$(printf '%s' "$1" | jq -Rs '{tool_input:{command:.}}' | python3 "$H" | jq -r '.hookSpecificOutput.permissionDecision // "allow"')
  [ "$got" = deny ] && got=block
  [ -z "$got" ] && got=allow
  if [ "$got" = "$want" ]; then s=OK; else s=FAIL; fail=1; fi
  printf '%-5s want=%-5s got=%-5s %s\n' "$s" "$want" "$got" "$1"
}

# 1. psql 차단 및 허용 검사
t block 'psql -h localhost -U kdy987 -d asseterpdb -c "select 1"'
t block 'cd x && psql "$LOCAL_DB" -c "select 1"'
t block 'docker exec omen_postgres psql -U kdy987 -c "select 1"'
t block 'docker compose exec db psql -U u'
t block 'echo hi | psql'
t block 'sudo -u postgres psql'
t block 'pg_dump asseterpdb'
t block 'PGPASSWORD=x; psql -c 1'
t allow 'yunhee sql "select 1"'
t allow 'yunhee run "psql -c x"'
t allow 'git commit -m "psql 차단 훅"'
t allow 'ls /usr/bin | grep psql'
t allow 'which psql'
t allow 'echo "use psql later"'
t allow 'curl -s -d "psql ok" ntfy.sh/x'

# 2. 수정사항 039 #5 핵심 케이스 (① ~ ⑦)
# ① cat > a.md <<'EOF' \n tail -3 docs/x.md \n EOF -> 통과
t allow $'cat > a.md <<\'EOF\'\ntail -3 docs/x.md\nEOF'
# ② echo "tail -3 x" -> 통과
t allow 'echo "tail -3 x"'
# ③ python3 - <<'EOF' \n # tail of file \n EOF -> 통과
t allow $'python3 - <<\'EOF\'\n# tail of file\nEOF'
# ④ tail -3 docs/08-회차인계.md -> 차단
t block 'tail -3 docs/08-회차인계.md'
# ⑤ ls | tail -3 -> 통과
t allow 'ls | tail -3'
# ⑥ cat docs/as-is/src/x.md -> 차단
t block 'cat docs/as-is/src/x.md'
# ⑦ grep -n x f -A3 -> 차단
t block 'grep -n x frontend/src/a.tsx -A3'

# 3. 추가 쓰기 및 예외 케이스
t allow $'cat <<\'EOF\' > backend/src/main/java/A.java\npublic class A {}\nEOF'
t allow $'cat > docs/work/F/x.md <<\'EOF\'\ntail -3 docs/08-회차인계.md\ngrep -A3 x frontend/src/a.tsx\nEOF'
t allow 'git commit -m "cat frontend/src/a.tsx 설명"'
t block 'cat frontend/src/pages/apr/A.tsx'
t block 'tail -3 docs/as-is/src/apr/screens/A.md'
t block $'cat > x.md <<\'EOF\'\nhi\nEOF\ncat frontend/src/a.tsx'

echo "=== All hook tests finished. Exit code: $fail ==="
exit $fail
