#!/usr/bin/env bash
set -u
mkdir -p /mnt/e/opencell/.paper_cache
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'
for url in \
  'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC37484/pdf/' \
  'https://europepmc.org/backend/ptpmcrender.fcgi?accid=PMC37484&blobtype=pdf' \
  'https://www.pnas.org/content/pnas/98/15/8614.full.pdf' \
  'https://www.pnas.org/cgi/reprint/98/15/8614' ; do
  echo "=== $url"
  code=$(curl -sL -A "$UA" -H 'Accept: application/pdf,*/*' -o /tmp/test.pdf -w '%{http_code}' "$url")
  size=$(stat -c%s /tmp/test.pdf 2>/dev/null || echo 0)
  type=$(file -b /tmp/test.pdf 2>/dev/null)
  echo "  http=$code size=$size type=$type"
  if [ "$code" = "200" ] && echo "$type" | grep -qi PDF; then
    cp /tmp/test.pdf /mnt/e/opencell/.paper_cache/thattai2001.pdf
    echo "  SAVED."
    exit 0
  fi
done
echo "All sources failed."
exit 1
