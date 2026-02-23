#!/usr/bin/env bash
# socks5_list_compile.sh
# Downloads multiple SOCKS5 proxy lists from GitHub, normalizes entries, and deduplicates.
# Result: soxlist1.txt (cleaned)

OUTFILE="soxlist1.txt"
TMPFILE="$(mktemp)"

# Download all lists
curl -s https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/roosterkid/openproxylist/7f81d7e1853389bf70b58edeefa87acefac29ae7/SOCKS5_RAW.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/jetkai/proxy-list/refs/heads/main/online-proxies/txt/proxies-socks5.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/proxifly/free-proxy-list/refs/heads/main/proxies/all/data.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/socks5_checked.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/iplocate/free-proxy-list/refs/heads/main/all-proxies.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"
curl -s https://raw.githubusercontent.com/ebrasha/abdal-proxy-hub/refs/heads/main/socks5-proxy-list-by-EbraSha.txt >> "$TMPFILE" && echo "" >> "$TMPFILE"

# Normalize and clean
cat "$TMPFILE" \
  | sed -E 's#^[[:space:]]+##; s#[[:space:]]+$##' \
  | sed -E 's#^(https?|socks4|socks5)://##i' \
  | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$' \
  | sort -u \
  > "$OUTFILE"

# Cleanup
rm -f "$TMPFILE"

echo "✅ Cleaned and deduplicated proxy list saved to: $OUTFILE"
echo "Total unique proxies: $(wc -l < "$OUTFILE")"
