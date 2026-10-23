#!/usr/bin/env bash
# Re-download every raw input into data/raw/. Run from the project root:  bash scripts/download_data.sh
# Each download is checked so an HTML error page is never saved as data.
set -euo pipefail

UA="Sai Teja Koppolu skppolu1@memphis.edu"   # SEC EDGAR requires a name + email User-Agent
RAW=data/raw
mkdir -p "$RAW/fred" "$RAW/faf5" "$RAW/sec_edgar/fedex_corp_earnings"

check() {  # fail if the file looks like an HTML page instead of the expected format
  local f=$1 kind=$2
  case $kind in
    csv)  head -1 "$f" | grep -q '^observation_date,' || { echo "BAD (not FRED csv): $f"; exit 1; } ;;
    html) grep -qiE '<html|<document|<xbrl' "$f" || { echo "BAD (not html): $f"; exit 1; } ;;
    zip|xlsx) file "$f" | grep -qiE 'zip|excel|microsoft' || { echo "BAD (not zip/xlsx): $f"; exit 1; } ;;
    pdf)  file "$f" | grep -q PDF || { echo "BAD (not pdf): $f"; exit 1; } ;;
  esac
}

# --- FRED (no API key needed for fredgraph.csv) ---------------------------------------------
FRED_IDS="TRUCKD11 FRGSHPUSM649NCIS FRGEXPUSM649NCIS INDPRO IPMAN PCU484122484122 PCU484121484121
PCU4841248412 TSIFRGHT CES4348400001 RAILFRTCARLOADSD11 RAILFRTINTERMODALD11 GASDESW ISRATIO AMTMNO
DGORDER RSXFS WHLSLRIRSA"
for id in $FRED_IDS; do
  curl -sSf -o "$RAW/fred/$id.csv" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$id"
  check "$RAW/fred/$id.csv" csv
done

# --- FAF5.7.1 regional database + lookups ----------------------------------------------------
FAF=https://faf.ornl.gov/faf5
curl -sSf -o "$RAW/faf5/FAF5.7.1.zip" "$FAF/Data/Download_Files/FAF5.7.1.zip"; check "$RAW/faf5/FAF5.7.1.zip" zip
curl -sSf -o "$RAW/faf5/FAF5_metadata.xlsx" "$FAF/data/FAF5_metadata.xlsx"; check "$RAW/faf5/FAF5_metadata.xlsx" xlsx
curl -sSf -o "$RAW/faf5/CFS_area_code_FAF5_zone_id.xlsx" "$FAF/data/CFS%20area%20code%20-%20FAF5%20zone%20id.xlsx"
check "$RAW/faf5/CFS_area_code_FAF5_zone_id.xlsx" xlsx
curl -sSf -o "$RAW/faf5/FAF5_User_Guide.pdf" "$FAF/data/FAF5%20User%20Guide.pdf"; check "$RAW/faf5/FAF5_User_Guide.pdf" pdf
unzip -o -q "$RAW/faf5/FAF5.7.1.zip" -d "$RAW/faf5/FAF5.7.1"

# --- SEC EDGAR: FedEx Freight Holding Company, Inc. (FDXF, CIK 2082247) ------------------------
sec() { curl -sSf --compressed -A "$UA" -o "$2" "$1"; sleep 0.25; }
B=https://www.sec.gov/Archives/edgar/data/2082247
S=$RAW/sec_edgar
sec https://data.sec.gov/submissions/CIK0002082247.json "$S/submissions_CIK0002082247.json"
sec "$B/000162828026054314/fdxf-20260806.htm"               "$S/8-K_2026-08-06_fdxf-20260806.htm"
sec "$B/000162828026054314/fdxf-cy2025cy2024recast.htm"     "$S/8-K_2026-08-06_ex99_recast_cy2025_cy2024.htm"
sec "$B/000162828026045515/fdxf-20260625.htm"               "$S/8-K_2026-06-25_fdxf-20260625.htm"
sec "$B/000162828026045515/fdxf-q4fy2026juneearningsr.htm"  "$S/8-K_2026-06-25_ex99_q4fy2026_earnings_release.htm"
sec "$B/000162828026053359/fdxf-20260531.htm"               "$S/10-K_FY2026_fdxf-20260531.htm"
sec "$B/000110465926113295/tm2626881d1_8k.htm"              "$S/8-K_2026-10-02_tm2626881d1_8k.htm"
sec "$B/000110465926104793/tm2624680d1_8k.htm"              "$S/8-K_2026-09-02_tm2624680d1_8k.htm"
sec "$B/000110465926041977/tm2520565-10_1012b.htm"          "$S/Form10-12B-A_2026-04-10.htm"
for f in "$S"/*.htm; do check "$f" html; done

# --- SEC EDGAR: FedEx Corp (CIK 1048911) earnings releases with FedEx Freight segment stats ------
sec https://data.sec.gov/submissions/CIK0001048911.json "$S/fedex_corp_earnings/submissions_CIK0001048911.json"
.venv/bin/python -I scripts/fetch_fedex_corp_earnings.py "$S/fedex_corp_earnings"
for f in "$S"/fedex_corp_earnings/*.htm; do check "$f" html; done

echo "all downloads OK"
